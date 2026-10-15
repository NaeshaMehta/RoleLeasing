import unittest

import pandas as pd
from simulation.config import SimulationConfig
from simulation.events import SimulationEvent
from simulation.runner import RoleSimulationModel


class TestSolarBatteryModel(unittest.TestCase):
    def test_solar_configuration_validates_reserve_capacity_and_harvest(self):
        with self.assertRaises(ValueError):
            SimulationConfig(battery_capacity=0.0)
        with self.assertRaises(ValueError):
            SimulationConfig(minimum_energy_reserve=1.0)
        with self.assertRaises(ValueError):
            SimulationConfig(solar_harvest_rate=-0.1)
        with self.assertRaises(ValueError):
            SimulationConfig(solar_migration_safety_margin=-0.1)

    def test_battery_harvest_and_consumption_respect_capacity(self):
        config = SimulationConfig(
            seed=7,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            battery_capacity=0.8,
            energy_range=(0.7, 0.8),
        )
        model = RoleSimulationModel(config=config)
        node = model.nodes_by_id[0]
        node.energy = 0.75

        accepted = node.harvest_energy(0.2)
        self.assertAlmostEqual(accepted, 0.05)
        self.assertAlmostEqual(node.energy, 0.8)

        node.degrade_energy(1.0)
        self.assertEqual(node.energy, 0.0)
        node.harvest_energy(0.1)
        self.assertAlmostEqual(node.energy, 0.1)
        with self.assertRaises(ValueError):
            node.harvest_energy(-0.1)

    def test_seeded_per_node_solar_rates_are_reproducible_and_bounded(self):
        config = SimulationConfig(
            seed=11,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            solar_harvest_rate=0.0002,
        )
        first = RoleSimulationModel(config=config)
        second = RoleSimulationModel(config=config)

        first_rates = {
            node_id: node.solar_harvest_rate
            for node_id, node in first.nodes_by_id.items()
        }
        second_rates = {
            node_id: node.solar_harvest_rate
            for node_id, node in second.nodes_by_id.items()
        }
        self.assertEqual(first_rates, second_rates)
        self.assertTrue(all(
            0.0001 <= rate <= 0.0003
            for rate in first_rates.values()
        ))

    def test_zero_harvest_preserves_existing_run_behavior(self):
        config = SimulationConfig(
            seed=13,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=5,
        )
        baseline = RoleSimulationModel(config=config)
        zero_solar = RoleSimulationModel(
            config=SimulationConfig(
                seed=13,
                subnet_counts=(1,),
                nodes_per_subnet=4,
                steps=5,
                solar_harvest_rate=0.0,
            )
        )
        baseline.run_steps()
        zero_solar.run_steps()

        pd.testing.assert_frame_equal(
            baseline.metrics.timeseries_frame(),
            zero_solar.metrics.timeseries_frame(),
        )
        self.assertEqual(zero_solar.solar_energy_harvested, 0.0)

    def test_solar_metrics_separate_harvest_consumption_and_residual_energy(self):
        config = SimulationConfig(
            seed=17,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=2,
            solar_harvest_rate=0.0002,
        )
        model = RoleSimulationModel(config=config)
        model.run_steps()
        summary = model.metrics.summary("normal", config.seed)
        timeseries = model.metrics.timeseries_frame()

        self.assertGreater(summary["solar_energy_harvested"], 0)
        self.assertGreater(summary["total_modeled_energy_consumed"], 0)
        self.assertGreaterEqual(summary["average_remaining_energy"], 0)
        self.assertIn("depleted_node_count", timeseries.columns)
        self.assertGreater(summary["sensor_data_messages"], 0)

    def test_solar_recharges_energy_depleted_node_to_reserve_before_rejoining(self):
        config = SimulationConfig(
            seed=18,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            battery_capacity=0.8,
            energy_range=(0.7, 0.8),
            minimum_energy_reserve=0.1,
            solar_harvest_rate=0.2,
        )
        model = RoleSimulationModel(config=config)
        node = model.nodes_by_id[0]
        node.energy = 0.0
        node.fail()
        model._energy_depleted_node_ids.add(0)
        node.solar_harvest_rate = 0.15

        model._harvest_solar_energy()

        self.assertTrue(node.is_available())
        self.assertGreaterEqual(node.energy, config.minimum_energy_reserve)
        self.assertNotIn(0, model._energy_depleted_node_ids)


