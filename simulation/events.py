"""Deterministic, replayable node events for simulation experiments."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulation.config import SCENARIOS, SimulationConfig
from simulation.entities import EntityHierarchy


@dataclass(frozen=True, order=True)
class SimulationEvent:
    tick: int
    node_id: int
    kind: str
    amount: float = 0.0

    def __post_init__(self) -> None:
        if self.tick < 1:
            raise ValueError("event tick must be >= 1")
        if self.kind not in {"fail", "recover", "degrade_energy", "degrade_link"}:
            raise ValueError(f"unsupported event kind: {self.kind}")
        if self.kind.startswith("degrade_") and not 0.0 <= self.amount <= 1.0:
            raise ValueError("degradation amount must be within [0, 1]")


def generate_event_schedule(
    scenario: str,
    config: SimulationConfig,
    seed: int | None = None,
) -> tuple[SimulationEvent, ...]:
    """Generate one immutable event schedule to replay across protocol modes."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    if scenario == "normal":
        return ()

    rng = np.random.default_rng(config.seed if seed is None else seed)
    selected_count = max(1, min(config.num_nodes // 10, 10))
    selected = sorted(
        int(node_id) for node_id in rng.choice(config.num_nodes, size=selected_count, replace=False)
    )
    first_tick = max(1, config.steps // 4)
    middle_tick = max(1, config.steps // 2)
    last_tick = max(first_tick + 1, (3 * config.steps) // 4)
    last_tick = min(config.steps, last_tick)

    events: list[SimulationEvent] = []
    if scenario == "node_failures":
        events.extend(SimulationEvent(first_tick, node_id, "fail") for node_id in selected)
        if last_tick > first_tick:
            events.extend(SimulationEvent(last_tick, node_id, "recover") for node_id in selected)
    elif scenario == "energy_degradation":
        events.extend(SimulationEvent(first_tick, node_id, "degrade_energy", 0.15) for node_id in selected)
        events.extend(SimulationEvent(middle_tick, node_id, "degrade_energy", 0.15) for node_id in selected)
    else:
        events.extend(SimulationEvent(first_tick, node_id, "degrade_link", 0.4) for node_id in selected)
        events.extend(SimulationEvent(middle_tick, node_id, "degrade_link", 0.4) for node_id in selected)

    return tuple(sorted(events))


def apply_event(event: SimulationEvent, hierarchy: EntityHierarchy) -> bool:
    """Apply a single event; return whether it changed the node's state."""
    try:
        node = hierarchy.nodes_by_id[event.node_id]
    except KeyError as exc:
        raise ValueError(f"event references unknown node {event.node_id}") from exc

    if event.kind == "fail":
        if not node.is_available():
            return False
        node.fail()
    elif event.kind == "recover":
        if node.is_available():
            return False
        node.recover()
    elif event.kind == "degrade_energy":
        previous = node.energy
        node.degrade_energy(event.amount)
        return node.energy != previous
    else:
        previous = node.link_quality
        node.degrade_link(event.amount)
        return node.link_quality != previous
    return True
