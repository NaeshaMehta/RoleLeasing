import unittest
import random

import mesa
from transitions.core import MachineError

from simulation.capability import refresh_capabilities
from simulation.communications import NetworkRouter
from simulation.config import SimulationConfig
from simulation.entities import build_hierarchy
from simulation.leases import Lease
from simulation.protocols import ProtocolEngine
from simulation.topology import create_topology


class ProtocolTestContext:
    def __init__(self, protocol, config):
        self.config = config
        self.protocol = protocol
        self.random = random.Random(config.seed)
        self.hierarchy = build_hierarchy(mesa.Model(seed=config.seed), create_topology(config))
        refresh_capabilities(self.hierarchy)
        self.router = NetworkRouter(create_topology(config), self.hierarchy, config)
        if protocol == "hierarchical":
            self.controller_node_id = self.random.choice(tuple(self.hierarchy.nodes_by_id))
        else:
            self.controller_node_id = max(
                self.hierarchy.nodes_by_id,
                key=lambda node_id: self.hierarchy.nodes_by_id[node_id].centrality,
            )

    @property
    def controller_available(self):
        return self.hierarchy.nodes_by_id[self.controller_node_id].is_available()

    def control_source(self, scope):
        if self.protocol in {"centralized", "hierarchical"}:
            return self.controller_node_id if self.controller_available else None
        return self.hierarchy.representative_node_id(scope)

    def holder_unavailable_since(self, _holder_id):
        return None

    def control_exchange(self, kind, scope, holder_id):
        source = self.control_source(scope)
        destination = self.hierarchy.representative_node_id(holder_id)
        if source is None or destination is None:
            return None
        return self.router.send(kind, source, destination)

    def control_exchange_batch(self, _kind, scope, destinations):
        return self.router.send_control_batch(self.control_source(scope), destinations)


class TestLeaseLifecycle(unittest.TestCase):
    def test_complete_lease_lifecycle(self):
        lease = Lease("gateway", "subnet_0", 1, 1, 0.0, 10.0, 10.0)
        lease.activate_lease()
        self.assertEqual(lease.state, "active")
        self.assertEqual(lease.renewal_time, 7.0)
        lease.renew_period(7.0, 12.0)
        self.assertEqual((lease.state, lease.expiry_time), ("active", 19.0))
        self.assertAlmostEqual(lease.renewal_time, 15.4)
        lease.migrate_holder(2, 8.0, 15.0, 2)
        self.assertEqual((lease.state, lease.holder_id, lease.epoch), ("active", 2, 2))
        lease.expire()
        self.assertEqual(lease.state, "expired")

    def test_invalid_lifecycle_operations_are_rejected(self):
        lease = Lease("gateway", "subnet_0", 1, 1, 0.0, 10.0, 10.0)
        with self.assertRaises(MachineError):
            lease.expire()
        lease.activate_lease()
        lease.invalidate_lease()
        self.assertEqual(lease.state, "expired")


