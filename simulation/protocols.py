"""Assignment policies for centralized and decentralized protocol variants."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import TYPE_CHECKING

from nodes import SUPPORTED_ROLES
from simulation.config import PROTOCOLS
from simulation.leases import Lease

if TYPE_CHECKING:
    from simulation.runner import RoleSimulationModel


MIGRATION_RECORD_COLUMNS = (
    "time",
    "role",
    "scope",
    "old_holder",
    "new_holder",
    "old_capability",
    "new_capability",
    "migration_cost",
    "old_utility",
    "new_utility",
)


@dataclass(frozen=True)
class MigrationCost:
    control_messages: float
    state_transfer: float
    energy_cost: float
    disruption: float


def calculate_migration_cost(model: RoleSimulationModel, old_holder: int | str, new_holder: int | str) -> float:
    """Evaluate the configured deterministic migration-cost equation."""
    old_node = model.hierarchy.representative_node_id(old_holder)
    new_node = model.hierarchy.representative_node_id(new_holder)
    if old_node is None or new_node is None:
        return inf
    route = model.router.find_route(old_node, new_node)
    if route is None:
        return inf
    config = model.config
    terms = MigrationCost(
        control_messages=2.0,
        state_transfer=config.migration_state_transfer,
        energy_cost=route.cost * config.control_energy_per_hop,
        disruption=config.migration_disruption,
    )
    return (
        config.migration_alpha * terms.control_messages
        + config.migration_beta * terms.state_transfer
        + config.migration_gamma * terms.energy_cost
        + config.migration_delta * terms.disruption
    )


class ProtocolEngine:
    """Owns leases and applies the selected policy to a shared simulation world."""

    def __init__(self, model: RoleSimulationModel, protocol: str) -> None:
        if protocol not in PROTOCOLS:
            raise ValueError(f"protocol must be one of {PROTOCOLS}")
        self.model = model
        self.protocol = protocol
        self.assignments: dict[tuple[str, str], Lease] = {}
        self.migration_records: list[dict[str, object]] = []
        self.recovery_times: list[float] = []
        self._pending_recovery: dict[tuple[str, str], float] = {}
        self._unavailability_start: dict[tuple[str, str], float] = {}
        self._failed_holders: dict[tuple[str, str], Lease] = {}
        self._observed_capabilities: dict[tuple[int | str, str], float] = {}
        self._last_migration_time: dict[tuple[str, str], int] = {}
        self.current_epoch = 1
        self._record_current_capabilities()
        self._initialize_assignments()

    def step(
        self,
        now: int,
        state_changed: bool = False,
        affected_scopes: frozenset[str] = frozenset(),
    ) -> None:
        if self.protocol == "static":
            return
        if self.protocol == "proposed" and now > 0 and now % self.model.config.epoch_length == 0:
            self._advance_epoch(now)
        if (
            self.protocol == "proposed"
            and self.model.config.capability_broadcast_interval_steps > 0
            and now > 0
            and now % self.model.config.capability_broadcast_interval_steps == 0
        ):
            self._broadcast_capabilities()
        if self.protocol == "proposed" and self.model.config.batch_control_updates:
            self._renew_due_batches(now)

        for role, scope in self.assignment_keys:
            key = (role, scope)
            lease = self.assignments.get(key)
            holder_available = lease is None or self.model.hierarchy.is_available(lease.holder_id)
            if lease is not None and not holder_available:
                recorded_failure_time = self.model.holder_unavailable_since(lease.holder_id)
                failure_time = self._unavailability_start.setdefault(
                    key,
                    float(now) if recorded_failure_time is None else recorded_failure_time,
                )
                if now - failure_time < self.model.config.detection_delay_steps:
                    continue
                self._pending_recovery.setdefault(key, failure_time)
            elif holder_available:
                self._unavailability_start.pop(key, None)

            if lease is not None and (
                lease.state != "active"
                or not holder_available
                or (self.protocol == "proposed" and lease.epoch != self.current_epoch)
            ):
                if self.protocol == "hierarchical" and not holder_available:
                    self._failed_holders[key] = lease
                self._invalidate(key, lease, now)
                lease = None
            elif lease is not None and lease.expiry_time <= now:
                lease.expire()
                del self.assignments[key]
                lease = None

            if lease is None:
                self._assign(role, scope, now)
                continue

            if self.protocol == "proposed":
                self._renew_if_due(key, lease, now)
                lease = self.assignments.get(key)
                if lease is None:
                    self._assign(role, scope, now)
                    continue
                if (
                    (
                        scope in affected_scopes
                        if self.model.config.reassess_affected_scopes_only
                        else state_changed
                    )
                    or now % self.model.config.capability_reassessment_interval_steps == 0
                ):
                    self._consider_cost_aware_migration(key, lease, now)
            elif self.protocol in {"centralized", "dynamic"}:
                self._consider_immediate_migration(key, lease, now)

    @property
    def assignment_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (role, scope)
            for scope in self.model.hierarchy.scope_ids
            for role in SUPPORTED_ROLES
        )

    def role_available(self, role: str, scope: str) -> bool:
        lease = self.assignments.get((role, scope))
        if lease is None or lease.state != "active":
            return False
        if not self.model.hierarchy.is_available(lease.holder_id):
            return False
        return (
            self.protocol not in {"centralized", "hierarchical"}
            or self.model.controller_available
        )

    def _initialize_assignments(self) -> None:
        for role, scope in self.assignment_keys:
            self._assign(role, scope, now=0)

    def _assign(self, role: str, scope: str, now: int) -> Lease | None:
        best = self._select_for_role(scope, role, now)
        if best is None:
            return None
        holder_id, capability = best
        route = self.model.control_exchange("LEASE_GRANT", scope, holder_id)
        if route is None:
            return None
        duration = self._lease_duration(capability)
        lease = Lease(
            role=role,
            scope=scope,
            holder_id=holder_id,
            epoch=self.current_epoch,
            start_time=float(now),
            duration=duration,
            expiry_time=now + duration,
            renewal_fraction=self.model.config.lease_renewal_fraction,
        )
        lease.activate_lease()
        self.assignments[(role, scope)] = lease
        failed_lease = self._failed_holders.pop((role, scope), None)
        if failed_lease is not None and failed_lease.holder_id != holder_id:
            old_capability = self.model.hierarchy.capability(failed_lease.holder_id, role)
            migration_cost = calculate_migration_cost(self.model, failed_lease.holder_id, holder_id)
            self.migration_records.append({
                "time": now,
                "role": role,
                "scope": scope,
                "old_holder": failed_lease.holder_id,
                "new_holder": holder_id,
                "old_capability": old_capability,
                "new_capability": capability,
                "migration_cost": migration_cost,
                "old_utility": old_capability,
                "new_utility": capability,
            })
        failure_time = self._pending_recovery.pop((role, scope), None)
        if failure_time is not None:
            self.recovery_times.append(float(now) - failure_time)
        return lease

    def _select_for_role(
        self,
        scope: str,
        role: str,
        now: int = 0,
    ) -> tuple[int | str, float] | None:
        source = self.model.control_source(scope)
        if source is None:
            return None
        candidates: list[tuple[int | str, float]] = []
        for candidate in self.model.hierarchy.scope_candidates[scope]:
            if not self.model.hierarchy.is_available(candidate):
                continue
            destination = self.model.hierarchy.representative_node_id(candidate)
            if destination is None or self.model.router.find_route(source, destination) is None:
                continue
            candidates.append((candidate, self._known_capability(candidate, role)))
        if not candidates:
            return None
        if self.protocol == "hierarchical":
            return self.model.random.choice(candidates)
        return max(candidates, key=lambda item: (item[1], str(item[0])))

    def _invalidate(self, key: tuple[str, str], lease: Lease, now: int) -> None:
        lease.invalidate_lease()
        self.assignments.pop(key, None)
        self._pending_recovery.setdefault(key, float(now))

    def _renew_if_due(self, key: tuple[str, str], lease: Lease, now: int) -> None:
        if self.model.config.batch_control_updates:
            return
        if now < lease.renewal_time:
            return
        if self.model.control_exchange("LEASE_RENEW", lease.scope, lease.holder_id) is None:
            self._invalidate(key, lease, now)
            return
        capability = self.model.hierarchy.capability(lease.holder_id, lease.role)
        lease.renew_period(now, self._lease_duration(capability))

    def _renew_due_batches(self, now: int) -> None:
        due_by_scope: dict[str, list[tuple[tuple[str, str], Lease]]] = {}
        for key, lease in self.assignments.items():
            if (
                lease.state == "active"
                and lease.expiry_time > now
                and lease.renewal_time <= now
                and self.model.hierarchy.is_available(lease.holder_id)
            ):
                due_by_scope.setdefault(lease.scope, []).append((key, lease))

        for scope, renewals in due_by_scope.items():
            holder_ids = tuple(dict.fromkeys(
                self.model.hierarchy.representative_node_id(lease.holder_id)
                for _, lease in renewals
            ))
            if None in holder_ids:
                delivered = False
            else:
                delivered = self.model.control_exchange_batch(
                    "LEASE_RENEW_BATCH",
                    scope,
                    tuple(node_id for node_id in holder_ids if node_id is not None),
                )
            for key, lease in renewals:
                if not delivered:
                    self._invalidate(key, lease, now)
                    continue
                capability = self.model.hierarchy.capability(lease.holder_id, lease.role)
                lease.renew_period(now, self._lease_duration(capability))

    def _advance_epoch(self, now: int) -> None:
        self.current_epoch += 1
        if self.model.config.retain_valid_leases_on_epoch:
            for lease in self.assignments.values():
                lease.epoch = self.current_epoch
            return
        for key, lease in tuple(self.assignments.items()):
            lease.invalidate_lease()
            del self.assignments[key]
            self._assign(key[0], key[1], now)

    def _record_current_capabilities(self) -> None:
        for scope, candidates in self.model.hierarchy.scope_candidates.items():
            for role in SUPPORTED_ROLES:
                for candidate in candidates:
                    self._observed_capabilities[(candidate, role)] = (
                        self.model.hierarchy.capability(candidate, role)
                    )

    def _broadcast_capabilities(self) -> None:
        for scope in self.model.hierarchy.scope_ids:
            source = self.model.hierarchy.representative_node_id(scope)
            if source is None:
                continue
            recipients = self.model.hierarchy.node_ids_for_entity(scope)
            if self.model.router.broadcast_control(source, recipients):
                for candidate in self.model.hierarchy.scope_candidates[scope]:
                    for role in SUPPORTED_ROLES:
                        self._observed_capabilities[(candidate, role)] = (
                            self.model.hierarchy.capability(candidate, role)
                        )

    def _known_capability(self, candidate: int | str, role: str) -> float:
        if self.model.config.capability_broadcast_interval_steps == 0:
            return self.model.hierarchy.capability(candidate, role)
        known = self._observed_capabilities.get((candidate, role))
        if known is not None:
            return known
        return self.model.hierarchy.capability(candidate, role)

    def _consider_immediate_migration(self, key: tuple[str, str], lease: Lease, now: int) -> None:
        best = self._select_for_role(lease.scope, lease.role, now)
        if best is None or best[0] == lease.holder_id:
            return
        self._migrate(key, lease, best[0], best[1], now, cost_aware=False)

    def _consider_cost_aware_migration(self, key: tuple[str, str], lease: Lease, now: int) -> None:
        last_migration = self._last_migration_time.get(key)
        if (
            self.model.config.migration_cooldown_steps > 0
            and last_migration is not None
            and now - last_migration < self.model.config.migration_cooldown_steps
        ):
            return
        current_capability = self._known_capability(lease.holder_id, lease.role)
        best_holder: int | str | None = None
        best_capability = current_capability
        best_utility = current_capability
        for candidate in self.model.hierarchy.scope_candidates[lease.scope]:
            if candidate == lease.holder_id or not self.model.hierarchy.is_available(candidate):
                continue
            cost = calculate_migration_cost(self.model, lease.holder_id, candidate)
            if cost == inf:
                continue
            capability = self._known_capability(candidate, lease.role)
            utility = capability - self.model.config.migration_weight * cost
            if utility > best_utility:
                best_holder, best_capability, best_utility = candidate, capability, utility
        hysteresis = self.model.config.hysteresis_delta
        if self.model.config.adaptive_hysteresis:
            mean_energy = sum(
                node.energy for node in self.model.hierarchy.nodes_by_id.values()
            ) / max(1, len(self.model.hierarchy.nodes_by_id))
            hysteresis += (1.0 - mean_energy) * 0.15
        if best_holder is not None and best_utility > current_capability + hysteresis:
            if self.model.config.solar_migration_gate and not self._solar_migration_is_worthwhile(
                lease.holder_id,
                best_holder,
                lease.scope,
                now,
            ):
                return
            self._migrate(key, lease, best_holder, best_capability, now, cost_aware=True)

    def _solar_migration_is_worthwhile(
        self,
        current_holder: int | str,
        candidate: int | str,
        scope: str,
        now: int,
    ) -> bool:
        config = self.model.config
        source = self.model.control_source(scope)
        destination = self.model.hierarchy.representative_node_id(candidate)
        if source is None or destination is None:
            return False
        route = self.model.router.find_route(source, destination)
        if route is None:
            return False
        migration_energy = self.model.router.estimate_route_energy("MIGRATE", route)
        energy_benefit = (
            self._projected_reserve_energy(candidate, now)
            - self._projected_reserve_energy(current_holder, now)
        )
        return energy_benefit > (
            migration_energy + config.solar_migration_safety_margin
        )

    def _projected_reserve_energy(self, holder_id: int | str, now: int) -> float:
        config = self.model.config
        node_ids = [
            node_id
            for node_id in self.model.hierarchy.node_ids_for_entity(holder_id)
            if self.model.nodes_by_id[node_id].is_available()
        ]
        if not node_ids:
            return 0.0
        elapsed = max(1, now)
        projected = []
        for node_id in node_ids:
            node = self.model.nodes_by_id[node_id]
            recent_consumption = (
                self.model.router.energy_consumed_by_node.get(node_id, 0.0) / elapsed
            )
            future_energy = node.energy + config.solar_decision_horizon_steps * (
                node.solar_harvest_rate - recent_consumption
            )
            bounded_energy = min(config.battery_capacity, max(0.0, future_energy))
            projected.append(max(0.0, bounded_energy - config.minimum_energy_reserve))
        return sum(projected) / len(projected)

    def _migrate(
        self,
        key: tuple[str, str],
        lease: Lease,
        new_holder: int | str,
        new_capability: float,
        now: int,
        cost_aware: bool,
    ) -> None:
        old_holder = lease.holder_id
        old_capability = self.model.hierarchy.capability(old_holder, lease.role)
        migration_cost = calculate_migration_cost(self.model, old_holder, new_holder)
        if migration_cost == inf:
            return
        if self.model.control_exchange("MIGRATE", lease.scope, new_holder) is None:
            return
        old_utility = old_capability
        new_utility = (
            new_capability - self.model.config.migration_weight * migration_cost
            if cost_aware else new_capability
        )
        lease.migrate_holder(
            new_holder,
            now=float(now),
            duration=self._lease_duration(new_capability),
            epoch=self.current_epoch,
        )
        self.migration_records.append({
            "time": now,
            "role": lease.role,
            "scope": lease.scope,
            "old_holder": old_holder,
            "new_holder": new_holder,
            "old_capability": old_capability,
            "new_capability": new_capability,
            "migration_cost": migration_cost,
            "old_utility": old_utility,
            "new_utility": new_utility,
        })
        self._last_migration_time[key] = now

    def _lease_duration(self, capability: float) -> float:
        config = self.model.config
        if self.protocol != "proposed":
            return float(config.steps + 1)
        return (
            config.lease_min_duration
            + capability * (config.lease_max_duration - config.lease_min_duration)
        )
