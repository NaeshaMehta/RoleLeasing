"""Deterministic logical placement and physical mesh construction."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt

import numpy as np

from simulation.config import SimulationConfig


@dataclass(frozen=True)
class NodeAttributes:
    energy: float
    health: float
    link_quality: float


@dataclass
class NetworkTopology:
    positions: dict[int, tuple[float, float]]
    attributes: dict[int, NodeAttributes]
    node_to_subnet: dict[int, str]
    subnet_to_network: dict[str, str]
    network_to_subnets: dict[str, tuple[str, ...]]
    adjacency: dict[int, dict[int, float]]
    centrality: dict[int, float]
    communication_range: float

    @property
    def node_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self.positions))

    @property
    def subnet_ids(self) -> tuple[str, ...]:
        return tuple(self.subnet_to_network)

    @property
    def network_ids(self) -> tuple[str, ...]:
        return tuple(self.network_to_subnets)


def create_topology(config: SimulationConfig) -> NetworkTopology:
    """Create a fixed-seed grid mesh, separate from logical membership."""
    rng = np.random.default_rng(config.seed)
    count = config.num_nodes
    columns = ceil(sqrt(count))
    positions: dict[int, tuple[float, float]] = {}
    attributes: dict[int, NodeAttributes] = {}
    node_to_subnet: dict[int, str] = {}
    subnet_to_network: dict[str, str] = {}
    network_to_subnets: dict[str, tuple[str, ...]] = {}

    node_id = 0
    for network_index, subnet_count in enumerate(config.subnet_counts):
        network_id = f"network_{network_index}"
        subnet_ids: list[str] = []
        for subnet_index in range(subnet_count):
            subnet_id = f"{network_id}_subnet_{subnet_index}"
            subnet_ids.append(subnet_id)
            subnet_to_network[subnet_id] = network_id
            for _ in range(config.nodes_per_subnet):
                node_to_subnet[node_id] = subnet_id
                node_id += 1
        network_to_subnets[network_id] = tuple(subnet_ids)

    subnet_nodes: dict[str, list[int]] = {subnet_id: [] for subnet_id in subnet_to_network}
    for node_id, subnet_id in node_to_subnet.items():
        subnet_nodes[subnet_id].append(node_id)
    subnet_grid_columns = ceil(sqrt(len(subnet_nodes)))
    local_columns = ceil(sqrt(config.nodes_per_subnet))
    local_rows = ceil(config.nodes_per_subnet / local_columns)
    local_spacing = min(config.grid_spacing * 0.5, config.communication_range / 3.0)
    cluster_width = (local_columns - 1) * local_spacing
    cluster_height = (local_rows - 1) * local_spacing
    cluster_gap = config.intercluster_gap_in_ranges * config.communication_range
    cluster_pitch_x = cluster_width + cluster_gap
    cluster_pitch_y = cluster_height + cluster_gap
    subnet_grid_positions = {
        subnet_id: divmod(index, subnet_grid_columns)
        for index, subnet_id in enumerate(subnet_nodes)
    }
    local_positions = {
        node_id: divmod(index, local_columns)
        for subnet_node_ids in subnet_nodes.values()
        for index, node_id in enumerate(subnet_node_ids)
    }

    for node_id in range(count):
        if config.intercluster_gap_in_ranges > 0:
            subnet_id = node_to_subnet[node_id]
            cluster_row, cluster_column = subnet_grid_positions[subnet_id]
            local_row, local_column = local_positions[node_id]
            jitter = local_spacing * config.position_jitter
            x = (
                cluster_column * cluster_pitch_x
                + local_column * local_spacing
                + rng.uniform(-jitter, jitter)
            )
            y = (
                cluster_row * cluster_pitch_y
                + local_row * local_spacing
                + rng.uniform(-jitter, jitter)
            )
        else:
            row, column = divmod(node_id, columns)
            jitter = config.grid_spacing * config.position_jitter
            x = column * config.grid_spacing + rng.uniform(-jitter, jitter)
            y = row * config.grid_spacing + rng.uniform(-jitter, jitter)
        positions[node_id] = (float(x), float(y))
        attributes[node_id] = NodeAttributes(
            energy=float(rng.uniform(*config.energy_range)),
            health=float(rng.uniform(*config.health_range)),
            link_quality=float(rng.uniform(*config.link_quality_range)),
        )

    adjacency: dict[int, dict[int, float]] = {node_id: {} for node_id in range(count)}
    for left in range(count):
        lx, ly = positions[left]
        for right in range(left + 1, count):
            rx, ry = positions[right]
            distance = float(np.hypot(lx - rx, ly - ry))
            if distance <= config.communication_range:
                quality = max(0.0, 1.0 - distance / config.communication_range)
                adjacency[left][right] = quality
                adjacency[right][left] = quality

    if config.intercluster_gap_in_ranges > 0:
        subnet_ids = tuple(subnet_nodes)
        for left_index, left_subnet in enumerate(subnet_ids):
            left_row, left_column = subnet_grid_positions[left_subnet]
            for right_subnet in subnet_ids[left_index + 1:]:
                right_row, right_column = subnet_grid_positions[right_subnet]
                if abs(left_row - right_row) + abs(left_column - right_column) != 1:
                    continue
                bridge_left, bridge_right, distance = min(
                    (
                        (
                            left_node,
                            right_node,
                            float(np.hypot(
                                positions[left_node][0] - positions[right_node][0],
                                positions[left_node][1] - positions[right_node][1],
                            )),
                        )
                        for left_node in subnet_nodes[left_subnet]
                        for right_node in subnet_nodes[right_subnet]
                    ),
                    key=lambda edge: edge[2],
                )
                quality = float(np.exp(-distance / config.communication_range)) * min(
                    attributes[bridge_left].link_quality,
                    attributes[bridge_right].link_quality,
                )
                if quality <= config.minimum_link_quality:
                    raise ValueError(
                        "intercluster gap produces unusable backhaul links; reduce "
                        "intercluster_gap_in_ranges or minimum_link_quality"
                    )
                adjacency[bridge_left][bridge_right] = quality
                adjacency[bridge_right][bridge_left] = quality

    max_degree = max((len(neighbors) for neighbors in adjacency.values()), default=0)
    centrality = {
        node: (len(neighbors) / max_degree if max_degree else 0.0)
        for node, neighbors in adjacency.items()
    }

    topology = NetworkTopology(
        positions=positions,
        attributes=attributes,
        node_to_subnet=node_to_subnet,
        subnet_to_network=subnet_to_network,
        network_to_subnets=network_to_subnets,
        adjacency=adjacency,
        centrality=centrality,
        communication_range=config.communication_range,
    )
    if count > 1 and not _is_connected(topology.adjacency):
        raise RuntimeError("Generated physical mesh is disconnected")
    return topology


def _is_connected(adjacency: dict[int, dict[int, float]]) -> bool:
    if not adjacency:
        return True
    visited = {next(iter(adjacency))}
    stack = list(visited)
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                stack.append(neighbor)
    return len(visited) == len(adjacency)
