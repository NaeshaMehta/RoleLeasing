import unittest

import mesa

from simulation.communications import NetworkRouter
from simulation.config import SimulationConfig
from simulation.entities import build_hierarchy
from simulation.topology import create_topology


class TestNetworkRouter(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(subnet_counts=(1,), nodes_per_subnet=4)
        self.topology = create_topology(self.config)
        self.model = mesa.Model(seed=self.config.seed)
        self.hierarchy = build_hierarchy(self.model, self.topology)
        for node in self.hierarchy.nodes_by_id.values():
            node.link_quality = 1.0
        self.topology.adjacency = {
            0: {1: 0.9, 2: 0.9, 3: 0.01},
            1: {0: 0.9, 3: 0.9},
            2: {0: 0.9, 3: 0.9},
            3: {0: 0.01, 1: 0.9, 2: 0.9},
        }
        self.router = NetworkRouter(self.topology, self.hierarchy, self.config)

    def test_quality_weighted_route_prefers_reliable_multihop_path(self):
        route = self.router.find_route(0, 3)
        self.assertIsNotNone(route)
        assert route is not None
        self.assertIn(route.path, ((0, 1, 3), (0, 2, 3)))
        self.assertEqual(route.hops, 2)
        self.assertAlmostEqual(route.bottleneck_quality, 0.9)

    def test_send_accounts_logical_messages_hops_and_energy(self):
        energy_before = self.hierarchy.nodes_by_id[0].energy
        route = self.router.send("LEASE_GRANT", 0, 3)
        self.assertIsNotNone(route)
        self.assertEqual(self.router.control_messages, 1)
        self.assertEqual(self.router.message_hop_transmissions, 2)
        self.assertEqual(self.router.step_metrics()["control_messages_step"], 1)
        self.assertLess(self.hierarchy.nodes_by_id[0].energy, energy_before)

    def test_control_broadcast_counts_one_message_and_tree_hops(self):
        before_energy = self.hierarchy.nodes_by_id[0].energy
        delivered = self.router.broadcast_control(0, (0, 1, 2, 3))

        self.assertTrue(delivered)
        self.assertEqual(self.router.control_messages, 1)
        self.assertEqual(self.router.message_hop_transmissions, 3)
        self.assertEqual(self.router.failed_deliveries, 0)
        self.assertLess(self.hierarchy.nodes_by_id[0].energy, before_energy)

    def test_batched_control_counts_one_message_and_unique_route_edges(self):
        delivered = self.router.send_control_batch(0, (1, 2, 3))

        self.assertTrue(delivered)
        self.assertEqual(self.router.control_messages, 1)
        self.assertEqual(self.router.message_hop_transmissions, 3)
        self.assertEqual(self.router.failed_deliveries, 0)

    def test_distance_energy_charges_transmitters_for_longer_links(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            distance_energy_weight=2.0,
        )
        topology = create_topology(config)
        hierarchy = build_hierarchy(mesa.Model(seed=config.seed), topology)
        topology.adjacency = {0: {1: 0.9}, 1: {0: 0.9}, 2: {}, 3: {}}
        topology.positions[0] = (0.0, 0.0)
        topology.positions[1] = (config.communication_range, 0.0)
        router = NetworkRouter(topology, hierarchy, config)
        sender_before = hierarchy.nodes_by_id[0].energy
        receiver_before = hierarchy.nodes_by_id[1].energy

        router.send("data", 0, 1)

        sender_used = sender_before - hierarchy.nodes_by_id[0].energy
        receiver_used = receiver_before - hierarchy.nodes_by_id[1].energy
        self.assertAlmostEqual(sender_used, config.data_energy_per_hop * 3.0)
        self.assertAlmostEqual(receiver_used, config.data_energy_per_hop)
        self.assertAlmostEqual(router.data_energy_consumed, sender_used + receiver_used)

    def test_unreachable_destination_and_same_node_route(self):
        self.hierarchy.nodes_by_id[3].fail()
        self.assertIsNone(self.router.find_route(0, 3))
        self.assertIsNone(self.router.send("data", 0, 3))
        self.assertEqual(self.router.failed_deliveries, 1)
        self.assertEqual(self.router.find_route(0, 0).hops, 0)

    def test_link_degradation_can_partition_the_mesh(self):
        self.assertIsNotNone(self.router.find_route(0, 3))
        for node in (1, 2):
            self.hierarchy.nodes_by_id[node].link_quality = 0.0
        self.router.invalidate_graph()
        self.assertIsNone(self.router.find_route(0, 3))


if __name__ == "__main__":
    unittest.main()
