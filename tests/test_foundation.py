import unittest

from simulation.config import SimulationConfig
from simulation.topology import create_topology


class TestSimulationConfiguration(unittest.TestCase):
    def test_default_profile_matches_plan(self):
        config = SimulationConfig()
        self.assertEqual((config.num_nodes, config.num_subnets, config.num_networks), (100, 10, 3))
        self.assertEqual(config.subnet_counts, (4, 3, 3))

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            SimulationConfig(nodes_per_subnet=0)
        with self.assertRaises(ValueError):
            SimulationConfig(subnet_counts=(3, 0))
        with self.assertRaises(ValueError):
            SimulationConfig(communication_range=1.0)
        with self.assertRaises(ValueError):
            SimulationConfig(lease_min_duration=float("nan"))
        with self.assertRaises(ValueError):
            SimulationConfig(subnet_counts=(1.5,))
        with self.assertRaises(ValueError):
            SimulationConfig(intercluster_gap_in_ranges=float("inf"))
        with self.assertRaises(ValueError):
            SimulationConfig(capability_reassessment_interval_steps=0)
        with self.assertRaises(ValueError):
            SimulationConfig(capability_broadcast_interval_steps=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(lease_renewal_fraction=1.0)
        with self.assertRaises(ValueError):
            SimulationConfig(migration_cooldown_steps=-1)


class TestDeterministicTopology(unittest.TestCase):
    def test_fixed_seed_reproduces_topology_and_attributes(self):
        config = SimulationConfig()
        first = create_topology(config)
        second = create_topology(config)
        self.assertEqual(first.positions, second.positions)
        self.assertEqual(first.attributes, second.attributes)
        self.assertEqual(first.adjacency, second.adjacency)

    def test_physical_mesh_is_connected_and_membership_counts_match(self):
        topology = create_topology(SimulationConfig())
        self.assertEqual(len(topology.node_ids), 100)
        self.assertEqual(len(topology.subnet_ids), 10)
        self.assertEqual(len(topology.network_ids), 3)
        self.assertEqual(len(topology.node_to_subnet), 100)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in topology.centrality.values()))
        reached = {0}
        pending = [0]
        while pending:
            current = pending.pop()
            for neighbor in topology.adjacency[current]:
                if neighbor not in reached:
                    reached.add(neighbor)
                    pending.append(neighbor)
        self.assertEqual(len(reached), 100)

    def test_spaced_clusters_are_connected_by_low_quality_backhaul_links(self):
        config = SimulationConfig(intercluster_gap_in_ranges=1.5)
        topology = create_topology(config)
        long_edges = []
        for source, neighbors in topology.adjacency.items():
            for destination, quality in neighbors.items():
                if source >= destination:
                    continue
                source_subnet = topology.node_to_subnet[source]
                destination_subnet = topology.node_to_subnet[destination]
                distance = (
                    (topology.positions[source][0] - topology.positions[destination][0]) ** 2
                    + (topology.positions[source][1] - topology.positions[destination][1]) ** 2
                ) ** 0.5
                if source_subnet != destination_subnet and distance > config.communication_range:
                    long_edges.append((distance, quality))
        self.assertTrue(long_edges)
        self.assertTrue(all(quality <= 0.5 for _, quality in long_edges))
        reached = {0}
        pending = [0]
        while pending:
            current = pending.pop()
            for neighbor in topology.adjacency[current]:
                if neighbor not in reached:
                    reached.add(neighbor)
                    pending.append(neighbor)
        self.assertEqual(len(reached), config.num_nodes)


if __name__ == "__main__":
    unittest.main()
