"""
nodes.py — NodeAgent for the role-leasing simulation.

Responsibilities (spec §3.1):
  - Hold per-node physical attributes: energy, health, link_quality, centrality.
  - Record subnet membership.
  - Compute role-specific capability C(e, r) in [0, 1] (spec §3.2).
  - Expose operational state via a `transitions` state machine (online / failed),
    matching the architecture diagram's "Node states" + "Failure/recovery states".

Deliberately NOT done here:
  - No passive energy decay in step(). Per spec §4, degradation/failure are
    injected events; keeping them explicit preserves identical event schedules
    across protocol variants.
  - Capability weights are a module-level table (the node's part of the protocol
    definition), not buried logic — so they can be inspected/overridden cleanly.
"""

from __future__ import annotations
import mesa
from transitions import Machine


# ---------------------------------------------------------------------------
# Node capability definition (spec §3.2).
# Each role uses a specific subset of attributes; weights sum to 1 so that,
# given inputs in [0, 1], the result is guaranteed in [0, 1].
# This is the single source of truth for node-level capability.
# ---------------------------------------------------------------------------
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "gateway":          {"energy": 0.40, "link_quality": 0.35, "centrality": 0.25},
    "anomaly_detection":{"energy": 0.50, "health": 0.50},
    "health_monitoring":{"energy": 0.50, "health": 0.50},
    "discoverability":  {"energy": 0.34, "link_quality": 0.33, "health": 0.33},
}

SUPPORTED_ROLES = tuple(ROLE_WEIGHTS.keys())


class NodeAgent(mesa.Agent):
    """A single node in the physical mesh."""

    NODE_STATES = ["online", "failed"]
    NODE_TRANSITIONS = [
        {"trigger": "fail",    "source": "online", "dest": "failed"},
        {"trigger": "recover", "source": "failed", "dest": "online"},
    ]

    def __init__(self, model: mesa.Model, subnet_id: str):
        # Mesa 3.x assigns unique_id via the model; pass only `model`.
        super().__init__(model)

        self.subnet_id = subnet_id

        # Physical attributes, all normalized to [0, 1].
        # energy/health/link_quality are seeded by the model (topology/world);
        # centrality is computed from topology and passed in — never invented here.
        self.energy: float = 1.0
        self.energy_capacity: float = 1.0
        self.solar_harvest_rate: float = 0.0
        self.health: float = 1.0
        self.link_quality: float = 1.0
        self.centrality: float = 0.0

        # Operational state machine (spec §3.9 failure/recovery).
        self.machine = Machine(
            model=self,
            states=NodeAgent.NODE_STATES,
            transitions=NodeAgent.NODE_TRANSITIONS,
            initial="online",
            auto_transitions=False,
        )

    # ------------------------------------------------------------------
    # Capability (spec §3.2)
    # ------------------------------------------------------------------
    def capability(self, role: str) -> float:
        """C(e, r) = weighted sum of relevant attributes, in [0, 1].

        Returns 0.0 when the node is not online — a failed node contributes no
        capability, which is what invalidates its leases downstream (spec §3.9).
        """
        if self.state != "online":
            return 0.0

        weights = ROLE_WEIGHTS.get(role)
        if weights is None:
            raise ValueError(f"Unsupported role '{role}'. Supported: {SUPPORTED_ROLES}")

        attrs = {
            "energy": self.energy,
            "health": self.health,
            "link_quality": self.link_quality,
            "centrality": self.centrality,
        }

        value = sum(weights[attr] * attrs[attr] for attr in weights)
        return min(max(value, 0.0), 1.0)

    def capability_vector(self) -> dict[str, float]:
        """Capability across every supported role (used by aggregation)."""
        return {role: self.capability(role) for role in SUPPORTED_ROLES}

    # ------------------------------------------------------------------
    # Injected events (spec §4). The model calls these; the agent does not
    # mutate its own state passively.
    # ------------------------------------------------------------------
    def degrade_energy(self, amount: float) -> None:
        """Energy degradation event → capability decreases."""
        if amount < 0:
            raise ValueError("energy consumption must be non-negative")
        self.energy = min(max(self.energy - amount, 0.0), self.energy_capacity)

    def harvest_energy(self, amount: float) -> float:
        """Charge the battery, returning accepted energy after capacity limits."""
        if amount < 0:
            raise ValueError("harvested energy must be non-negative")
        self.energy = min(max(self.energy, 0.0), self.energy_capacity)
        accepted = min(amount, self.energy_capacity - self.energy)
        self.energy += accepted
        return accepted

    def degrade_link(self, amount: float) -> None:
        """Link degradation event → capability decreases."""
        self.link_quality = min(max(self.link_quality - amount, 0.0), 1.0)

    # `fail` and `recover` are provided by the transitions Machine as trigger
    # methods (self.fail(), self.recover()). They flip operational state only;
    # physical attributes are left to explicit events so recovery stays faithful
    # to whatever degradation schedule the experiment injected.

    def is_available(self) -> bool:
        return self.state == "online"

    # ------------------------------------------------------------------
    # Mesa step — intentionally a no-op for protocol purposes.
    # World dynamics (failures, degradation) are event-driven per spec §4;
    # keeping step() empty means steady-state behavior is fully reproducible.
    # ------------------------------------------------------------------
    def step(self) -> None:  # pragma: no cover - trivial
        pass


if __name__ == "__main__":
    # Minimal self-test proving capability + state-machine logic.
    class _DummyModel(mesa.Model):
        pass

    m = _DummyModel()
    n = NodeAgent(m, subnet_id="net0_subnet0")
    n.energy, n.health, n.link_quality, n.centrality = 0.9, 0.8, 0.7, 0.6

    print("online capabilities:", {r: round(n.capability(r), 3) for r in SUPPORTED_ROLES})

    n.degrade_energy(0.5)
    print("after energy -0.5 :", round(n.capability("gateway"), 3))

    n.fail()
    print(f"state={n.state}, gateway cap while failed = {n.capability('gateway')}")

    n.recover()
    print(f"recovered -> state={n.state}, gateway cap = {round(n.capability('gateway'), 3)}")
