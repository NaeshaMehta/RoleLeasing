"""Stage 1: SimPy events and raw CSV storage; no summary analytics here.

Physical mesh: undirected grid, one shared FIFO server per link (half duplex).
Logical hierarchy: predefined independently of the physical edges.
This is a teaching model, not a radio, distributed consensus or MAC simulator.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import PacketConfig, PROTOCOLS, ROLE_WEIGHTS, SCENARIOS

EVENT_COLUMNS = (
    "run_id", "scenario", "protocol", "seed", "event_seq", "timestamp_s", "event",
    "packet_id", "packet_type", "message_type", "source", "destination", "node_id",
    "link_id", "hop", "current_node", "size_bytes", "created_s", "latency_s", "queue_wait_s",
    "queue_size", "busy", "drop_reason", "delivered_bytes_total", "throughput_bps",
    "energy", "energy_delta", "role", "scope", "holder", "epoch", "version",
    "expiry_s", "available", "details_json",
)


@dataclass
class Node:
    energy: float
    health: float
    link_quality: float
    centrality: float
    failed: bool = False

    @property
    def alive(self):
        return not self.failed and self.energy > 0


@dataclass
class Lease:
    holder: str
    epoch: int
    version: int
    start_s: float
    expiry_s: float
    renewal_s: float


@dataclass
class Packet:
    packet_id: str
    packet_type: str
    message_type: str
    source: int
    destination: int
    size_bytes: int
    created_s: float
    current_node: int
    hop: int = 0


def stable_uniform(*parts):
    """Order-independent randomness: policy event counts cannot shift data draws."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class PacketNetwork:
    def __init__(self, config, seed, scenario, protocol, writer):
        import simpy  # Analytics can run on another computer without SimPy.

        self.simpy = simpy
        self.env = simpy.Environment()
        self.cfg, self.seed = config, seed
        self.scenario, self.protocol, self.writer = scenario, protocol, writer
        self.run_id = f"{scenario}:{protocol}:{seed}"
        self.sequence = self.control_sequence = self.delivered_bytes = 0
        self.nodes, self.children, self.adjacency = {}, {}, {}
        self.positions, self.node_subnet, self.subnet_network = {}, {}, {}
        self.leases, self.versions, self.previous_holders = {}, {}, {}
        self.initial_candidates = {}
        self.pending, self.inflight, self.last_vectors = set(), {}, {}
        self.role_state, self.down_since, self.ever_up = {}, {}, set()
        self.down_reason = {}
        self.gateway_load = {}
        self.last_active = None
        self.epoch = 0
        self._make_world()
        self.scopes = tuple(self.children)
        self.keys = tuple((role, scope) for scope in self.scopes for role in ROLE_WEIGHTS)
        self.links = {
            (u, v): simpy.Resource(self.env, capacity=1)
            for u in self.nodes for v in sorted(self.adjacency[u]) if u < v
        }

    def log(self, event, packet=None, **fields):
        self.sequence += 1
        row = dict(run_id=self.run_id, scenario=self.scenario, protocol=self.protocol,
                   seed=self.seed, event_seq=self.sequence, timestamp_s=self.env.now, event=event)
        if packet:
            row.update({key: getattr(packet, key) for key in (
                "packet_id", "packet_type", "message_type", "source", "destination",
                "size_bytes", "created_s", "hop", "current_node")})
        if "details" in fields:
            fields["details_json"] = json.dumps(fields.pop("details"), sort_keys=True, separators=(",", ":"))
        row.update(fields)
        self.writer.writerow(row)

    def _make_world(self):
        rng = random.Random(self.seed)
        n, columns = self.cfg.num_nodes, math.ceil(math.sqrt(self.cfg.num_nodes))
        for i in range(n):
            self.adjacency[i] = set()
            self.positions[i] = (i % columns, i // columns)
        for i in range(n):
            for j in (i + 1, i + columns):
                if j < n and (j == i + columns or i // columns == j // columns):
                    self.adjacency[i].add(j)
                    self.adjacency[j].add(i)
        degree = max(1, max(map(len, self.adjacency.values())))
        for i in range(n):
            self.nodes[i] = Node(rng.uniform(.75, 1), rng.uniform(.8, 1),
                                 rng.uniform(.75, 1), len(self.adjacency[i]) / degree)
            self.gateway_load[i] = 0
        subnet = node = 0
        for net, count in enumerate(self.cfg.subnet_counts):
            subnets = []
            for _ in range(count):
                name = f"subnet_{subnet}"
                subnets.append(name)
                members = tuple(f"node_{i}" for i in range(node, node + self.cfg.nodes_per_subnet))
                self.children[name] = members
                for i in range(node, node + self.cfg.nodes_per_subnet):
                    self.node_subnet[i] = name
                self.subnet_network[name] = f"network_{net}"
                node += self.cfg.nodes_per_subnet
                subnet += 1
            self.children[f"network_{net}"] = tuple(subnets)
        self.children["internetwork"] = tuple(f"network_{i}" for i in range(len(self.cfg.subnet_counts)))
        self.members = {}
        def leaves(entity):
            if entity.startswith("node_"):
                return (int(entity[5:]),)
            if entity not in self.members:
                self.members[entity] = tuple(i for child in self.children[entity] for i in leaves(child))
            return self.members[entity]
        leaves("internetwork")

    def representative(self, entity):
        ids = (int(entity[5:]),) if entity.startswith("node_") else self.members[entity]
        return next((i for i in ids if self.nodes[i].alive), None)

    def vectors(self):
        result = {}
        for i, node in self.nodes.items():
            result[f"node_{i}"] = {
                r: sum(getattr(node, k) * w for k, w in weights.items()) if node.alive else 0.0
                for r, weights in ROLE_WEIGHTS.items()
            }
        def aggregate(entity):
            if entity not in result:
                vectors = [aggregate(child) for child in self.children[entity]]
                result[entity] = {r: sum(v[r] for v in vectors) / len(vectors) for r in ROLE_WEIGHTS}
            return result[entity]
        aggregate("internetwork")
        return result

    def route(self, source, destination):
        if source is None or destination is None or not self.nodes[source].alive or not self.nodes[destination].alive:
            return None
        parents, queue = {source: None}, deque([source])
        while queue:
            u = queue.popleft()
            if u == destination:
                path = [u]
                while parents[path[-1]] is not None:
                    path.append(parents[path[-1]])
                return list(reversed(path))
            for v in sorted(self.adjacency[u]):
                if v not in parents and self.nodes[v].alive:
                    parents[v] = u
                    queue.append(v)
        return None

    def role_available(self, key):
        lease = self.leases.get(key)
        return bool(lease and self.representative(lease.holder) is not None
                    and (self.protocol != "proposed" or
                         lease.epoch == int(self.env.now // self.cfg.epoch_s) and self.env.now < lease.expiry_s))

    def audit(self):
        """Log exact role state transitions and active-node lifetime transitions."""
        active = sum(node.alive for node in self.nodes.values())
        if active != self.last_active:
            self.log("ACTIVE_COUNT", details={"active": active, "total": len(self.nodes)})
            self.last_active = active
        for key in self.keys:
            available = self.role_available(key)
            if self.role_state.get(key) == available:
                continue
            was_up = self.role_state.get(key, False)
            self.role_state[key] = available
            role, scope = key
            lease = self.leases.get(key)
            cause = ("holder_failure" if lease and self.representative(lease.holder) is None
                     else "epoch" if lease and self.protocol == "proposed" and lease.epoch != int(self.env.now // self.cfg.epoch_s)
                     else "expiry" if lease and self.protocol == "proposed" and self.env.now >= lease.expiry_s
                     else "bootstrap" if key not in self.ever_up else "assignment_missing")
            self.log("ROLE_STATE", role=role, scope=scope, available=int(available),
                     holder=lease.holder if lease else "", details={"cause": "available" if available else cause})
            if available:
                if key in self.ever_up:
                    self.log("ROLE_RECOVERED", role=role, scope=scope,
                             latency_s=self.env.now - self.down_since[key],
                             details={"cause": self.down_reason[key]})
                self.ever_up.add(key)
                self.down_since.pop(key, None)
            elif was_up or key not in self.down_since:
                self.down_since[key] = self.env.now
                self.down_reason[key] = cause

    def energy_change(self, node_id, amount, cause):
        node = self.nodes[node_id]
        before = node.energy
        node.energy = max(0.0, node.energy - amount)
        self.log("ENERGY_CHANGE", node_id=node_id, energy=node.energy,
                 energy_delta=before - node.energy, details={"cause": cause})
        if before > 0 and node.energy == 0:
            self.log("NODE_DEPLETED", node_id=node_id)
            self.audit()

    def new_packet(self, source, destination, kind, message, size, packet_id=None):
        if packet_id is None:
            self.control_sequence += 1
            packet_id = f"C:{self.control_sequence}"
        packet = Packet(packet_id, kind, message, source, destination, size, self.env.now, source)
        self.inflight[packet_id] = packet
        self.log("PACKET_GENERATED", packet)
        return packet

    def finish(self, packet, reason=None):
        if packet.packet_id not in self.inflight:
            raise RuntimeError("packet terminated more than once")
        del self.inflight[packet.packet_id]
        if reason:
            self.log("PACKET_DROPPED", packet, latency_s=self.env.now - packet.created_s,
                     drop_reason=reason)
            return False
        if packet.packet_type == "data":
            self.delivered_bytes += packet.size_bytes
        self.log("PACKET_DELIVERED", packet, latency_s=self.env.now - packet.created_s,
                 delivered_bytes_total=self.delivered_bytes,
                 throughput_bps=8 * self.delivered_bytes / self.env.now if self.env.now else 0)
        return True

    def queue_state(self, edge):
        resource = self.links[edge]
        self.log("QUEUE_STATE", link_id=f"{edge[0]}-{edge[1]}",
                 queue_size=len(resource.queue), busy=resource.count)

    def transmit(self, packet, destination):
        """Route one leg; return a drop reason or None. No hidden retransmits."""
        path = self.route(packet.current_node, destination)
        if path is None:
            return "no_route"
        for u, v in zip(path, path[1:]):
            packet.hop += 1
            edge = tuple(sorted((u, v)))
            link, resource = f"{edge[0]}-{edge[1]}", self.links[edge]
            self.log("HOP_ARRIVAL", packet, node_id=u, link_id=link)
            if resource.count and len(resource.queue) >= self.cfg.queue_capacity:
                self.log("QUEUE_DROP", packet, node_id=u, link_id=link,
                         queue_size=len(resource.queue), drop_reason="queue_overflow")
                return "queue_overflow"
            arrival = self.env.now
            with resource.request() as request:
                self.queue_state(edge)
                yield request
                self.queue_state(edge)
                if not self.nodes[u].alive or not self.nodes[v].alive:
                    self.log("HOP_FAILED", packet, link_id=link, drop_reason="node_unavailable")
                    reason = "node_unavailable"
                else:
                    service = packet.size_bytes * 8 / self.cfg.bandwidth_bps
                    self.log("TX_START", packet, node_id=u, link_id=link,
                             queue_wait_s=self.env.now - arrival,
                             details={"service_s": service})
                    self.energy_change(u, packet.size_bytes * self.cfg.tx_energy_per_byte, "tx")
                    self.energy_change(v, packet.size_bytes * self.cfg.rx_energy_per_byte, "rx")
                    yield self.env.timeout(service)
                    self.log("TX_END", packet, node_id=u, link_id=link)
                    quality = min(self.nodes[u].link_quality, self.nodes[v].link_quality)
                    loss = self.cfg.base_link_loss + self.cfg.quality_loss_weight * (1 - quality)
                    reason = ("node_unavailable" if not self.nodes[u].alive or not self.nodes[v].alive
                              else "link_loss" if stable_uniform(self.seed, packet.packet_id,
                                                                 packet.hop, link) < loss else None)
                    if reason:
                        self.log("HOP_FAILED", packet, link_id=link, drop_reason=reason)
            self.queue_state(edge)
            if reason:
                return reason
            yield self.env.timeout(self.cfg.propagation_s)
            if not self.nodes[v].alive:
                self.log("HOP_FAILED", packet, link_id=link, drop_reason="node_unavailable")
                return "node_unavailable"
            packet.current_node = v
            self.log("HOP_RECEIVED", packet, node_id=v, link_id=link)
        return None

    def control(self, source, destination, message, size=64):
        packet = self.new_packet(source, destination, "control", message, size)
        reason = yield from self.transmit(packet, destination)
        return self.finish(packet, reason)

    def gateway_node(self, scope):
        """Delegate an aggregate gateway role through its child gateway leases."""
        key = ("gateway", scope)
        if not self.role_available(key):
            return None
        holder = self.leases[key].holder
        if holder.startswith("node_"):
            return self.representative(holder)
        return self.gateway_node(holder)

    def sensor_packet(self, source, sequence):
        packet = self.new_packet(source, 0, "data", "SENSOR_DATA",
                                 self.cfg.packet_size_bytes, f"D:{source}:{sequence}")
        if not self.nodes[source].alive:
            self.finish(packet, "source_unavailable")
            return
        subnet = self.node_subnet[source]
        scopes = (subnet, self.subnet_network[subnet], "internetwork")
        for scope in scopes:
            destination = self.gateway_node(scope)
            if destination is None:
                self.finish(packet, "gateway_unavailable")
                return
            # Freeze every lease used in recursive delegation during this leg.
            chain, current = [], scope
            while not current.startswith("node_"):
                key = ("gateway", current)
                chain.append((key, self.leases[key].version))
                current = self.leases[key].holder
            reason = yield from self.transmit(packet, destination)
            if reason:
                self.finish(packet, reason)
                return
            if any(not self.role_available(key) or self.leases[key].version != version
                   for key, version in chain):
                self.finish(packet, "lease_changed_in_transit")
                return
            self.gateway_load[destination] += 1
            self.log("GATEWAY_FORWARD", packet, node_id=destination, scope=scope, role="gateway")
        reason = yield from self.transmit(packet, 0)  # node 0 is the fixed sink attachment
        self.finish(packet, reason)

    def traffic(self):
        schedule = []
        for node_id in self.nodes:
            offset = stable_uniform(self.seed, "traffic", node_id) * self.cfg.packet_interval_s
            sequence = 0
            time = offset
            while time < self.cfg.duration_s:
                schedule.append((time, node_id, sequence))
                sequence += 1
                time = offset + sequence * self.cfg.packet_interval_s
        for time, node_id, sequence in sorted(schedule):
            yield self.env.timeout(time - self.env.now)
            self.env.process(self.sensor_packet(node_id, sequence))

    def disturbance_schedule(self):
        rng = random.Random(self.seed + 98761)
        # Keep the external sink attachment alive; all policies see the same IDs.
        targets = sorted(rng.sample(list(range(1, self.cfg.num_nodes)),
                                    min(max(1, self.cfg.num_nodes // 10), self.cfg.num_nodes - 1)))
        duration = self.cfg.duration_s
        if self.scenario == "normal":
            return []
        if self.scenario == "node_failures":
            return [(duration * f, i, kind, 0) for f, kind in ((.25, "fail"), (.75, "recover")) for i in targets]
        kind = "energy" if self.scenario == "energy_degradation" else "link"
        amount = .25 if kind == "energy" else .35
        return [(duration * f, i, kind, amount) for f in (.25, .5) for i in targets]

    def disturbances(self):
        for time, node_id, kind, amount in self.disturbance_schedule():
            yield self.env.timeout(time - self.env.now)
            node = self.nodes[node_id]
            if kind in ("fail", "recover"):
                node.failed = kind == "fail"
            elif kind == "energy":
                self.energy_change(node_id, amount, "injected_degradation")
            else:
                node.link_quality = max(0, node.link_quality - amount)
            self.log("DISTURBANCE", node_id=node_id,
                     details={"kind": kind, "amount": amount, "link_quality": node.link_quality})
            self.audit()

    def migration_cost(self, old, new, scope):
        parent, old_rep, new_rep = map(self.representative, (scope, old, new))
        pairs = ((old_rep, parent), (parent, new_rep), (new_rep, parent),
                 (old_rep, new_rep), (parent, new_rep), (new_rep, parent))
        paths = [self.route(u, v) for u, v in pairs]
        if any(path is None for path in paths):
            return math.inf
        energy = sum((len(path) - 1) * size * (self.cfg.tx_energy_per_byte + self.cfg.rx_energy_per_byte)
                     for path, size in zip(paths, (64, 64, 64, 256, 64, 64)))
        return (self.cfg.migration_alpha * 6 + self.cfg.migration_beta * self.cfg.state_transfer
                + self.cfg.migration_gamma * energy + self.cfg.migration_delta * self.cfg.disruption)

    def transaction(self, key, candidate, capability, cost=0.0, renewal=False):
        """Commit only after delivered control messages; old lease remains until commit."""
        self.pending.add(key)
        role, scope = key
        old = self.leases.get(key)
        old_holder = old.holder if old else self.previous_holders.get(key)
        old_capability = self.vectors().get(old_holder, {}).get(role, 0.0)
        transaction_epoch = self.epoch
        parent, new_rep = self.representative(scope), self.representative(candidate)
        proactive = not renewal and old and self.role_available(key) and old.holder != candidate
        self.log("TRANSACTION_START", role=role, scope=scope, holder=candidate,
                 details={"renewal": renewal, "proactive": bool(proactive), "cost": cost})
        try:
            grant = "LEASE_GRANT" if self.protocol == "proposed" else "ROLE_ASSIGN"
            ack = "LEASE_ACK" if self.protocol == "proposed" else "ROLE_ACK"
            if proactive:
                old_rep = self.representative(old.holder)
                messages = ((old_rep, parent, "MIGRATE_INTENT", 64),
                            (parent, new_rep, "MIGRATE_PREPARE", 64),
                            (new_rep, parent, "MIGRATE_READY", 64),
                            (old_rep, new_rep, "STATE_TRANSFER", 256),
                            (parent, new_rep, grant, 64),
                            (new_rep, parent, ack, 64))
            else:
                messages = ((parent, new_rep, "LEASE_RENEW" if renewal else grant, 64),
                            (new_rep, parent, ack, 64))
            for source, destination, message, size in messages:
                if not (yield from self.control(source, destination, message, size)):
                    self.log("TRANSACTION_ABORT", role=role, scope=scope, details={"reason": "control_delivery"})
                    return
            if (self.protocol == "proposed" and int(self.env.now // self.cfg.epoch_s) != transaction_epoch
                    or self.representative(candidate) is None
                    or (proactive or renewal) and not self.role_available(key)):
                self.log("TRANSACTION_ABORT", role=role, scope=scope, details={"reason": "lease_or_epoch_changed"})
                return
            if old and not renewal:
                self.log("LEASE_EXPIRE" if self.protocol == "proposed" else "ASSIGNMENT_RELEASED",
                         role=role, scope=scope, holder=old.holder,
                         epoch=old.epoch, version=old.version, details={"reason": "atomic_handover"})
            now = self.env.now
            duration = self.cfg.lease_min_s + capability * (self.cfg.lease_max_s - self.cfg.lease_min_s)
            version = self.versions.get(key, 0) + (0 if renewal else 1)
            self.versions[key] = version
            lease = Lease(candidate, transaction_epoch, version, now,
                          now + duration if self.protocol == "proposed" else math.inf,
                          now + duration * self.cfg.renewal_fraction)
            self.leases[key] = lease
            self.previous_holders[key] = candidate
            if self.protocol == "proposed":
                self.env.process(self.lease_boundary(key, lease))
            activation = "LEASE_ACTIVATED" if self.protocol == "proposed" else "ASSIGNMENT_ACTIVATED"
            self.log("LEASE_RENEWED" if renewal else activation, role=role, scope=scope,
                     holder=candidate, epoch=transaction_epoch, version=version,
                     expiry_s=lease.expiry_s if math.isfinite(lease.expiry_s) else "",
                     details={"capability": capability})
            if old_holder and candidate != old_holder:
                self.log("ROLE_MIGRATION", role=role, scope=scope, holder=candidate,
                         details={"old_holder": old_holder, "new_holder": candidate,
                                  "old_capability": old_capability, "new_capability": capability,
                                  "migration_cost": cost, "old_utility": old_capability,
                                  "new_utility": capability - self.cfg.migration_weight * cost
                                  if self.protocol == "proposed" else capability,
                                  "kind": "proactive" if proactive else "reassignment"})
            self.audit()
        finally:
            self.pending.discard(key)

    def lease_boundary(self, key, lease):
        boundary = min(lease.expiry_s, (lease.epoch + 1) * self.cfg.epoch_s)
        yield self.env.timeout(max(0, boundary - self.env.now))
        if self.leases.get(key) is lease:
            self.log("LEASE_VALIDITY_ENDED", role=key[0], scope=key[1], holder=lease.holder,
                     epoch=lease.epoch, version=lease.version)
            self.audit()

    def controller(self):
        while True:
            now = self.env.now
            self.epoch = int(now // self.cfg.epoch_s) if self.protocol == "proposed" else 0
            for key, lease in tuple(self.leases.items()):
                if self.protocol == "proposed" and (lease.epoch != self.epoch or now >= lease.expiry_s):
                    self.log("LEASE_EXPIRE", role=key[0], scope=key[1], holder=lease.holder,
                             epoch=lease.epoch, version=lease.version,
                             details={"reason": "epoch" if lease.epoch != self.epoch else "timeout"})
                    del self.leases[key]
            self.audit()
            vectors = self.vectors()
            for key in self.keys:
                if key in self.pending or self.protocol == "static" and key in self.ever_up:
                    continue
                role, scope = key
                parent = self.representative(scope)
                candidates = [e for e in self.children[scope]
                              if self.route(parent, self.representative(e)) is not None]
                if not candidates:
                    continue
                best = max(candidates, key=lambda e: (vectors[e][role], e))
                if self.protocol == "static":
                    # Bootstrap retries target the same initial holder; static never
                    # changes an assignment after it has first become operational.
                    best = self.initial_candidates.setdefault(key, best)
                    if self.route(parent, self.representative(best)) is None:
                        continue
                lease = self.leases.get(key)
                if not self.role_available(key):
                    # Detection delay applies to physical holder failure, not bootstrap/expiry.
                    if lease and self.representative(lease.holder) is None:
                        if now - self.down_since[key] < self.cfg.detection_s:
                            continue
                    self.pending.add(key)
                    self.env.process(self.transaction(key, best, vectors[best][role]))
                    continue
                if self.protocol == "proposed":
                    scored = [(vectors[e][role] - self.cfg.migration_weight * self.migration_cost(lease.holder, e, scope), e)
                              for e in candidates if e != lease.holder]
                    utility, candidate = max(scored, default=(-math.inf, lease.holder))
                    if utility > vectors[lease.holder][role] + self.cfg.hysteresis_delta:
                        cost = self.migration_cost(lease.holder, candidate, scope)
                        self.pending.add(key)
                        self.env.process(self.transaction(key, candidate, vectors[candidate][role], cost))
                    elif now >= lease.renewal_s:
                        self.pending.add(key)
                        self.env.process(self.transaction(key, lease.holder, vectors[lease.holder][role], renewal=True))
                elif best != lease.holder:
                    self.pending.add(key)
                    cost = self.migration_cost(lease.holder, best, scope)
                    self.env.process(self.transaction(key, best, vectors[best][role], cost))
            yield self.env.timeout(self.cfg.evaluation_s)

    def capability_updates(self):
        if self.protocol == "static":
            return
        self.last_vectors = self.vectors()
        parents = {child: parent for parent, children in self.children.items() for child in children}
        while True:
            yield self.env.timeout(self.cfg.evaluation_s)
            vectors = self.vectors()
            for entity, parent in parents.items():
                changed = max(abs(vectors[entity][r] - self.last_vectors[entity][r]) for r in ROLE_WEIGHTS)
                if changed > self.cfg.capability_epsilon and self.representative(entity) is not None:
                    self.env.process(self.control(self.representative(entity), self.representative(parent), "CAP_UPDATE"))
                    self.last_vectors[entity] = vectors[entity]
            if self.env.now % self.cfg.summary_s < self.cfg.evaluation_s:
                for scope in self.scopes:
                    if scope != "internetwork":
                        self.env.process(self.control(self.representative(scope),
                                                      self.representative(parents[scope]), "SUMMARY"))

    def snapshot(self):
        self.audit()
        for i, node in self.nodes.items():
            self.log("NODE_SAMPLE", node_id=i, energy=node.energy, available=int(node.alive),
                     details={"gateway_forwards": self.gateway_load[i]})
        self.log("RUN_SAMPLE", delivered_bytes_total=self.delivered_bytes,
                 throughput_bps=8 * self.delivered_bytes / self.env.now if self.env.now else 0,
                 queue_size=sum(len(r.queue) for r in self.links.values()))

    def sampler(self):
        while True:
            self.snapshot()
            yield self.env.timeout(self.cfg.sample_s)

    def run(self):
        self.log("RUN_START", details={"config": asdict(self.cfg), "roles": len(self.keys),
                                       "role_weights": ROLE_WEIGHTS,
                                       "disturbances": self.disturbance_schedule()})
        for i, node in self.nodes.items():
            self.log("NODE_INIT", node_id=i, energy=node.energy,
                     details={"health": node.health, "link_quality": node.link_quality,
                              "centrality": node.centrality, "position": self.positions[i],
                              "subnet": self.node_subnet[i]})
        for edge in self.links:
            self.queue_state(edge)
        for process in (self.disturbances, self.controller, self.traffic, self.capability_updates, self.sampler):
            self.env.process(process())
        self.env.run(until=self.cfg.duration_s)
        # Fixed observation window: do not call in-flight packets drops, or drain
        # after the window while other protocol/traffic processes keep running.
        self.snapshot()
        for packet in self.inflight.values():
            self.log("PACKET_CENSORED", packet, latency_s=self.env.now - packet.created_s,
                     details={"reason": "observation_window_ended"})
        for key in sorted(self.ever_up):
            if not self.role_state[key]:
                self.log("ROLE_UNRECOVERED", role=key[0], scope=key[1],
                         latency_s=self.env.now - self.down_since[key],
                         details={"cause": self.down_reason[key]})
        self.log("RUN_END", details={"duration_s": self.env.now})


def run_simulation(output_path="raw_simulation_events.csv", config=None,
                   seeds=(42, 43, 44), scenarios=SCENARIOS, protocols=PROTOCOLS):
    """Write raw events for a matched experiment matrix, then close the CSV.

    Every run is fresh. Traffic times, initial states and injected disturbances
    depend on seed, not protocol. No analytics state is passed to stage 2.
    """
    config = config or PacketConfig()
    seeds, scenarios, protocols = tuple(seeds), tuple(scenarios), tuple(protocols)
    if not seeds or not scenarios or not protocols:
        raise ValueError("seeds, scenarios and protocols cannot be empty")
    if len(set(seeds)) != len(seeds) or any(type(seed) is not int for seed in seeds):
        raise ValueError("seeds must be unique integers")
    if len(set(scenarios)) != len(scenarios) or not set(scenarios) <= set(SCENARIOS):
        raise ValueError("unknown or duplicate scenarios")
    if len(set(protocols)) != len(protocols) or not set(protocols) <= set(PROTOCOLS):
        raise ValueError("unknown or duplicate protocols")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        for seed in seeds:
            for scenario in scenarios:
                for protocol in protocols:
                    print(f"Simulating seed={seed} scenario={scenario} protocol={protocol}")
                    PacketNetwork(config, seed, scenario, protocol, writer).run()
    return path
