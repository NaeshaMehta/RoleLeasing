"""Pure, deterministic role capability and recursive aggregation functions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from nodes import ROLE_WEIGHTS, SUPPORTED_ROLES
from simulation.entities import EntityHierarchy

EntityId = TypeVar("EntityId", int, str)


def weighted_aggregate(
    child_vectors: Mapping[EntityId, Mapping[str, float]],
    weights: Mapping[EntityId, float] | None = None,
) -> dict[str, float]:
    """Aggregate role vectors with normalized weights; absent weights are uniform."""
    if not child_vectors:
        return {role: 0.0 for role in SUPPORTED_ROLES}

    ordered_ids = sorted(child_vectors, key=str)
    selected_weights = {child_id: (weights or {}).get(child_id, 1.0) for child_id in ordered_ids}
    if any(weight < 0 for weight in selected_weights.values()):
        raise ValueError("aggregation weights must be non-negative")
    denominator = sum(selected_weights.values())
    if denominator <= 0:
        raise ValueError("aggregation weights must have a positive total")

    result: dict[str, float] = {}
    for role in SUPPORTED_ROLES:
        values = [child_vectors[child_id].get(role, 0.0) for child_id in ordered_ids]
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"child capability for {role} must be within [0, 1]")
        result[role] = sum(
            selected_weights[child_id] * child_vectors[child_id].get(role, 0.0)
            for child_id in ordered_ids
        ) / denominator
    return result


def refresh_capabilities(
    hierarchy: EntityHierarchy,
    child_weights: Mapping[str, Mapping[int | str, float]] | None = None,
) -> None:
    """Recompute all capability vectors from leaves to root without hidden state."""
    weights = child_weights or {}
    node_vectors = {
        node_id: node.capability_vector()
        for node_id, node in hierarchy.nodes_by_id.items()
    }
    for subnet_id, subnet in hierarchy.subnets.items():
        subnet.capabilities = weighted_aggregate(
            {node_id: node_vectors[node_id] for node_id in subnet.node_ids},
            weights.get(subnet_id),
        )
    for network_id, network in hierarchy.networks.items():
        network.capabilities = weighted_aggregate(
            {subnet_id: hierarchy.subnets[subnet_id].capabilities for subnet_id in network.subnet_ids},
            weights.get(network_id),
        )
    hierarchy.internetwork.capabilities = weighted_aggregate(
        {
            network_id: hierarchy.networks[network_id].capabilities
            for network_id in hierarchy.internetwork.network_ids
        },
        weights.get(hierarchy.internetwork.entity_id),
    )


def role_weights(role: str) -> Mapping[str, float]:
    """Expose the node-level weight definition without duplicating its source."""
    try:
        return ROLE_WEIGHTS[role]
    except KeyError as exc:
        raise ValueError(f"Unsupported role {role!r}") from exc
