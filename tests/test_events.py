import unittest

import mesa

from simulation.config import SimulationConfig
from simulation.entities import build_hierarchy
from simulation.events import SimulationEvent, apply_event, generate_event_schedule
from simulation.topology import create_topology


class TestEventSchedules(unittest.TestCase):
    def test_schedules_are_deterministic_and_scenario_specific(self):
        config = SimulationConfig(seed=101, subnet_counts=(2,), nodes_per_subnet=5, steps=20)
        failures = generate_event_schedule("node_failures", config)
        self.assertEqual(failures, generate_event_schedule("node_failures", config))
        self.assertTrue(any(event.kind == "fail" for event in failures))
        self.assertTrue(any(event.kind == "recover" for event in failures))
        energy = generate_event_schedule("energy_degradation", config)
        link = generate_event_schedule("link_degradation", config)
        self.assertTrue(all(event.kind == "degrade_energy" for event in energy))
        self.assertTrue(all(event.kind == "degrade_link" for event in link))
        self.assertNotEqual(energy, link)
        self.assertEqual(generate_event_schedule("normal", config), ())

    def test_invalid_events_are_rejected(self):
        with self.assertRaises(ValueError):
            SimulationEvent(0, 0, "fail")
        with self.assertRaises(ValueError):
            SimulationEvent(1, 0, "degrade_link", 1.5)
        with self.assertRaises(ValueError):
            generate_event_schedule("unknown", SimulationConfig())


class TestEventApplication(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(subnet_counts=(1,), nodes_per_subnet=2)
        self.hierarchy = build_hierarchy(
            mesa.Model(seed=self.config.seed),
            create_topology(self.config),
        )

    def test_fail_recover_and_degradation_events(self):
        node = self.hierarchy.nodes_by_id[0]
        self.assertTrue(apply_event(SimulationEvent(1, 0, "fail"), self.hierarchy))
        self.assertFalse(apply_event(SimulationEvent(2, 0, "fail"), self.hierarchy))
        self.assertFalse(node.is_available())
        self.assertTrue(apply_event(SimulationEvent(3, 0, "recover"), self.hierarchy))
        self.assertTrue(node.is_available())

        energy_before = node.energy
        link_before = node.link_quality
        self.assertTrue(apply_event(SimulationEvent(4, 0, "degrade_energy", 0.2), self.hierarchy))
        self.assertTrue(apply_event(SimulationEvent(5, 0, "degrade_link", 0.2), self.hierarchy))
        self.assertAlmostEqual(node.energy, energy_before - 0.2)
        self.assertAlmostEqual(node.link_quality, link_before - 0.2)

    def test_unknown_node_event_is_explicit(self):
        with self.assertRaises(ValueError):
            apply_event(SimulationEvent(1, 99, "fail"), self.hierarchy)


if __name__ == "__main__":
    unittest.main()
