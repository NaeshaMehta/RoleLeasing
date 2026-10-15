"""
test_nodes.py — Unit tests for NodeAgent.

Run with: pytest test_nodes.py -v
Or directly: python test_nodes.py
"""

import unittest
import mesa
from nodes import NodeAgent, ROLE_WEIGHTS, SUPPORTED_ROLES


class DummyModel(mesa.Model):
    """Minimal model to satisfy Mesa Agent initialization."""
    pass


class TestNodeAgentInitialization(unittest.TestCase):
    """Test that nodes initialize with correct default state and attributes."""

    def setUp(self):
        self.model = DummyModel()
        self.node = NodeAgent(self.model, subnet_id="test_subnet_0")

    def test_initial_state_is_online(self):
        """Node should start in 'online' state per spec §3.9."""
        self.assertEqual(self.node.state, "online")
        self.assertTrue(self.node.is_available())

    def test_default_attributes_in_range(self):
        """All physical attributes must be within [0, 1] after init."""
        for attr in ["energy", "health", "link_quality", "centrality"]:
            val = getattr(self.node, attr)
            self.assertGreaterEqual(val, 0.0, f"{attr} below 0")
            self.assertLessEqual(val, 1.0, f"{attr} above 1")

    def test_subnet_membership_stored(self):
        """Node must record its subnet ID per spec §3.1."""
        self.assertEqual(self.node.subnet_id, "test_subnet_0")

    def test_unique_ids_assigned_by_model(self):
        """Mesa should assign unique IDs automatically."""
        node2 = NodeAgent(self.model, subnet_id="other")
        self.assertNotEqual(self.node.unique_id, node2.unique_id)


class TestCapabilityCalculation(unittest.TestCase):
    """Test capability computation per spec §3.2."""

    def setUp(self):
        self.model = DummyModel()
        self.node = NodeAgent(self.model, subnet_id="s0")
        # Set deterministic values for predictable results
        self.node.energy = 1.0
        self.node.health = 1.0
        self.node.link_quality = 1.0
        self.node.centrality = 1.0

    def test_capability_in_unit_interval(self):
        """C(e,r) must be in [0, 1] for all roles."""
        for role in SUPPORTED_ROLES:
            cap = self.node.capability(role)
            self.assertGreaterEqual(cap, 0.0, f"{role} capability < 0")
            self.assertLessEqual(cap, 1.0, f"{role} capability > 1")

    def test_gateway_uses_correct_attributes(self):
        """Gateway = energy + link_quality + centrality (weights sum to 1)."""
        # With all attrs = 1.0, gateway cap should be exactly 1.0
        self.assertAlmostEqual(self.node.capability("gateway"), 1.0)

        # Zero out health — should NOT affect gateway capability
        self.node.health = 0.0
        self.assertAlmostEqual(self.node.capability("gateway"), 1.0)

    def test_anomaly_detection_uses_energy_and_health_only(self):
        """Anomaly detection ignores link_quality and centrality."""
        self.node.link_quality = 0.0
        self.node.centrality = 0.0
        # energy=1, health=1 → cap should still be 1.0
        self.assertAlmostEqual(self.node.capability("anomaly_detection"), 1.0)

    def test_health_monitoring_uses_energy_and_health_only(self):
        """Health monitoring ignores link_quality and centrality."""
        self.node.link_quality = 0.0
        self.node.centrality = 0.0
        self.assertAlmostEqual(self.node.capability("health_monitoring"), 1.0)

    def test_discoverability_uses_energy_link_health(self):
        """Discoverability ignores centrality."""
        self.node.centrality = 0.0
        # energy=1, link_quality=1, health=1 → cap should be ~1.0
        self.assertAlmostEqual(self.node.capability("discoverability"), 1.0)

    def test_zero_energy_yields_low_capability(self):
        """If energy drops to 0, capability should drop significantly."""
        self.node.energy = 0.0
        for role in SUPPORTED_ROLES:
            cap = self.node.capability(role)
            # All roles include energy with positive weight, so cap < 1.0
            self.assertLess(cap, 1.0, f"{role} should be affected by zero energy")

    def test_failed_node_returns_zero_capability(self):
        """Per spec §3.9: failed node contributes no capability."""
        self.node.fail()
        for role in SUPPORTED_ROLES:
            self.assertEqual(
                self.node.capability(role), 0.0,
                f"Failed node should return 0 for {role}"
            )

    def test_unsupported_role_raises_error(self):
        """Requesting an unknown role must raise ValueError."""
        with self.assertRaises(ValueError):
            self.node.capability("nonexistent_role")

    def test_capability_vector_covers_all_roles(self):
        """capability_vector() should return a dict for every supported role."""
        vec = self.node.capability_vector()
        self.assertEqual(set(vec.keys()), set(SUPPORTED_ROLES))
        for val in vec.values():
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)


