import unittest

import mesa

from simulation.capability import refresh_capabilities, weighted_aggregate
from simulation.config import SimulationConfig
from simulation.entities import build_hierarchy
from simulation.topology import create_topology
from nodes import SUPPORTED_ROLES


class TestCapabilityAggregation(unittest.TestCase):
    def test_uniform_and_declared_weight_aggregation(self):
        children = {
            "a": {"gateway": 0.2},
            "b": {"gateway": 0.8},
        }
        self.assertAlmostEqual(weighted_aggregate(children)["gateway"], 0.5)
        self.assertAlmostEqual(
            weighted_aggregate(children, {"a": 3.0, "b": 1.0})["gateway"],
            0.35,
        )

    def test_empty_children_and_invalid_weights(self):
        self.assertTrue(all(value == 0.0 for value in weighted_aggregate({}).values()))
        with self.assertRaises(ValueError):
            weighted_aggregate({"a": {"gateway": 0.5}}, {"a": 0.0})
        with self.assertRaises(ValueError):
            weighted_aggregate({"a": {"gateway": 1.2}})

    def test_recursive_aggregation_and_failed_leaf(self):
        config = SimulationConfig(subnet_counts=(2,), nodes_per_subnet=2)
        model = mesa.Model(seed=config.seed)
        hierarchy = build_hierarchy(model, create_topology(config))
        for node in hierarchy.nodes_by_id.values():
            node.energy = node.health = node.link_quality = node.centrality = 1.0
        refresh_capabilities(hierarchy)
        for subnet in hierarchy.subnets.values():
            self.assertEqual(subnet.capabilities, {role: 1.0 for role in SUPPORTED_ROLES})
        self.assertEqual(hierarchy.internetwork.capabilities["gateway"], 1.0)

        first = hierarchy.nodes_by_id[0]
        first.fail()
        refresh_capabilities(hierarchy)
        self.assertLess(hierarchy.subnets[first.subnet_id].capabilities["gateway"], 1.0)
        self.assertTrue(hierarchy.is_available(first.subnet_id))


class TestHierarchyEntities(unittest.TestCase):
    def test_distinct_mesa_entities_and_scope_candidate_levels(self):
        config = SimulationConfig(subnet_counts=(2, 1), nodes_per_subnet=2)
        model = mesa.Model(seed=config.seed)
        hierarchy = build_hierarchy(model, create_topology(config))
        self.assertEqual(len(hierarchy.nodes_by_id), 6)
        self.assertEqual(len(hierarchy.subnets), 3)
        self.assertEqual(len(hierarchy.networks), 2)
        self.assertEqual(len(hierarchy.scope_candidates), 3 + 2 + 1)
        self.assertEqual(len(hierarchy.scope_candidates["network_0"]), 2)
        self.assertEqual(len(hierarchy.scope_candidates["internetwork"]), 2)


if __name__ == "__main__":
    unittest.main()
