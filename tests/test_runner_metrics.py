import unittest

from simulation.config import PROTOCOLS, SimulationConfig
from simulation.events import SimulationEvent
from simulation.runner import RoleSimulationModel


class TestSimulationRunner(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(
            seed=37,
            subnet_counts=(2,),
            nodes_per_subnet=3,
            steps=8,
            epoch_length=20,
        )

    def test_runner_records_metrics_and_routes_data_each_tick(self):
        model = RoleSimulationModel(self.config, protocol="proposed")
        expected_roles = len(model.hierarchy.scope_ids) * 4
        self.assertEqual(len(model.protocol_engine.assignments), expected_roles)
        model.run_steps(3)

        frame = model.metrics.timeseries_frame()
        self.assertEqual(len(frame), 4)
        self.assertEqual(frame.iloc[-1]["time"], 3)
        self.assertEqual(frame.iloc[-1]["data_messages_step"], 6)
        self.assertEqual(frame.iloc[-1]["active_node_count"], 6)
        self.assertGreaterEqual(frame.iloc[-1]["role_availability"], 0.0)
        self.assertTrue(set(("gateway_load_mean", "energy_variance")).issubset(frame.columns))

    def test_widespread_mode_routes_aggregated_backhaul_and_records_energy(self):
        config = SimulationConfig(
            seed=37,
            subnet_counts=(2,),
            nodes_per_subnet=3,
            steps=2,
            epoch_length=20,
            intercluster_gap_in_ranges=1.5,
            distance_energy_weight=1.0,
            hierarchical_backhaul=True,
        )
        model = RoleSimulationModel(config, protocol="proposed")
        model.run_steps(1)
        final = model.metrics.timeseries_frame().iloc[-1]
        summary = model.metrics.summary("normal", config.seed)

        self.assertGreater(final["backhaul_messages_step"], 0)
        self.assertGreater(final["backhaul_hop_transmissions_step"], 0)
        self.assertGreater(final["communication_energy_consumed_step"], 0)
        self.assertGreater(final["gateway_energy_consumed_step"], 0)
        self.assertGreater(summary["communication_energy_consumed"], 0)
        self.assertGreater(summary["gateway_energy_consumed"], 0)
        self.assertEqual(final["sensor_data_messages_step"], config.num_nodes)
        self.assertGreaterEqual(final["sensor_data_delivery_fraction"], 0.0)

    def test_failure_event_reassigns_and_records_recovery(self):
        model = RoleSimulationModel(self.config, protocol="dynamic")
        subnet_scope = model.topology.node_to_subnet[0]
        lease = model.protocol_engine.assignments[("gateway", subnet_scope)]
        failed_holder = lease.holder_id
        model = RoleSimulationModel(
            self.config,
            protocol="dynamic",
            event_schedule=(SimulationEvent(1, failed_holder, "fail"),),
        )
        model.run_steps(1)
        reassigned = model.protocol_engine.assignments[("gateway", subnet_scope)]
        self.assertNotEqual(reassigned.holder_id, failed_holder)
        self.assertEqual(model.protocol_engine.recovery_times, [0.0])
        self.assertEqual(model.metrics.timeseries_frame().iloc[-1]["failed_unavailable_roles"], 0)

    def test_central_controller_failure_makes_centralized_roles_unavailable(self):
        model = RoleSimulationModel(self.config, protocol="centralized")
        controller_id = model.controller_node_id
        model.fail_node(controller_id)
        model.step()
        final = model.metrics.timeseries_frame().iloc[-1]
        self.assertEqual(final["role_availability"], 0.0)

    def test_network_lifetime_is_marked_when_active_fraction_crosses_threshold(self):
        config = SimulationConfig(seed=37, subnet_counts=(1,), nodes_per_subnet=2, steps=3)
        model = RoleSimulationModel(config, protocol="static")
        model.fail_node(0)
        model.fail_node(1)
        model.step()
        self.assertEqual(model.network_lifetime_tick, 1)

    def test_protocols_share_identical_seeded_initial_world(self):
        models = [
            RoleSimulationModel(self.config, protocol=protocol)
            for protocol in PROTOCOLS
        ]
        topology_fingerprints = [
            (
                model.topology.positions,
                model.topology.node_to_subnet,
                model.topology.attributes,
            )
            for model in models
        ]
        self.assertTrue(all(fingerprint == topology_fingerprints[0] for fingerprint in topology_fingerprints))

    def test_model_rejects_unknown_event_nodes_and_overrun(self):
        with self.assertRaises(ValueError):
            RoleSimulationModel(
                self.config,
                event_schedule=(SimulationEvent(1, 999, "fail"),),
            )
        model = RoleSimulationModel(self.config)
        with self.assertRaises(ValueError):
            model.run_steps(self.config.steps + 1)


if __name__ == "__main__":
    unittest.main()
