"""Deterministic shortest-path routing and abstract communication accounting."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

from simulation.config import SimulationConfig
from simulation.entities import EntityHierarchy
from simulation.topology import NetworkTopology


@dataclass(frozen=True)
class RouteResult:
    source: int
    destination: int
    path: tuple[int, ...]
    cost: float
    bottleneck_quality: float

    @property
    def hops(self) -> int:
        return max(0, len(self.path) - 1)


class NetworkRouter:
    """Routes over the physical mesh; logical hierarchy does not create links."""

    LINK_QUALITY_PENALTY = 4.0

    def __init__(
        self,
        topology: NetworkTopology,
        hierarchy: EntityHierarchy,
        config: SimulationConfig,
    ) -> None:
        self.topology = topology
        self.hierarchy = hierarchy
        self.config = config
        self.control_messages = 0
        self.data_messages = 0
        self.message_hop_transmissions = 0
        self.data_hop_transmissions = 0
        self.cumulative_route_cost = 0.0
        self.failed_deliveries = 0
        self.delivered_data_messages = 0
        self._step_control_messages = 0
        self._step_data_messages = 0
        self._step_message_hops = 0
        self._step_data_hops = 0
        self._step_route_cost = 0.0
        self._step_failed_deliveries = 0
        self._step_delivered_data = 0
        self.energy_consumed_by_node: dict[int, float] = {}
        self.energy_consumed_by_node_step: dict[int, float] = {}
        self.data_energy_consumed = 0.0
        self.control_energy_consumed = 0.0
        self.data_energy_consumed_step = 0.0
        self.control_energy_consumed_step = 0.0
        self.backhaul_messages = 0
        self.backhaul_hop_transmissions = 0
        self._step_backhaul_messages = 0
        self._step_backhaul_hops = 0
        self.sensor_data_messages = 0
        self.sensor_data_delivered = 0
        self._step_sensor_messages = 0
        self._step_sensor_delivered = 0
        self._graph_cache: dict[int, dict[int, tuple[float, float]]] | None = None
        self._routes_cache: dict[int, dict[int, RouteResult]] = {}
        self._base_edges = {
            (left, right): quality
            for left, neighbors in topology.adjacency.items()
            for right, quality in neighbors.items()
            if left < right
        }

    def begin_step(self) -> None:
        self._step_control_messages = 0
        self._step_data_messages = 0
        self._step_message_hops = 0
        self._step_data_hops = 0
        self._step_route_cost = 0.0
        self._step_failed_deliveries = 0
        self._step_delivered_data = 0
        self.energy_consumed_by_node_step = {}
        self.data_energy_consumed_step = 0.0
        self.control_energy_consumed_step = 0.0
        self._step_backhaul_messages = 0
        self._step_backhaul_hops = 0
        self._step_sensor_messages = 0
        self._step_sensor_delivered = 0

    def invalidate_graph(self) -> None:
        self._graph_cache = None
        self._routes_cache.clear()

    def find_route(self, source: int, destination: int) -> RouteResult | None:
        if source not in self.hierarchy.nodes_by_id or destination not in self.hierarchy.nodes_by_id:
            raise ValueError("route endpoints must be node IDs in this simulation")
        if not self.hierarchy.nodes_by_id[source].is_available():
            return None
        if not self.hierarchy.nodes_by_id[destination].is_available():
            return None
        if source == destination:
            return RouteResult(source, destination, (source,), 0.0, 1.0)

        return self._routes_from(source).get(destination)

    def _routes_from(self, source: int) -> dict[int, RouteResult]:
        cached = self._routes_cache.get(source)
        if cached is not None:
            return cached
        graph = self._current_graph()
        distances = {source: 0.0}
        previous: dict[int, int] = {}
        queue: list[tuple[float, int]] = [(0.0, source)]
        while queue:
            distance, current = heappop(queue)
            if distance > distances.get(current, float("inf")):
                continue
            for neighbor, (edge_cost, _) in sorted(graph.get(current, {}).items()):
                candidate = distance + edge_cost
                if candidate < distances.get(neighbor, float("inf")) - 1e-12:
                    distances[neighbor] = candidate
                    previous[neighbor] = current
                    heappush(queue, (candidate, neighbor))

        routes: dict[int, RouteResult] = {}
        for destination, cost in distances.items():
            if destination == source:
                routes[destination] = RouteResult(source, destination, (source,), 0.0, 1.0)
                continue
            path = [destination]
            while path[-1] != source:
                path.append(previous[path[-1]])
            path.reverse()
            qualities = [
                graph[left][right][1]
                for left, right in zip(path, path[1:])
            ]
            routes[destination] = RouteResult(
                source=source,
                destination=destination,
                path=tuple(path),
                cost=cost,
                bottleneck_quality=min(qualities, default=1.0),
            )
        self._routes_cache[source] = routes
        return routes

    def send(self, kind: str, source: int, destination: int) -> RouteResult | None:
        """Count one abstract message and its routed transmissions, if delivered."""
        is_data = kind in {"data", "backhaul"}
        if is_data:
            self.data_messages += 1
            self._step_data_messages += 1
            if kind == "backhaul":
                self.backhaul_messages += 1
                self._step_backhaul_messages += 1
            else:
                self.sensor_data_messages += 1
                self._step_sensor_messages += 1
        else:
            self.control_messages += 1
            self._step_control_messages += 1
        route = self.find_route(source, destination)
        if route is None:
            self.failed_deliveries += 1
            self._step_failed_deliveries += 1
            return None

        self.message_hop_transmissions += route.hops
        self._step_message_hops += route.hops
        self.cumulative_route_cost += route.cost
        self._step_route_cost += route.cost
        if is_data:
            self.data_hop_transmissions += route.hops
            self._step_data_hops += route.hops
            self.delivered_data_messages += 1
            self._step_delivered_data += 1
            if kind == "backhaul":
                self.backhaul_hop_transmissions += route.hops
                self._step_backhaul_hops += route.hops
            else:
                self.sensor_data_delivered += 1
                self._step_sensor_delivered += 1
        self._charge_energy(kind, route.path)
        return route

    def broadcast_control(self, source: int, recipients: tuple[int, ...]) -> bool:
        """Flood one control message over a deterministic tree of the scope graph."""
        self.control_messages += 1
        self._step_control_messages += 1
        if source not in self.hierarchy.nodes_by_id:
            raise ValueError("broadcast source must be a node ID in this simulation")
        if not self.hierarchy.nodes_by_id[source].is_available():
            self.failed_deliveries += 1
            self._step_failed_deliveries += 1
            return False

        graph = self._current_graph()
        eligible = {
            node_id for node_id in recipients
            if self.hierarchy.nodes_by_id[node_id].is_available()
        }
        if source not in eligible:
            self.failed_deliveries += 1
            self._step_failed_deliveries += 1
            return False

        visited = {source}
        frontier = [source]
        tree_edges: list[tuple[int, int]] = []
        while frontier:
            current = frontier.pop(0)
            for neighbor in sorted(graph[current]):
                if neighbor in eligible and neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append(neighbor)
                    tree_edges.append((current, neighbor))

        self.message_hop_transmissions += len(tree_edges)
        self._step_message_hops += len(tree_edges)
        for sender, receiver in tree_edges:
            edge_cost, _ = graph[sender][receiver]
            self.cumulative_route_cost += edge_cost
            self._step_route_cost += edge_cost
            self._charge_energy("CAPABILITY_BROADCAST", (sender, receiver))

        delivered = eligible.issubset(visited)
        if not delivered:
            self.failed_deliveries += 1
            self._step_failed_deliveries += 1
        return delivered

    def send_control_batch(
        self,
        source: int | None,
        destinations: tuple[int, ...],
    ) -> bool:
        """Send one logical control message over the union of destination routes."""
        self.control_messages += 1
        self._step_control_messages += 1
        if source is None:
            self.failed_deliveries += 1
            self._step_failed_deliveries += 1
            return False
        routes = [self.find_route(source, destination) for destination in sorted(set(destinations))]
        if not routes or any(route is None for route in routes):
            self.failed_deliveries += 1
            self._step_failed_deliveries += 1
            return False

        edges = {
            (min(sender, receiver), max(sender, receiver))
            for route in routes
            if route is not None
            for sender, receiver in zip(route.path, route.path[1:])
        }
        for left, right in sorted(edges):
            edge_cost, _ = self._current_graph()[left][right]
            self.message_hop_transmissions += 1
            self._step_message_hops += 1
            self.cumulative_route_cost += edge_cost
            self._step_route_cost += edge_cost
            self._charge_energy("LEASE_RENEW_BATCH", (left, right))
        return True

    def record_unrouted_data(self, kind: str = "data") -> None:
        """Count an offered sensor message that had no usable gateway destination."""
        self.data_messages += 1
        self._step_data_messages += 1
        if kind == "backhaul":
            self.backhaul_messages += 1
            self._step_backhaul_messages += 1
        else:
            self.sensor_data_messages += 1
            self._step_sensor_messages += 1
        self.failed_deliveries += 1
        self._step_failed_deliveries += 1

    def step_metrics(self) -> dict[str, int | float]:
        return {
            "control_messages_step": self._step_control_messages,
            "data_messages_step": self._step_data_messages,
            "message_hop_transmissions_step": self._step_message_hops,
            "data_hop_transmissions_step": self._step_data_hops,
            "route_cost_step": self._step_route_cost,
            "failed_deliveries_step": self._step_failed_deliveries,
            "delivered_data_messages_step": self._step_delivered_data,
            "backhaul_messages_step": self._step_backhaul_messages,
            "backhaul_hop_transmissions_step": self._step_backhaul_hops,
            "sensor_data_messages_step": self._step_sensor_messages,
            "sensor_data_delivered_step": self._step_sensor_delivered,
            "data_energy_consumed_step": self.data_energy_consumed_step,
            "control_energy_consumed_step": self.control_energy_consumed_step,
        }

    def _current_graph(self) -> dict[int, dict[int, tuple[float, float]]]:
        if self._graph_cache is not None:
            return self._graph_cache
        graph: dict[int, dict[int, tuple[float, float]]] = {
            node_id: {} for node_id in self.hierarchy.nodes_by_id
        }
        for (left, right), geometric_quality in self._base_edges.items():
            left_node = self.hierarchy.nodes_by_id[left]
            right_node = self.hierarchy.nodes_by_id[right]
            if not left_node.is_available() or not right_node.is_available():
                continue
            quality = geometric_quality * min(left_node.link_quality, right_node.link_quality)
            if quality <= self.config.minimum_link_quality:
                continue
            cost = 1.0 + self.LINK_QUALITY_PENALTY * (1.0 - quality)
            graph[left][right] = (cost, quality)
            graph[right][left] = (cost, quality)
        self._graph_cache = graph
        return self._graph_cache

    def _charge_energy(self, kind: str, path: tuple[int, ...]) -> None:
        for sender, receiver in zip(path, path[1:]):
            sender_energy, receiver_energy = self._hop_energy_cost(
                kind,
                sender,
                receiver,
            )
            self.hierarchy.nodes_by_id[sender].degrade_energy(sender_energy)
            self.hierarchy.nodes_by_id[receiver].degrade_energy(receiver_energy)
            self._record_energy(kind, sender, sender_energy)
            self._record_energy(kind, receiver, receiver_energy)

    def estimate_route_energy(self, kind: str, route: RouteResult) -> float:
        """Estimate the exact communication energy charged for this routed message."""
        return sum(
            sum(self._hop_energy_cost(kind, sender, receiver))
            for sender, receiver in zip(route.path, route.path[1:])
        )

    def _hop_energy_cost(self, kind: str, sender: int, receiver: int) -> tuple[float, float]:
        per_endpoint = (
            self.config.data_energy_per_hop
            if kind in {"data", "backhaul"}
            else self.config.control_energy_per_hop
        )
        sender_position = self.topology.positions[sender]
        receiver_position = self.topology.positions[receiver]
        distance = (
            (sender_position[0] - receiver_position[0]) ** 2
            + (sender_position[1] - receiver_position[1]) ** 2
        ) ** 0.5
        distance_multiplier = 1.0 + self.config.distance_energy_weight * (
            distance / self.config.communication_range
        ) ** self.config.distance_energy_exponent
        return per_endpoint * distance_multiplier, per_endpoint

    def _record_energy(self, kind: str, node_id: int, amount: float) -> None:
        self.energy_consumed_by_node[node_id] = (
            self.energy_consumed_by_node.get(node_id, 0.0) + amount
        )
        self.energy_consumed_by_node_step[node_id] = (
            self.energy_consumed_by_node_step.get(node_id, 0.0) + amount
        )
        if kind in {"data", "backhaul"}:
            self.data_energy_consumed += amount
            self.data_energy_consumed_step += amount
        else:
            self.control_energy_consumed += amount
            self.control_energy_consumed_step += amount