class TestSolarMigrationGate(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(
            seed=19,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=8,
            epoch_length=100,
            solar_migration_gate=True,
            solar_decision_horizon_steps=20,
            solar_migration_safety_margin=0.01,
        )
        self.model = RoleSimulationModel(config=self.config, protocol="proposed")
        self.engine = self.model.protocol_engine

    def _prepare_migration(self, candidate_harvest: float):
        nodes = self.model.nodes_by_id
        for node in nodes.values():
            node.energy = 0.5
            node.health = 0.1
            node.solar_harvest_rate = 0.0
        current_id, candidate_id = 0, 1
        nodes[current_id].health = 0.2
        nodes[candidate_id].health = 0.9
        nodes[candidate_id].solar_harvest_rate = candidate_harvest
        scope = nodes[current_id].subnet_id
        role = "anomaly_detection"
        lease = self.engine.assignments[(role, scope)]
        lease.holder_id = current_id
        return current_id, candidate_id, scope, role, lease

    def test_gate_accepts_migration_when_projected_energy_benefit_covers_cost(self):
        current_id, candidate_id, scope, role, lease = self._prepare_migration(0.005)

        self.engine._consider_cost_aware_migration(
            (role, scope),
            lease,
            now=4,
        )

        self.assertEqual(lease.holder_id, candidate_id)
        self.assertEqual(len(self.engine.migration_records), 1)
        source = self.model.control_source(scope)
        destination = self.model.hierarchy.representative_node_id(candidate_id)
        self.assertIsNotNone(source)
        self.assertIsNotNone(destination)
        assert source is not None and destination is not None
        route = self.model.router.find_route(source, destination)
        self.assertIsNotNone(route)
        assert route is not None
        self.assertGreater(
            self.engine._projected_reserve_energy(candidate_id, now=4)
            - self.engine._projected_reserve_energy(current_id, now=4),
            self.model.router.estimate_route_energy("MIGRATE", route)
            + self.config.solar_migration_safety_margin,
        )

    def test_gate_rejects_migration_when_benefit_is_below_cost_and_margin(self):
        current_id, candidate_id, scope, role, lease = self._prepare_migration(0.0001)
        control_messages_before = self.model.router.control_messages

        self.engine._consider_cost_aware_migration(
            (role, scope),
            lease,
            now=4,
        )

        self.assertEqual(lease.holder_id, current_id)
        self.assertEqual(self.engine.migration_records, [])
        self.assertEqual(self.model.router.control_messages, control_messages_before)

    def test_provider_ranking_remains_capability_only(self):
        for node in self.model.nodes_by_id.values():
            node.energy = 0.2
            node.health = 0.2
            node.solar_harvest_rate = 0.0
        self.model.nodes_by_id[0].energy = 0.5
        self.model.nodes_by_id[0].health = 1.0
        self.model.nodes_by_id[1].energy = 0.5
        self.model.nodes_by_id[1].health = 0.9
        self.model.nodes_by_id[1].solar_harvest_rate = 0.05

        selected = self.engine._select_for_role(
            self.model.nodes_by_id[0].subnet_id,
            "anomaly_detection",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected[0], 0)

    def test_failure_recovery_bypasses_optional_migration_gate(self):
        self.config = SimulationConfig(
            seed=23,
            subnet_counts=(1,),
            nodes_per_subnet=6,
            steps=4,
            epoch_length=100,
            solar_migration_gate=True,
            solar_migration_safety_margin=1.0,
        )
        initial = RoleSimulationModel(config=self.config, protocol="proposed")
        scope = initial.hierarchy.scope_ids[0]
        lease = initial.protocol_engine.assignments[("anomaly_detection", scope)]
        failed_holder = lease.holder_id
        model = RoleSimulationModel(
            config=self.config,
            protocol="proposed",
            event_schedule=(SimulationEvent(1, int(failed_holder), "fail"),),
        )
        model.protocol_engine.assignments[("anomaly_detection", scope)].holder_id = failed_holder
        model.run_steps()

        recovered_lease = model.protocol_engine.assignments[("anomaly_detection", scope)]
        self.assertNotEqual(recovered_lease.holder_id, failed_holder)
        self.assertEqual(recovered_lease.state, "active")
        self.assertTrue(model.protocol_engine.role_available(
            "anomaly_detection",
            scope,
        ))

    def test_gate_preserves_valid_leases_across_epochs(self):
        config = SimulationConfig(
            seed=29,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=8,
            epoch_length=2,
            retain_valid_leases_on_epoch=True,
            solar_harvest_rate=0.0002,
            solar_migration_gate=True,
        )
        model = RoleSimulationModel(config=config, protocol="proposed")
        model.run_steps()

        self.assertTrue(model.protocol_engine.assignments)
        self.assertTrue(all(
            lease.state == "active"
            and lease.epoch == model.protocol_engine.current_epoch
            for lease in model.protocol_engine.assignments.values()
        ))


class TestPatentStudyMetrics(unittest.TestCase):
    def test_sensor_counts_and_csc_denominator_are_explicit(self):
        config = SimulationConfig(
            seed=31,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=3,
        )
        model = RoleSimulationModel(config=config, protocol="proposed")
        model.run_steps()
        summary = model.metrics.summary("normal", config.seed)
        series = model.metrics.timeseries_frame()

        self.assertEqual(
            summary["capability_time_intervals_required"],
            len(model.protocol_engine.assignment_keys) * config.steps,
        )
        self.assertEqual(
            summary["sensor_items_generated"],
            model.router.sensor_data_messages,
        )
        self.assertEqual(
            summary["sensor_items_delivered"],
            model.router.sensor_data_delivered,
        )
        self.assertAlmostEqual(
            summary["sensor_delivery_fraction"],
            summary["sensor_items_delivered"] / summary["sensor_items_generated"],
        )
        self.assertAlmostEqual(
            summary["communication_energy_per_delivered_item"],
            summary["total_modeled_energy_consumed"]
            / summary["sensor_items_delivered"],
        )
        self.assertIn("cumulative_capability_service_continuity", series.columns)
        self.assertIn("sensor_items_generated_step", series.columns)
        self.assertIn("sensor_items_delivered_step", series.columns)

    def test_lifetime_crossings_record_first_below_threshold_tick(self):
        config = SimulationConfig(
            seed=37,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=4,
        )
        model = RoleSimulationModel(config=config, protocol="proposed")
        recorder = model.metrics

        recorder._record_lifetime_crossings(1, 0.89, 0.95)
        recorder._record_lifetime_crossings(2, 0.45, 0.49)
        recorder._record_lifetime_crossings(3, 0.40, 0.40)

        self.assertEqual(
            recorder.service_lifetime_crossings[
                ("capability_service_continuity", 0.9)
            ],
            1,
        )
        self.assertEqual(
            recorder.service_lifetime_crossings[
                ("capability_service_continuity", 0.5)
            ],
            2,
        )
        self.assertEqual(
            recorder.service_lifetime_crossings[("sensor_delivery_fraction", 0.9)],
            2,
        )
        self.assertEqual(
            recorder.service_lifetime_crossings[("sensor_delivery_fraction", 0.5)],
            2,
        )


if __name__ == "__main__":
    unittest.main()
