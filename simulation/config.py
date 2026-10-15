"""Validated configuration and metric semantics for a simulation run."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


PROTOCOLS = ("centralized", "hierarchical", "static", "dynamic", "proposed")
SCENARIOS = ("normal", "node_failures", "energy_degradation", "link_degradation")


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 42
    subnet_counts: tuple[int, ...] = (4, 3, 3)
    nodes_per_subnet: int = 10
    steps: int = 100
    communication_range: float = 5.2
    grid_spacing: float = 4.0
    position_jitter: float = 0.1
    intercluster_gap_in_ranges: float = 0.0
    distance_energy_weight: float = 0.0
    distance_energy_exponent: float = 2.0
    hierarchical_backhaul: bool = False
    epoch_length: int = 20
    retain_valid_leases_on_epoch: bool = False
    capability_reassessment_interval_steps: int = 1
    reassess_affected_scopes_only: bool = False
    capability_change_threshold: float = 0.02
    capability_broadcast_interval_steps: int = 0
    migration_cooldown_steps: int = 0
    adaptive_hysteresis: bool = False
    batch_control_updates: bool = False
    detection_delay_steps: int = 0
    lease_min_duration: float = 10.0
    lease_max_duration: float = 100.0
    lease_renewal_fraction: float = 0.7
    migration_weight: float = 0.1
    hysteresis_delta: float = 0.05
    minimum_active_fraction: float = 0.5
    data_energy_per_hop: float = 0.00005
    control_energy_per_hop: float = 0.00001
    battery_capacity: float = 1.0
    solar_harvest_rate: float = 0.0
    solar_migration_gate: bool = False
    minimum_energy_reserve: float = 0.1
    solar_decision_horizon_steps: int = 500
    solar_migration_safety_margin: float = 0.01
    minimum_link_quality: float = 0.02
    energy_range: tuple[float, float] = (0.75, 1.0)
    health_range: tuple[float, float] = (0.8, 1.0)
    link_quality_range: tuple[float, float] = (0.75, 1.0)
    migration_alpha: float = 0.01
    migration_beta: float = 0.1
    migration_gamma: float = 10.0
    migration_delta: float = 0.2
    migration_state_transfer: float = 0.25
    migration_disruption: float = 0.25

    def __post_init__(self) -> None:
        if not self.subnet_counts or any(
            not isinstance(count, int) or isinstance(count, bool) or count <= 0
            for count in self.subnet_counts
        ):
            raise ValueError("subnet_counts must contain positive counts")
        if (
            not isinstance(self.nodes_per_subnet, int)
            or isinstance(self.nodes_per_subnet, bool)
            or self.nodes_per_subnet <= 0
        ):
            raise ValueError("nodes_per_subnet must be positive")
        if not isinstance(self.steps, int) or isinstance(self.steps, bool) or self.steps <= 0:
            raise ValueError("steps must be positive")
        finite_values = (
            self.communication_range,
            self.grid_spacing,
            self.position_jitter,
            self.intercluster_gap_in_ranges,
            self.distance_energy_weight,
            self.distance_energy_exponent,
            self.lease_min_duration,
            self.lease_max_duration,
            self.migration_weight,
            self.hysteresis_delta,
            self.capability_change_threshold,
            self.minimum_active_fraction,
            self.data_energy_per_hop,
            self.control_energy_per_hop,
            self.battery_capacity,
            self.solar_harvest_rate,
            self.minimum_energy_reserve,
            self.solar_migration_safety_margin,
            self.minimum_link_quality,
            self.migration_alpha,
            self.migration_beta,
            self.migration_gamma,
            self.migration_delta,
            self.migration_state_transfer,
            self.migration_disruption,
        )
        if not all(isfinite(value) for value in finite_values):
            raise ValueError("configuration numeric values must be finite")
        if self.communication_range <= 0 or self.grid_spacing <= 0:
            raise ValueError("communication_range and grid_spacing must be positive")
        if self.position_jitter < 0 or self.position_jitter >= 0.5:
            raise ValueError("position_jitter must be in [0, 0.5)")
        if self.intercluster_gap_in_ranges < 0:
            raise ValueError("intercluster_gap_in_ranges must be non-negative")
        if self.distance_energy_weight < 0 or self.distance_energy_exponent <= 0:
            raise ValueError("distance energy weight must be non-negative and exponent positive")
        if not isinstance(self.hierarchical_backhaul, bool):
            raise ValueError("hierarchical_backhaul must be a boolean")
        if not isinstance(self.retain_valid_leases_on_epoch, bool):
            raise ValueError("retain_valid_leases_on_epoch must be a boolean")
        if not isinstance(self.reassess_affected_scopes_only, bool):
            raise ValueError("reassess_affected_scopes_only must be a boolean")
        if not isinstance(self.adaptive_hysteresis, bool):
            raise ValueError("adaptive_hysteresis must be a boolean")
        if not isinstance(self.batch_control_updates, bool):
            raise ValueError("batch_control_updates must be a boolean")
        if not isinstance(self.solar_migration_gate, bool):
            raise ValueError("solar_migration_gate must be a boolean")
        if self.communication_range < self.grid_spacing * (1 + 2 * self.position_jitter):
            raise ValueError("communication_range is too small to preserve grid connectivity")
        if (
            not isinstance(self.epoch_length, int)
            or isinstance(self.epoch_length, bool)
            or self.epoch_length <= 0
        ):
            raise ValueError("epoch_length must be positive")
        if (
            not isinstance(self.capability_reassessment_interval_steps, int)
            or isinstance(self.capability_reassessment_interval_steps, bool)
            or self.capability_reassessment_interval_steps <= 0
        ):
            raise ValueError("capability_reassessment_interval_steps must be positive")
        if not 0 <= self.capability_change_threshold <= 1:
            raise ValueError("capability_change_threshold must be in [0, 1]")
        if (
            not isinstance(self.capability_broadcast_interval_steps, int)
            or isinstance(self.capability_broadcast_interval_steps, bool)
            or self.capability_broadcast_interval_steps < 0
        ):
            raise ValueError("capability_broadcast_interval_steps must be non-negative")
        if (
            not isinstance(self.migration_cooldown_steps, int)
            or isinstance(self.migration_cooldown_steps, bool)
            or self.migration_cooldown_steps < 0
        ):
            raise ValueError("migration_cooldown_steps must be non-negative")
        if (
            not isinstance(self.detection_delay_steps, int)
            or isinstance(self.detection_delay_steps, bool)
            or self.detection_delay_steps < 0
        ):
            raise ValueError("detection_delay_steps must be non-negative")
        if self.lease_min_duration <= 0 or self.lease_max_duration < self.lease_min_duration:
            raise ValueError("lease durations must be positive and max >= min")
        if not 0 < self.battery_capacity <= 1:
            raise ValueError("battery_capacity must be within (0, 1]")
        if self.solar_harvest_rate < 0:
            raise ValueError("solar_harvest_rate must be non-negative")
        if not 0 <= self.minimum_energy_reserve < self.battery_capacity:
            raise ValueError("minimum_energy_reserve must be within the battery capacity")
        if (
            not isinstance(self.solar_decision_horizon_steps, int)
            or isinstance(self.solar_decision_horizon_steps, bool)
            or self.solar_decision_horizon_steps <= 0
        ):
            raise ValueError("solar_decision_horizon_steps must be positive")
        if self.solar_migration_safety_margin < 0:
            raise ValueError("solar_migration_safety_margin must be non-negative")
        if not 0 < self.lease_renewal_fraction < 1:
            raise ValueError("lease_renewal_fraction must be in (0, 1)")
        if not 0 < self.minimum_active_fraction <= 1:
            raise ValueError("minimum_active_fraction must be in (0, 1]")
        if not 0 <= self.minimum_link_quality < 1:
            raise ValueError("minimum_link_quality must be in [0, 1)")
        if not 0 <= self.hysteresis_delta:
            raise ValueError("hysteresis_delta must be non-negative")
        if self.migration_weight < 0:
            raise ValueError("migration_weight must be non-negative")
        if any(value < 0 for value in (
            self.data_energy_per_hop,
            self.control_energy_per_hop,
            self.migration_alpha,
            self.migration_beta,
            self.migration_gamma,
            self.migration_delta,
            self.migration_state_transfer,
            self.migration_disruption,
        )):
            raise ValueError("energy costs and migration-cost terms must be non-negative")
        for name, bounds in (
            ("energy_range", self.energy_range),
            ("health_range", self.health_range),
            ("link_quality_range", self.link_quality_range),
        ):
            low, high = bounds
            if not all(isfinite(value) for value in bounds) or not 0 <= low <= high <= 1:
                raise ValueError(f"{name} must be an ordered pair within [0, 1]")
        if self.energy_range[1] > self.battery_capacity:
            raise ValueError("energy_range cannot exceed battery_capacity")

    @property
    def num_networks(self) -> int:
        return len(self.subnet_counts)

    @property
    def num_subnets(self) -> int:
        return sum(self.subnet_counts)

    @property
    def num_nodes(self) -> int:
        return self.num_subnets * self.nodes_per_subnet

    @property
    def total_role_scopes(self) -> int:
        return self.num_subnets + self.num_networks + 1
