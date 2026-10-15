"""Mesa agents for nodes and the logical hierarchy."""

from __future__ import annotations

from dataclasses import dataclass

import mesa

from nodes import NodeAgent
from simulation.topology import NetworkTopology


class SubnetAgent(mesa.Agent):
    def __init__(self, model: mesa.Model, subnet_id: str, network_id: str, node_ids: tuple[int, ...]):
        super().__init__(model)
        self.entity_id = subnet_id
        self.network_id = network_id
        self.node_ids = node_ids
        self.capabilities: dict[str, float] = {}


class NetworkAgent(mesa.Agent):
    def __init__(self, model: mesa.Model, network_id: str, subnet_ids: tuple[str, ...]):
        super().__init__(model)
        self.entity_id = network_id
        self.subnet_ids = subnet_ids
        self.capabilities: dict[str, float] = {}


class InternetworkAgent(mesa.Agent):
    def __init__(self, model: mesa.Model, network_ids: tuple[str, ...]):
        super().__init__(model)
        self.entity_id = "internetwork"
        self.network_ids = network_ids
        self.capabilities: dict[str, float] = {}


@dataclass
class EntityHierarchy:
    nodes_by_id: dict[int, NodeAgent]
    subnets: dict[str, SubnetAgent]
    networks: dict[str, NetworkAgent]
    internetwork: InternetworkAgent
    scope_candidates: dict[str, tuple[int | str, ...]]
    entity_node_ids: dict[str, tuple[int, ...]]

    @property
    def scope_ids(self) -> tuple[str, ...]:
        return tuple(self.scope_candidates)

    def entity(self, entity_id: int | str) -> NodeAgent | SubnetAgent | NetworkAgent | InternetworkAgent:
        if isinstance(entity_id, int):
            return self.nodes_by_id[entity_id]
        if entity_id == self.internetwork.entity_id:
            return self.internetwork
        if entity_id in self.subnets:
            return self.subnets[entity_id]
        return self.networks[entity_id]

    def node_ids_for_entity(self, entity_id: int | str) -> tuple[int, ...]:
        if isinstance(entity_id, int):
            return (entity_id,)
        return self.entity_node_ids[entity_id]

    def is_available(self, entity_id: int | str) -> bool:
        return any(self.nodes_by_id[node_id].is_available() for node_id in self.node_ids_for_entity(entity_id))

    def representative_node_id(self, entity_id: int | str) -> int | None:
        return next(
            (
                node_id for node_id in self.node_ids_for_entity(entity_id)
                if self.nodes_by_id[node_id].is_available()
            ),
            None,
        )

    def capability(self, entity_id: int | str, role: str) -> float:
        entity = self.entity(entity_id)
        if isinstance(entity, NodeAgent):
            return entity.capability(role)
        return entity.capabilities.get(role, 0.0)


def build_hierarchy(
    model: mesa.Model,
    topology: NetworkTopology,
    battery_capacity: float = 1.0,
) -> EntityHierarchy:
    """Create Mesa agents matching the topology's independent logical hierarchy."""
    nodes_by_id: dict[int, NodeAgent] = {}
    for node_id in topology.node_ids:
        subnet_id = topology.node_to_subnet[node_id]
        node = NodeAgent(model, subnet_id=subnet_id)
        attrs = topology.attributes[node_id]
        node.node_id = node_id
        node.network_id = topology.subnet_to_network[subnet_id]
        node.position = topology.positions[node_id]
        node.energy_capacity = battery_capacity
        node.energy = attrs.energy
        node.health = attrs.health
        node.link_quality = attrs.link_quality
        node.centrality = topology.centrality[node_id]
        nodes_by_id[node_id] = node

    node_lists: dict[str, list[int]] = {subnet_id: [] for subnet_id in topology.subnet_ids}
    for node_id, subnet_id in topology.node_to_subnet.items():
        node_lists[subnet_id].append(node_id)
    subnets = {
        subnet_id: SubnetAgent(
            model,
            subnet_id,
            topology.subnet_to_network[subnet_id],
            tuple(node_lists[subnet_id]),
        )
        for subnet_id in topology.subnet_ids
    }
    networks = {
        network_id: NetworkAgent(model, network_id, subnet_ids)
        for network_id, subnet_ids in topology.network_to_subnets.items()
    }
    internetwork = InternetworkAgent(model, topology.network_ids)

    scope_candidates: dict[str, tuple[int | str, ...]] = {}
    for subnet_id, subnet in subnets.items():
        scope_candidates[subnet_id] = subnet.node_ids
    for network_id, network in networks.items():
        scope_candidates[network_id] = network.subnet_ids
    scope_candidates[internetwork.entity_id] = internetwork.network_ids

    entity_node_ids: dict[str, tuple[int, ...]] = {
        subnet_id: subnet.node_ids for subnet_id, subnet in subnets.items()
    }
    for network_id, network in networks.items():
        entity_node_ids[network_id] = tuple(
            node_id for subnet_id in network.subnet_ids for node_id in subnets[subnet_id].node_ids
        )
    entity_node_ids[internetwork.entity_id] = tuple(topology.node_ids)

    return EntityHierarchy(
        nodes_by_id=nodes_by_id,
        subnets=subnets,
        networks=networks,
        internetwork=internetwork,
        scope_candidates=scope_candidates,
        entity_node_ids=entity_node_ids,
    )
