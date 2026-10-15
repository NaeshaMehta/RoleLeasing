"""Thin Mesa coordinator for reproducible simulation ticks."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import mesa
import numpy as np

from simulation.capability import refresh_capabilities
from simulation.communications import NetworkRouter, RouteResult
from simulation.config import PROTOCOLS, SCENARIOS, SimulationConfig
from simulation.entities import EntityHierarchy, build_hierarchy
from simulation.events import SimulationEvent, apply_event
from simulation.metrics import MetricsRecorder
from simulation.protocols import ProtocolEngine
from simulation.topology import NetworkTopology, create_topology


class RoleSimulationModel(mesa.Model):
    """One deterministic simulation world; protocols differ only by policy."""

    def __init__(
        self,
        config: SimulationConfig | None = None,
        protocol: str = "proposed",
        scenario: str = "normal",
        event_schedule: Iterable[SimulationEvent] = (),
    ) -> None:
        selected_config = config or SimulationConfig()
        if protocol not in PROTOCOLS:
            raise ValueError(f"protocol must be one of {PROTOCOLS}")
        if scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {SCENARIOS}")
        super().__init__(seed=selected_config.seed)
        self.config = selected_config
        self.protocol = protocol
        self.scenario = scenario
        self.current_epoch = 1
        self.network_lifetime_tick: int | None = None
        self.topology: NetworkTopology = create_topology(self.config)
        self.hierarchy: EntityHierarchy = build_hierarchy(
            self,
            self.topology,
            battery_capacity=self.config.battery_capacity,
        )
        self.nodes_by_id = self.hierarchy.nodes_by_id
        self.initial_mean_energy = sum(node.energy for node in self.nodes_by_id.values()) / len(self.nodes_by_id)
        solar_rng = np.random.default_rng(self.config.seed + 1_000_003)
        for node in self.nodes_by_id.values():
            node.solar_harvest_rate = (
                self.config.solar_harvest_rate * float(solar_rng.uniform(0.5, 1.5))
            )
        self.solar_energy_harvested = 0.0
        self.solar_energy_curtailed = 0.0
        self.solar_energy_harvested_step = 0.0
        self.router = NetworkRouter(self.topology, self.hierarchy, self.config)
        if protocol == "hierarchical":
            self.controller_node_id = self.random.choice(tuple(self.nodes_by_id))
        else:
            self.controller_node_id = max(
                self.nodes_by_id,
                key=lambda node_id: (self.nodes_by_id[node_id].centrality, -node_id),
            )
        self.node_failure_times: dict[int, float] = {}
        self._energy_depleted_node_ids: set[int] = set()
        self._dirty_scope_ids: set[str] = set()
        self._scheduled_events: dict[int, list[SimulationEvent]] = defaultdict(list)
        for event in event_schedule:
            if event.tick > self.config.steps:
                raise ValueError(f"event at tick {event.tick} exceeds configured run length")
            if event.node_id not in self.nodes_by_id:
                raise ValueError(f"event references unknown node {event.node_id}")
            self._scheduled_events[event.tick].append(event)
        for events in self._scheduled_events.values():
            events.sort()

        self.child_weights: dict[str, dict[int | str, float]] = {}
        self.node_loads = {node_id: 0.0 for node_id in self.nodes_by_id}
        self.gateway_loads = {node_id: 0.0 for node_id in self.nodes_by_id}
        self.data_offered = 0
        self.data_delivered = 0
        refresh_capabilities(self.hierarchy, self.child_weights)
        self._node_capability_snapshot = {
            (node_id, role): node.capability(role)
            for node_id, node in self.nodes_by_id.items()
            for role in node.capability_vector()
        }
        self.protocol_engine = ProtocolEngine(self, protocol)
        self.current_epoch = self.protocol_engine.current_epoch
        self.metrics = MetricsRecorder(self)
        self.router.begin_step()
        self.metrics.record(0)

    @property
    def controller_available(self) -> bool:
        return self.nodes_by_id[self.controller_node_id].is_available()

    def control_source(self, scope: str) -> int | None:
        if self.protocol in {"centralized", "hierarchical"}:
            return self.controller_node_id if self.controller_available else None
        return self.hierarchy.representative_node_id(scope)

    def control_exchange(self, kind: str, scope: str, holder_id: int | str) -> RouteResult | None:
        source = self.control_source(scope)
        destination = self.hierarchy.representative_node_id(holder_id)
        if source is None or destination is None:
            return None
        return self.router.send(kind, source, destination)

    def control_exchange_batch(
        self,
        kind: str,
        scope: str,
        destination_node_ids: tuple[int, ...],
    ) -> bool:
        source = self.control_source(scope)
        return self.router.send_control_batch(source, destination_node_ids)

    def holder_unavailable_since(self, holder_id: int | str) -> float | None:
        node_ids = self.hierarchy.node_ids_for_entity(holder_id)
        if any(self.nodes_by_id[node_id].is_available() for node_id in node_ids):
            return None
        failure_times = [self.node_failure_times[node_id] for node_id in node_ids if node_id in self.node_failure_times]
        return max(failure_times) if failure_times else None

    def fail_node(self, node_id: int) -> bool:
        return self._apply_manual_event("fail", node_id)

    def recover_node(self, node_id: int) -> bool:
        return self._apply_manual_event("recover", node_id)

    def degrade_energy(self, node_id: int, amount: float) -> bool:
        return self._apply_manual_event("degrade_energy", node_id, amount)

    def degrade_link(self, node_id: int, amount: float) -> bool:
        return self._apply_manual_event("degrade_link", node_id, amount)

    def run_steps(self, steps: int | None = None) -> None:
        run_length = self.config.steps if steps is None else steps
        if run_length < 0:
            raise ValueError("steps must be non-negative")
        if self.steps + run_length > self.config.steps:
            raise ValueError("requested run exceeds configured run length")
        for _ in range(run_length):
            self.step()

    def step(self) -> None:
        now = int(self.steps)
        self.router.begin_step()
        state_changed = False
        for event in self._scheduled_events.pop(now, []):
            changed = self._apply_event(event, float(now))
            state_changed = changed or state_changed
            if changed:
                self._mark_node_scopes_dirty(event.node_id)
        state_changed = self._fail_energy_empty_nodes(float(now)) or state_changed
        refresh_capabilities(self.hierarchy, self.child_weights)
        self._detect_material_capability_changes()
        affected_scopes = frozenset(self._dirty_scope_ids)
        self._dirty_scope_ids.clear()
        self.protocol_engine.step(
            now,
            state_changed=state_changed,
            affected_scopes=affected_scopes,
        )
        self.current_epoch = self.protocol_engine.current_epoch
        self._harvest_solar_energy()
        self._route_sensor_traffic()
        self._fail_energy_empty_nodes(float(now))
        refresh_capabilities(self.hierarchy, self.child_weights)
        self.metrics.record(now)

    def _harvest_solar_energy(self) -> None:
        self.solar_energy_harvested_step = 0.0
        recovered_nodes = False
        for node_id, node in self.nodes_by_id.items():
            rate = node.solar_harvest_rate
            accepted = node.harvest_energy(rate)
            self.solar_energy_harvested_step += accepted
            self.solar_energy_curtailed += rate - accepted
            if (
                node_id in self._energy_depleted_node_ids
                and node.energy >= self.config.minimum_energy_reserve
            ):
                node.recover()
                self._energy_depleted_node_ids.remove(node_id)
                self.node_failure_times.pop(node_id, None)
                self._mark_node_scopes_dirty(node_id)
                recovered_nodes = True
        if recovered_nodes:
            self.router.invalidate_graph()
        self.solar_energy_harvested += self.solar_energy_harvested_step

    def _route_sensor_traffic(self) -> None:
        self.gateway_loads = {node_id: 0.0 for node_id in self.nodes_by_id}
        active_subnets: set[str] = set()
        for node_id, node in self.nodes_by_id.items():
            if not node.is_available():
                continue
            self.node_loads[node_id] += 1.0
            self.data_offered += 1
            subnet_id = node.subnet_id
            lease = self.protocol_engine.assignments.get(("gateway", subnet_id))
            if lease is None or not self.protocol_engine.role_available("gateway", subnet_id):
                self.router.record_unrouted_data()
                continue
            gateway_node = self.hierarchy.representative_node_id(lease.holder_id)
            if gateway_node is None:
                self.router.record_unrouted_data()
                continue
            route = self.router.send("data", node_id, gateway_node)
            if route is not None:
                self.data_delivered += 1
                self.gateway_loads[gateway_node] += 1.0
                active_subnets.add(subnet_id)

        if not self.config.hierarchical_backhaul:
            return

        active_networks: set[str] = set()
        for subnet_id in sorted(active_subnets):
            subnet_gateway = self._gateway_node(subnet_id)
            network_id = self.topology.subnet_to_network[subnet_id]
            network_gateway = self._gateway_node(network_id)
            if subnet_gateway is None or network_gateway is None:
                self.router.record_unrouted_data("backhaul")
                continue
            if self.router.send("backhaul", subnet_gateway, network_gateway) is None:
                continue
            self.gateway_loads[network_gateway] += 1.0
            active_networks.add(network_id)

        for network_id in sorted(active_networks):
            network_gateway = self._gateway_node(network_id)
            internetwork_gateway = self._gateway_node("internetwork")
            if network_gateway is None or internetwork_gateway is None:
                self.router.record_unrouted_data("backhaul")
                continue
            if self.router.send("backhaul", network_gateway, internetwork_gateway) is not None:
                self.gateway_loads[internetwork_gateway] += 1.0

    def _gateway_node(self, scope: str) -> int | None:
        lease = self.protocol_engine.assignments.get(("gateway", scope))
        if lease is None or not self.protocol_engine.role_available("gateway", scope):
            return None
        return self.hierarchy.representative_node_id(lease.holder_id)

    def _apply_event(self, event: SimulationEvent, event_time: float) -> bool:
        changed = apply_event(event, self.hierarchy)
        if changed and event.kind == "recover":
            self._energy_depleted_node_ids.discard(event.node_id)
        if changed and event.kind in {"fail", "recover", "degrade_link"}:
            self.router.invalidate_graph()
        if changed and event.kind == "fail":
            self.node_failure_times[event.node_id] = event_time
        elif changed and event.kind == "recover":
            self.node_failure_times.pop(event.node_id, None)
        return changed

    def _fail_energy_empty_nodes(self, event_time: float) -> bool:
        changed = False
        for node_id, node in self.nodes_by_id.items():
            if node.is_available() and node.energy <= 0.0:
                node.fail()
                self.node_failure_times[node_id] = event_time
                self._energy_depleted_node_ids.add(node_id)
                self._mark_node_scopes_dirty(node_id)
                changed = True
        if changed:
            self.router.invalidate_graph()
        return changed

    def _mark_node_scopes_dirty(self, node_id: int) -> None:
        self._dirty_scope_ids.update(
            scope
            for scope in self.hierarchy.scope_ids
            if node_id in self.hierarchy.node_ids_for_entity(scope)
        )

    def _detect_material_capability_changes(self) -> None:
        if not self.config.reassess_affected_scopes_only:
            return
        threshold = self.config.capability_change_threshold
        if threshold == 0:
            return
        for node_id, node in self.nodes_by_id.items():
            for role, capability in node.capability_vector().items():
                key = (node_id, role)
                previous = self._node_capability_snapshot[key]
                if abs(capability - previous) >= threshold:
                    self._mark_node_scopes_dirty(node_id)
                    self._node_capability_snapshot[key] = capability

    def _apply_manual_event(self, kind: str, node_id: int, amount: float = 0.0) -> bool:
        event = SimulationEvent(max(1, int(self.steps)), node_id, kind, amount)
        return self._apply_event(event, float(self.steps))
