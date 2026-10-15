"""Explicit assumptions for the packet experiment (time is in seconds)."""

from dataclasses import dataclass
from math import isfinite

PROTOCOLS = ("static", "dynamic", "proposed")
SCENARIOS = ("normal", "node_failures", "energy_degradation", "link_degradation")

# Same role weights as nodes.py, without requiring Mesa for this standalone study.
ROLE_WEIGHTS = {
    "gateway": {"energy": 0.40, "link_quality": 0.35, "centrality": 0.25},
    "anomaly_detection": {"energy": 0.50, "health": 0.50},
    "health_monitoring": {"energy": 0.50, "health": 0.50},
    "discoverability": {"energy": 0.34, "link_quality": 0.33, "health": 0.33},
}


@dataclass(frozen=True)
class PacketConfig:
    duration_s: float = 30.0
    subnet_counts: tuple[int, ...] = (4, 3, 3)
    nodes_per_subnet: int = 10
    packet_interval_s: float = 5.0
    packet_size_bytes: int = 256
    bandwidth_bps: float = 64000.0
    propagation_s: float = 0.002
    queue_capacity: int = 12  # waiting packets, excluding one in service
    evaluation_s: float = 1.0
    detection_s: float = 2.0
    sample_s: float = 1.0
    summary_s: float = 10.0
    epoch_s: float = 20.0
    lease_min_s: float = 10.0
    lease_max_s: float = 30.0
    renewal_fraction: float = 0.7
    capability_epsilon: float = 0.02
    migration_weight: float = 0.1
    hysteresis_delta: float = 0.05
    migration_alpha: float = 0.01
    migration_beta: float = 0.1
    migration_gamma: float = 10.0
    migration_delta: float = 0.2
    state_transfer: float = 0.25
    disruption: float = 0.25
    tx_energy_per_byte: float = 0.00000008
    rx_energy_per_byte: float = 0.00000004
    minimum_active_fraction: float = 0.5
    base_link_loss: float = 0.005
    quality_loss_weight: float = 0.08

    @property
    def num_nodes(self):
        return sum(self.subnet_counts) * self.nodes_per_subnet

    def __post_init__(self):
        positive = ("duration_s", "packet_interval_s", "bandwidth_bps", "evaluation_s",
                    "sample_s", "summary_s", "epoch_s", "lease_min_s", "lease_max_s")
        for key in positive:
            if not isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive and finite")
        for key in ("propagation_s", "detection_s", "capability_epsilon", "migration_weight",
                    "hysteresis_delta", "migration_alpha", "migration_beta", "migration_gamma",
                    "migration_delta", "state_transfer", "disruption", "tx_energy_per_byte",
                    "rx_energy_per_byte", "base_link_loss", "quality_loss_weight"):
            if not isfinite(getattr(self, key)) or getattr(self, key) < 0:
                raise ValueError(f"{key} must be nonnegative and finite")
        if not self.subnet_counts or any(type(n) is not int or n < 1 for n in self.subnet_counts):
            raise ValueError("subnet_counts must contain positive integers")
        if type(self.nodes_per_subnet) is not int or self.nodes_per_subnet < 1:
            raise ValueError("nodes_per_subnet must be a positive integer")
        if type(self.queue_capacity) is not int or self.queue_capacity < 0:
            raise ValueError("queue_capacity must be a nonnegative integer")
        if type(self.packet_size_bytes) is not int or self.packet_size_bytes < 1:
            raise ValueError("packet_size_bytes must be a positive integer")
        if self.lease_max_s < self.lease_min_s:
            raise ValueError("lease_max_s must be >= lease_min_s")
        if not 0 < self.renewal_fraction < 1 or not 0 < self.minimum_active_fraction <= 1:
            raise ValueError("renewal_fraction and minimum_active_fraction out of range")
        if self.base_link_loss + self.quality_loss_weight > 1:
            raise ValueError("maximum packet loss probability must be <= 1")