class TestProtocolPolicies(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(
            seed=13,
            subnet_counts=(2,),
            nodes_per_subnet=3,
            steps=5,
            epoch_length=100,
            migration_weight=0.0,
            hysteresis_delta=0.0,
        )

    def test_one_assignment_per_role_and_scope(self):
        context = ProtocolTestContext("proposed", self.config)
        engine = ProtocolEngine(context, "proposed")
        expected = len(context.hierarchy.scope_ids) * 4
        self.assertEqual(len(engine.assignments), expected)
        self.assertEqual(len(engine.assignments), len(set(engine.assignments)))

    def test_static_protocol_does_not_reassign_failed_holder(self):
        context = ProtocolTestContext("static", self.config)
        engine = ProtocolEngine(context, "static")
        key = next(key for key, lease in engine.assignments.items() if isinstance(lease.holder_id, int))
        lease = engine.assignments[key]
        old_holder = lease.holder_id
        context.hierarchy.nodes_by_id[old_holder].fail()
        context.router.invalidate_graph()
        refresh_capabilities(context.hierarchy)
        engine.step(1)
        self.assertEqual(engine.assignments[key].holder_id, old_holder)
        self.assertFalse(engine.role_available(*key))

    def test_hierarchical_baseline_uses_fixed_controller_and_random_failover(self):
        context = ProtocolTestContext("hierarchical", self.config)
        repeated_context = ProtocolTestContext("hierarchical", self.config)
        self.assertEqual(context.controller_node_id, repeated_context.controller_node_id)
        self.assertEqual(
            context.control_source("subnet_0"),
            context.controller_node_id,
        )

        engine = ProtocolEngine(context, "hierarchical")
        repeated_engine = ProtocolEngine(repeated_context, "hierarchical")
        self.assertEqual(
            {
                key: lease.holder_id
                for key, lease in engine.assignments.items()
            },
            {
                key: lease.holder_id
                for key, lease in repeated_engine.assignments.items()
            },
        )
        key = next(
            key for key, lease in engine.assignments.items()
            if isinstance(lease.holder_id, int)
        )
        original_lease = engine.assignments[key]
        old_holder = original_lease.holder_id
        context.hierarchy.nodes_by_id[old_holder].fail()
        context.router.invalidate_graph()
        refresh_capabilities(context.hierarchy)
        engine.step(1)

        self.assertIn(key, engine.assignments)
        self.assertNotEqual(engine.assignments[key].holder_id, old_holder)
        self.assertTrue(context.hierarchy.is_available(engine.assignments[key].holder_id))
        self.assertEqual(len(engine.migration_records), 1)
        self.assertEqual(engine.migration_records[0]["old_holder"], old_holder)
        self.assertEqual(engine.migration_records[0]["new_holder"], engine.assignments[key].holder_id)

    def test_dynamic_protocol_reassigns_failed_holder_immediately(self):
        context = ProtocolTestContext("dynamic", self.config)
        engine = ProtocolEngine(context, "dynamic")
        key = next(key for key, lease in engine.assignments.items() if isinstance(lease.holder_id, int))
        lease = engine.assignments[key]
        old_holder = lease.holder_id
        context.hierarchy.nodes_by_id[old_holder].fail()
        context.router.invalidate_graph()
        refresh_capabilities(context.hierarchy)
        engine.step(1)
        self.assertNotEqual(engine.assignments[key].holder_id, old_holder)
        self.assertTrue(context.hierarchy.is_available(engine.assignments[key].holder_id))

    def test_proposed_migrates_only_after_hysteresis_improvement(self):
        context = ProtocolTestContext("proposed", self.config)
        engine = ProtocolEngine(context, "proposed")
        key = next(key for key, lease in engine.assignments.items() if isinstance(lease.holder_id, int))
        lease = engine.assignments[key]
        old_holder = lease.holder_id
        subnet_nodes = context.hierarchy.subnets[key[1]].node_ids
        replacement = next(node_id for node_id in subnet_nodes if node_id != old_holder)
        context.hierarchy.nodes_by_id[old_holder].energy = 0.01
        context.hierarchy.nodes_by_id[replacement].energy = 1.0
        refresh_capabilities(context.hierarchy)
        engine.step(1)
        self.assertEqual(engine.assignments[key].holder_id, replacement)
        self.assertIs(engine.assignments[key], lease)
        self.assertTrue(engine.migration_records)

    def test_proposed_hysteresis_blocks_a_non_improvement(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=self.config.subnet_counts,
            nodes_per_subnet=self.config.nodes_per_subnet,
            steps=self.config.steps,
            epoch_length=100,
            hysteresis_delta=0.99,
        )
        context = ProtocolTestContext("proposed", config)
        engine = ProtocolEngine(context, "proposed")
        key = next(key for key, lease in engine.assignments.items() if isinstance(lease.holder_id, int))
        old_holder = engine.assignments[key].holder_id
        engine.step(1)
        self.assertEqual(engine.assignments[key].holder_id, old_holder)
        self.assertFalse(engine.migration_records)

    def test_lease_renews_once_at_the_seventy_percent_point(self):
        context = ProtocolTestContext("proposed", self.config)
        engine = ProtocolEngine(context, "proposed")
        lease = next(iter(engine.assignments.values()))
        lease.start_time = 0.0
        lease.duration = 10.0
        lease.expiry_time = 10.0
        messages_before = context.router.control_messages
        engine.step(7)
        messages_after_renewal = context.router.control_messages
        engine.step(8)
        self.assertEqual(messages_after_renewal, messages_before + 1)
        self.assertEqual(context.router.control_messages, messages_after_renewal)

    def test_lease_renewal_fraction_is_configurable(self):
        lease = Lease(
            "gateway",
            "subnet_0",
            1,
            1,
            0.0,
            10.0,
            10.0,
            renewal_fraction=0.9,
        )
        self.assertEqual(lease.renewal_time, 9.0)

    def test_batch_control_updates_combine_due_renewals_per_scope(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=10,
            epoch_length=100,
            batch_control_updates=True,
        )
        context = ProtocolTestContext("proposed", config)
        engine = ProtocolEngine(context, "proposed")
        for lease in engine.assignments.values():
            lease.start_time = 0.0
            lease.duration = 10.0
            lease.expiry_time = 10.0
        messages_before = context.router.control_messages

        engine.step(7)

        self.assertEqual(
            context.router.control_messages - messages_before,
            len(context.hierarchy.scope_ids),
        )

    def test_epoch_fencing_reissues_current_epoch_leases(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=self.config.subnet_counts,
            nodes_per_subnet=self.config.nodes_per_subnet,
            steps=self.config.steps,
            epoch_length=1,
            migration_weight=self.config.migration_weight,
            hysteresis_delta=self.config.hysteresis_delta,
        )
        context = ProtocolTestContext("proposed", config)
        engine = ProtocolEngine(context, "proposed")
        engine.step(1)
        self.assertEqual(engine.current_epoch, 2)
        self.assertTrue(all(lease.epoch == 2 for lease in engine.assignments.values()))

    def test_epoch_fencing_can_retain_valid_leases_without_regranting(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=self.config.subnet_counts,
            nodes_per_subnet=self.config.nodes_per_subnet,
            steps=self.config.steps,
            epoch_length=1,
            retain_valid_leases_on_epoch=True,
        )
        context = ProtocolTestContext("proposed", config)
        engine = ProtocolEngine(context, "proposed")
        original = dict(engine.assignments)
        messages_before = context.router.control_messages

        engine.step(1)

        self.assertEqual(engine.current_epoch, 2)
        self.assertEqual(engine.assignments, original)
        self.assertTrue(all(lease.epoch == 2 for lease in engine.assignments.values()))
        self.assertEqual(context.router.control_messages, messages_before)

    def test_periodic_capability_broadcasts_are_costed_and_refresh_knowledge(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=3,
            epoch_length=100,
            hysteresis_delta=100.0,
            capability_broadcast_interval_steps=1,
        )
        context = ProtocolTestContext("proposed", config)
        engine = ProtocolEngine(context, "proposed")
        node_id = context.hierarchy.subnets["network_0_subnet_0"].node_ids[0]
        role = "anomaly_detection"
        stale_capability = engine._observed_capabilities[(node_id, role)]
        context.hierarchy.nodes_by_id[node_id].health = 0.01
        refresh_capabilities(context.hierarchy)
        messages_before = context.router.control_messages

        engine.step(1)

        self.assertEqual(
            context.router.control_messages - messages_before,
            len(context.hierarchy.scope_ids),
        )
        self.assertGreater(context.router.message_hop_transmissions, 0)
        self.assertGreater(context.router.control_energy_consumed, 0)
        self.assertNotAlmostEqual(
            engine._observed_capabilities[(node_id, role)],
            stale_capability,
            places=3,
        )
        self.assertAlmostEqual(
            engine._observed_capabilities[(node_id, role)],
            context.hierarchy.capability(node_id, role),
            places=4,
        )

    def test_configured_detection_delay_is_reflected_in_recovery_time(self):
        config = SimulationConfig(
            seed=self.config.seed,
            subnet_counts=self.config.subnet_counts,
            nodes_per_subnet=self.config.nodes_per_subnet,
            steps=self.config.steps,
            epoch_length=100,
            detection_delay_steps=1,
        )
        context = ProtocolTestContext("dynamic", config)
        engine = ProtocolEngine(context, "dynamic")
        key = next(key for key, lease in engine.assignments.items() if isinstance(lease.holder_id, int))
        old_holder = engine.assignments[key].holder_id
        context.hierarchy.nodes_by_id[old_holder].fail()
        context.router.invalidate_graph()
        refresh_capabilities(context.hierarchy)

        engine.step(1)
        self.assertEqual(engine.assignments[key].holder_id, old_holder)
        engine.step(2)
        self.assertNotEqual(engine.assignments[key].holder_id, old_holder)
        self.assertIn(1.0, engine.recovery_times)


if __name__ == "__main__":
    unittest.main()
