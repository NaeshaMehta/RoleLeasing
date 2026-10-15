"""Run the matched four-arm patent-study metric experiment."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import gc
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.config import SimulationConfig
from simulation.events import generate_event_schedule
from simulation.runner import RoleSimulationModel


SCENARIO_NAMES = ("normal", "node_failures", "energy_degradation", "link_degradation")
ARM_PROTOCOLS = {
    "A_hierarchical_no_harvest": ("hierarchical", 0.0, False),
    "B_proposed_no_harvest": ("proposed", 0.0, False),
    "C_proposed_moderate_harvest": ("proposed", 0.0002, False),
    "D_proposed_harvest_gate": ("proposed", 0.0002, True),
}
SERIES_COLUMNS = (
    "cumulative_capability_service_continuity",
    "cumulative_sensor_delivery_fraction",
    "mean_remaining_energy",
    "communication_energy_consumed_step",
    "active_node_fraction",
)


def run_seed(seed: int, output_root: Path, steps: int) -> int:
    seed_dir = output_root / "runs" / f"seed_{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    base = SimulationConfig(
        seed=seed,
        steps=steps,
        intercluster_gap_in_ranges=1.5,
        distance_energy_weight=1.0,
        hierarchical_backhaul=True,
        retain_valid_leases_on_epoch=True,
    )
    schedules = {
        scenario: generate_event_schedule(scenario, base, seed=seed)
        for scenario in SCENARIO_NAMES
    }
    summaries: list[dict[str, object]] = []
    crossings: list[dict[str, object]] = []
    series: dict[str, np.ndarray] = {}

    for scenario in SCENARIO_NAMES:
        for arm, (protocol, harvest_rate, gate_enabled) in ARM_PROTOCOLS.items():
            config = replace(
                base,
                solar_harvest_rate=harvest_rate,
                solar_migration_gate=gate_enabled,
            )
            model = RoleSimulationModel(
                config=config,
                protocol=protocol,
                scenario=scenario,
                event_schedule=schedules[scenario],
            )
            model.run_steps()
            summary = model.metrics.summary(scenario, seed)
            summary["arm"] = arm
            summary["solar_migration_gate"] = gate_enabled
            summaries.append(summary)

            for metric, threshold in (
                ("capability_service_continuity", 0.9),
                ("capability_service_continuity", 0.5),
                ("sensor_delivery_fraction", 0.9),
                ("sensor_delivery_fraction", 0.5),
            ):
                crossing_tick = model.metrics.service_lifetime_crossings.get(
                    (metric, threshold)
                )
                crossings.append({
                    "scenario": scenario,
                    "arm": arm,
                    "seed": seed,
                    "service_metric": metric,
                    "threshold": threshold,
                    "crossing_tick": crossing_tick,
                    "right_censored": crossing_tick is None,
                    "censoring_horizon": steps if crossing_tick is None else None,
                })
            network_tick = model.network_lifetime_tick
            crossings.append({
                "scenario": scenario,
                "arm": arm,
                "seed": seed,
                "service_metric": "active_node_fraction",
                "threshold": config.minimum_active_fraction,
                "crossing_tick": network_tick,
                "right_censored": network_tick is None,
                "censoring_horizon": steps if network_tick is None else None,
            })

            frame = model.metrics.timeseries_frame()
            for column in SERIES_COLUMNS:
                values = frame[column].to_numpy(dtype=float)
                if column == "communication_energy_consumed_step":
                    values = np.cumsum(values)
                series[f"{scenario}__{arm}__{column}"] = values
            del model
            del frame
            gc.collect()

    pd.DataFrame(summaries).to_csv(seed_dir / "per_run_metrics.csv", index=False)
    pd.DataFrame(crossings).to_csv(seed_dir / "threshold_crossings.csv", index=False)
    np.savez_compressed(seed_dir / "timeseries.npz", **series)
    return seed


def _seed_complete(seed_dir: Path, steps: int) -> bool:
    summary_path = seed_dir / "per_run_metrics.csv"
    crossing_path = seed_dir / "threshold_crossings.csv"
    series_path = seed_dir / "timeseries.npz"
    if not all(path.is_file() for path in (summary_path, crossing_path, series_path)):
        return False
    try:
        summary = pd.read_csv(summary_path)
        crossings = pd.read_csv(crossing_path)
        with np.load(series_path) as archive:
            return (
                len(summary) == len(SCENARIO_NAMES) * len(ARM_PROTOCOLS)
                and len(crossings) == len(SCENARIO_NAMES) * len(ARM_PROTOCOLS) * 5
                and len(archive.files) == (
                    len(SCENARIO_NAMES) * len(ARM_PROTOCOLS) * len(SERIES_COLUMNS)
                )
                and all(len(archive[key]) == steps + 1 for key in archive.files)
            )
    except (OSError, ValueError, KeyError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("patent-study/results_20000"))
    parser.add_argument("--first-seed", type=int, default=42)
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--steps", type=int, default=20_000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    pending = [
        seed
        for seed in range(args.first_seed, args.first_seed + args.seed_count)
        if not _seed_complete(output_root / "runs" / f"seed_{seed}", args.steps)
    ]
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(run_seed, seed, output_root, args.steps)
                for seed in pending
            ]
            for future in as_completed(futures):
                print(f"completed seed {future.result()}", flush=True)
    else:
        print("all requested seed outputs are already complete", flush=True)
    print(
        "Run aggregation with: "
        f".\\.venv\\Scripts\\python.exe .\\patent-study\\analyze_patent_study.py "
        f"--output {output_root} --first-seed {args.first_seed} "
        f"--seed-count {args.seed_count} --steps {args.steps}",
        flush=True,
    )


if __name__ == "__main__":
    main()
