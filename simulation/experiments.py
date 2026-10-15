"""Run matched scenario/protocol experiments and write reusable result files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from simulation.config import PROTOCOLS, SCENARIOS, SimulationConfig
from simulation.events import SimulationEvent, generate_event_schedule
from simulation.runner import RoleSimulationModel


def run_experiment_matrix(
    config: SimulationConfig,
    output_dir: str | Path,
    scenarios: Iterable[str] = SCENARIOS,
    protocols: Iterable[str] = PROTOCOLS,
    schedules: dict[str, tuple[SimulationEvent, ...]] | None = None,
) -> pd.DataFrame:
    """Run each protocol against identical scenario worlds and event schedules."""
    scenario_list = tuple(scenarios)
    protocol_list = tuple(protocols)
    invalid_scenarios = set(scenario_list) - set(SCENARIOS)
    invalid_protocols = set(protocol_list) - set(PROTOCOLS)
    if invalid_scenarios:
        raise ValueError(f"unknown scenarios: {sorted(invalid_scenarios)}")
    if invalid_protocols:
        raise ValueError(f"unknown protocols: {sorted(invalid_protocols)}")
    if not scenario_list or not protocol_list:
        raise ValueError("at least one scenario and protocol are required")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    timeseries_dir = root / "timeseries"
    migration_dir = root / "migrations"
    gateway_dir = root / "gateway_loads"
    for directory in (timeseries_dir, migration_dir, gateway_dir):
        directory.mkdir(exist_ok=True)

    schedule_map = schedules or {
        scenario: generate_event_schedule(scenario, config, seed=config.seed)
        for scenario in scenario_list
    }
    missing = set(scenario_list) - set(schedule_map)
    if missing:
        raise ValueError(f"event schedules missing scenarios: {sorted(missing)}")

    summary_rows: list[dict[str, object]] = []
    scenario_frames: dict[tuple[str, str], pd.DataFrame] = {}
    for scenario in scenario_list:
        for protocol in protocol_list:
            model = RoleSimulationModel(
                config=config,
                protocol=protocol,
                scenario=scenario,
                event_schedule=schedule_map[scenario],
            )
            model.run_steps()
            summary_rows.append(model.metrics.summary(scenario, config.seed))

            stem = f"{scenario}_{protocol}"
            timeseries = model.metrics.timeseries_frame()
            timeseries.insert(0, "scenario", scenario)
            timeseries.insert(2, "seed", config.seed)
            timeseries.to_csv(timeseries_dir / f"{stem}_timeseries.csv", index=False)
            scenario_frames[(scenario, protocol)] = timeseries

            migrations = model.metrics.migration_frame()
            migrations.insert(0, "scenario", scenario)
            migrations.insert(1, "protocol", protocol)
            migrations.insert(2, "seed", config.seed)
            migrations.to_csv(migration_dir / f"{stem}_migrations.csv", index=False)

            gateway_loads = model.metrics.gateway_load_frame()
            gateway_loads.insert(0, "scenario", scenario)
            gateway_loads.insert(2, "seed", config.seed)
            gateway_loads.to_csv(gateway_dir / f"{stem}_gateway_loads.csv", index=False)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(root / "summary.csv", index=False)
    _plot_scenario_timeseries(scenario_frames, scenario_list, protocol_list, root)
    _plot_summary(summary, root)
    return summary


def _plot_scenario_timeseries(
    frames: dict[tuple[str, str], pd.DataFrame],
    scenarios: tuple[str, ...],
    protocols: tuple[str, ...],
    output_dir: Path,
) -> None:
    metrics = (
        ("mean_remaining_energy", "Mean remaining energy"),
        ("communication_energy_consumed_step", "Communication energy per step"),
        ("gateway_energy_consumed_step", "Gateway energy per step"),
        ("control_messages_total", "Cumulative control messages"),
        ("role_availability", "Role availability"),
        ("active_node_count", "Active nodes"),
        ("role_migrations", "Cumulative role migrations"),
        ("gateway_load_variance", "Gateway load variance"),
    )
    for scenario in scenarios:
        figure, axes = plt.subplots(2, 4, figsize=(18, 8))
        for axis, (column, title) in zip(axes.flat, metrics):
            for protocol in protocols:
                frame = frames[(scenario, protocol)]
                axis.plot(frame["time"], frame[column], label=protocol)
            axis.set_title(title)
            axis.set_xlabel("Simulation step")
            axis.grid(True, alpha=0.25)
        axes.flat[0].legend()
        figure.suptitle(f"Scenario: {scenario}")
        figure.tight_layout()
        figure.savefig(output_dir / f"{scenario}_timeseries.png", dpi=140)
        plt.close(figure)


def _plot_summary(summary: pd.DataFrame, output_dir: Path) -> None:
    metrics = (
        ("network_lifetime", "Network lifetime (censored at horizon)"),
        ("role_migrations", "Role migrations"),
        ("control_messages", "Control messages"),
        ("communication_energy_consumed", "Communication energy"),
        ("gateway_energy_consumed", "Gateway energy"),
        ("average_remaining_energy", "Average remaining energy"),
        ("average_role_recovery_time", "Mean role recovery time"),
        ("failed_unavailable_roles_final", "Unavailable roles at end"),
        ("message_hop_transmissions", "Message-hop transmissions"),
        ("gateway_load_variance_mean", "Mean gateway-load variance"),
        ("sensor_data_delivery_fraction", "Sensor-data delivery fraction"),
    )
    scenarios = tuple(summary["scenario"].drop_duplicates())
    figure, axes = plt.subplots(3, 4, figsize=(18, 12))
    for axis, (column, title) in zip(axes.flat, metrics):
        pivot = summary.pivot(index="scenario", columns="protocol", values=column).reindex(scenarios)
        pivot.plot(kind="bar", ax=axis, legend=False)
        axis.set_title(title)
        axis.set_xlabel("")
        axis.tick_params(axis="x", rotation=35)
        axis.grid(True, axis="y", alpha=0.25)
    axes.flat[0].legend(loc="best", fontsize="small")
    figure.tight_layout()
    figure.savefig(output_dir / "summary_comparison.png", dpi=140)
    plt.close(figure)