class TestStateTransitions(unittest.TestCase):
    """Test the transitions-based state machine per spec §3.9."""

    def setUp(self):
        self.model = DummyModel()
        self.node = NodeAgent(self.model, subnet_id="s0")

    def test_fail_transition(self):
        """online → failed via fail() trigger."""
        self.assertEqual(self.node.state, "online")
        self.node.fail()
        self.assertEqual(self.node.state, "failed")
        self.assertFalse(self.node.is_available())

    def test_recover_transition(self):
        """failed → online via recover() trigger."""
        self.node.fail()
        self.assertEqual(self.node.state, "failed")
        self.node.recover()
        self.assertEqual(self.node.state, "online")
        self.assertTrue(self.node.is_available())

    def test_double_fail_is_noop_or_error(self):
        """Failing an already-failed node should not crash (transitions handles it)."""
        self.node.fail()
        # transitions raises MachineError by default on invalid transition;
        # if your config allows it, this just stays failed. We assert state unchanged.
        try:
            self.node.fail()
        except Exception:
            pass  # Expected if strict mode; either way state must be 'failed'
        self.assertEqual(self.node.state, "failed")

    def test_recover_from_online_is_noop_or_error(self):
        """Recovering an already-online node should not crash."""
        try:
            self.node.recover()
        except Exception:
            pass
        self.assertEqual(self.node.state, "online")


class TestEventMethods(unittest.TestCase):
    """Test injected events per spec §4. No passive decay allowed."""

    def setUp(self):
        self.model = DummyModel()
        self.node = NodeAgent(self.model, subnet_id="s0")
        self.node.energy = 1.0
        self.node.link_quality = 1.0

    def test_degrade_energy_reduces_value(self):
        """degrade_energy(amount) must reduce energy by exactly amount."""
        self.node.degrade_energy(0.3)
        self.assertAlmostEqual(self.node.energy, 0.7)

    def test_degrade_energy_clamps_at_zero(self):
        """Energy cannot go below 0."""
        self.node.degrade_energy(2.0)
        self.assertEqual(self.node.energy, 0.0)

    def test_degrade_link_reduces_value(self):
        """degrade_link(amount) must reduce link_quality by exactly amount."""
        self.node.degrade_link(0.4)
        self.assertAlmostEqual(self.node.link_quality, 0.6)

    def test_degrade_link_clamps_at_zero(self):
        """Link quality cannot go below 0."""
        self.node.degrade_link(5.0)
        self.assertEqual(self.node.link_quality, 0.0)

    def test_step_does_not_change_attributes(self):
        """step() must NOT decay energy or any attribute (spec §4: events only)."""
        e_before = self.node.energy
        lq_before = self.node.link_quality
        h_before = self.node.health
        c_before = self.node.centrality

        for _ in range(100):
            self.node.step()

        self.assertEqual(self.node.energy, e_before)
        self.assertEqual(self.node.link_quality, lq_before)
        self.assertEqual(self.node.health, h_before)
        self.assertEqual(self.node.centrality, c_before)

    def test_capability_changes_after_degradation_event(self):
        """Capability must reflect degradation immediately after event."""
        cap_before = self.node.capability("gateway")
        self.node.degrade_energy(0.5)
        cap_after = self.node.capability("gateway")
        self.assertLess(cap_after, cap_before)


class TestRoleWeightsIntegrity(unittest.TestCase):
    """Ensure the module-level ROLE_WEIGHTS table is well-formed."""

    def test_all_weights_sum_to_one(self):
        """Each role's weights must sum to 1.0 for [0,1] output guarantee."""
        for role, weights in ROLE_WEIGHTS.items():
            total = sum(weights.values())
            self.assertAlmostEqual(
                total, 1.0, places=6,
                msg=f"Weights for '{role}' sum to {total}, not 1.0"
            )

    def test_all_weight_keys_are_valid_attributes(self):
        """Weight keys must correspond to actual node attributes."""
        valid_attrs = {"energy", "health", "link_quality", "centrality"}
        for role, weights in ROLE_WEIGHTS.items():
            for key in weights:
                self.assertIn(
                    key, valid_attrs,
                    f"Role '{role}' has invalid weight key '{key}'"
                )

    def test_supported_roles_match_weights(self):
        """SUPPORTED_ROLES must exactly match ROLE_WEIGHTS keys."""
        self.assertEqual(set(SUPPORTED_ROLES), set(ROLE_WEIGHTS.keys()))


if __name__ == "__main__":
    unittest.main()
