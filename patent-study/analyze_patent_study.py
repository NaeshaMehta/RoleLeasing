"""Aggregate patent-study runs, paired confidence intervals, and plots."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import t

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ARMS = (
    "A_hierarchical_no_harvest",
    "B_proposed_no_harvest",
    "C_proposed_moderate_harvest",
    "D_proposed_harvest_gate",
)
SCENARIOS = ("normal", "node_failures", "energy_degradation", "link_degradation")
CONTRASTS = (
    ("B_proposed_no_harvest", "A_hierarchical_no_harvest", "B_minus_A"),
    ("C_proposed_moderate_harvest", "B_proposed_no_harvest", "C_minus_B"),
    ("D_proposed_harvest_gate", "C_proposed_moderate_harvest", "D_minus_C"),
    ("D_proposed_harvest_gate", "A_hierarchical_no_harvest", "D_minus_A"),
)
CONTINUOUS_METRICS = (
    "capability_service_continuity",
    "sensor_delivery_fraction",
    "sensor_items_generated",
    "sensor_items_delivered",
    "communication_energy_per_delivered_item",
    "total_modeled_energy_consumed",
    "average_remaining_energy",
    "control_messages",
    "message_hop_transmissions",
    "role_migrations",
    "average_role_recovery_time",
    "active_node_count_final",
)
LIFETIME_FIELDS = {
    "capability_service_continuity": (
        "capability_service_continuity_90_crossing_tick",
        "capability_service_continuity_90_right_censored",
    ),
    "capability_service_continuity_50": (
        "capability_service_continuity_50_crossing_tick",
        "capability_service_continuity_50_right_censored",
    ),
    "sensor_delivery_fraction": (
        "sensor_delivery_fraction_90_crossing_tick",
        "sensor_delivery_fraction_90_right_censored",
    ),
    "sensor_delivery_fraction_50": (
        "sensor_delivery_fraction_50_crossing_tick",
        "sensor_delivery_fraction_50_right_censored",
    ),
    "network_lifetime_50": ("network_lifetime", "network_lifetime_censored"),
}


def _load_runs(root: Path, first_seed: int, seed_count: int, steps: int):
    summaries, crossings = [], []
    timeseries_files = []
    for seed in range(first_seed, first_seed + seed_count):
        seed_dir = root / "runs" / f"seed_{seed}"
        summary_path = seed_dir / "per_run_metrics.csv"
        crossing_path = seed_dir / "threshold_crossings.csv"
        series_path = seed_dir / "timeseries.npz"
        if not all(path.is_file() for path in (summary_path, crossing_path, series_path)):
            raise FileNotFoundError(f"incomplete seed outputs: {seed_dir}")
        run_frame = pd.read_csv(summary_path)
        crossing_frame = pd.read_csv(crossing_path)
        if len(run_frame) != len(SCENARIOS) * len(ARMS):
            raise ValueError(f"wrong run count in {summary_path}")
        if len(crossing_frame) != len(SCENARIOS) * len(ARMS) * 5:
            raise ValueError(f"wrong threshold row count in {crossing_path}")
        with np.load(series_path) as archive:
            if not archive.files or any(len(archive[key]) != steps + 1 for key in archive.files):
                raise ValueError(f"wrong time-series length in {series_path}")
        summaries.append(run_frame)
        crossings.append(crossing_frame)
        timeseries_files.append(series_path)
    runs = pd.concat(summaries, ignore_index=True)
    crossing_data = pd.concat(crossings, ignore_index=True)
    expected = seed_count * len(SCENARIOS) * len(ARMS)
    if len(runs) != expected or runs.duplicated(["scenario", "arm", "seed"]).any():
        raise ValueError(f"expected {expected} unique matched runs")
    return runs, crossing_data, timeseries_files


def _paired_row(values: pd.Series, scenario: str, contrast: str, metric: str, unit: str):
    clean = values.dropna().astype(float)
    count = len(clean)
    mean = float(clean.mean()) if count else np.nan
    standard_error = float(clean.std(ddof=1) / np.sqrt(count)) if count > 1 else np.nan
    critical = float(t.ppf(0.975, count - 1)) if count > 1 else np.nan
    half_width = critical * standard_error if count > 1 else np.nan
    deviation = float(clean.std(ddof=1)) if count > 1 else np.nan
    return {
        "scenario": scenario,
        "contrast": contrast,
        "metric": metric,
        "paired_effect_mean": mean,
        "ci_95_lower": mean - half_width if count > 1 else np.nan,
        "ci_95_upper": mean + half_width if count > 1 else np.nan,
        "paired_standardized_effect": mean / deviation if deviation > 0 else np.nan,
        "paired_seed_count": count,
        "unit": unit,
    }


def _paired_comparisons(runs: pd.DataFrame, steps: int) -> pd.DataFrame:
    rows = []
    indexed = runs.set_index(["scenario", "seed", "arm"])
    for scenario in SCENARIOS:
        for arm_left, arm_right, contrast in CONTRASTS:
            left = indexed.xs((scenario, arm_left), level=("scenario", "arm")).sort_index()
            right = indexed.xs((scenario, arm_right), level=("scenario", "arm")).sort_index()
            for metric in CONTINUOUS_METRICS:
                rows.append(_paired_row(
                    left[metric] - right[metric],
                    scenario,
                    contrast,
                    metric,
                    "normalized_energy" if "energy" in metric else "count_or_fraction",
                ))
            for name, (time_column, censored_column) in LIFETIME_FIELDS.items():
                if name == "network_lifetime_50":
                    left_time = left[time_column]
                    right_time = right[time_column]
                    left_censored = left[censored_column].astype(bool)
                    right_censored = right[censored_column].astype(bool)
                else:
                    threshold = 0.5 if name.endswith("_50") else 0.9
                    metric_name = name.removesuffix("_50") if name.endswith("_50") else name
                    left_time_column = f"{metric_name}_{int(threshold * 100)}_crossing_tick"
                    left_censored_column = f"{metric_name}_{int(threshold * 100)}_right_censored"
                    left_time = left[left_time_column]
                    right_time = right[left_time_column]
                    left_censored = left[left_censored_column].astype(bool)
                    right_censored = right[left_censored_column].astype(bool)
                left_rmst = left_time.where(~left_censored, steps).fillna(steps)
                right_rmst = right_time.where(~right_censored, steps).fillna(steps)
                rows.append(_paired_row(
                    left_rmst - right_rmst,
                    scenario,
                    contrast,
                    f"restricted_mean_service_lifetime_{name}",
                    "ticks_restricted_to_horizon",
                ))
                rows.append(_paired_row(
                    left_censored.astype(float) - right_censored.astype(float),
                    scenario,
                    contrast,
                    f"right_censoring_fraction_{name}",
                    "fraction",
                ))
    return pd.DataFrame(rows)


def _aggregate_series(
    series_paths: list[Path],
    output_dir: Path,
    steps: int,
) -> None:
    aggregate: dict[str, list[np.ndarray]] = {}
    for path in series_paths:
        with np.load(path) as archive:
            for key in archive.files:
                aggregate.setdefault(key, []).append(archive[key].astype(float))

    def plot_mean(metric: str, title: str, filename: str, ylabel: str) -> None:
        figure, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True)
        time_axis = np.arange(steps + 1)
        for axis, scenario in zip(axes.flat, SCENARIOS):
            for arm in ARMS:
                key = f"{scenario}__{arm}__{metric}"
                values = np.vstack(aggregate[key])
                mean = np.nanmean(values, axis=0)
                if len(values) > 1:
                    half = t.ppf(0.975, len(values) - 1) * (
                        np.nanstd(values, axis=0, ddof=1) / np.sqrt(len(values))
                    )
                    axis.fill_between(time_axis, mean - half, mean + half, alpha=0.12)
                axis.plot(time_axis, mean, label=arm.removeprefix("_"))
            axis.set_title(scenario.replace("_", " "))
            axis.set_ylabel(ylabel)
            axis.set_xlabel("Simulation tick")
            axis.grid(True, alpha=0.25)
            axis.legend(fontsize="x-small")
        figure.suptitle(title)
        figure.tight_layout()
        figure.savefig(output_dir / filename, dpi=150)
        plt.close(figure)

    plot_mean(
        "cumulative_capability_service_continuity",
        "Capability-service continuity (cumulative fraction)",
        "capability_service_continuity.png",
        "Continuity",
    )
    plot_mean(
        "cumulative_sensor_delivery_fraction",
        "Sensor delivery (cumulative fraction)",
        "sensor_delivery.png",
        "Delivered / generated",
    )
    plot_mean(
        "mean_remaining_energy",
        "Mean residual battery energy",
        "residual_battery.png",
        "Normalized battery units",
    )
    plot_mean(
        "communication_energy_consumed_step",
        "Cumulative communication energy consumed",
        "communication_energy.png",
        "Normalized energy units",
    )
    plot_mean(
        "active_node_fraction",
        "Active-node fraction (network lifetime threshold = 50%)",
        "active_node_fraction.png",
        "Active nodes / total nodes",
    )


def _plot_lifetime(crossings: pd.DataFrame, output_dir: Path, steps: int) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True, sharey=True)
    for axis, scenario in zip(axes.flat, SCENARIOS):
        rows = crossings[
            (crossings["scenario"] == scenario)
            & (
                ((crossings["service_metric"] == "capability_service_continuity")
                 & (crossings["threshold"] == 0.9))
                | ((crossings["service_metric"] == "sensor_delivery_fraction")
                   & (crossings["threshold"] == 0.9))
            )
        ]
        for arm in ARMS:
            arm_rows = rows[rows["arm"] == arm]
            for metric, label, linestyle in (
                ("capability_service_continuity", "CSC < 90%", "-"),
                ("sensor_delivery_fraction", "Delivery < 90%", "--"),
            ):
                selected = arm_rows[arm_rows["service_metric"] == metric]
                durations = selected["crossing_tick"].fillna(steps).to_numpy(dtype=int)
                events = (~selected["right_censored"].astype(bool)).to_numpy()
                x, survival = _kaplan_meier(durations, events, steps)
                axis.step(
                    x,
                    survival,
                    where="post",
                    linestyle=linestyle,
                    label=f"{arm}: {label}",
                )
        axis.set_title(scenario.replace("_", " "))
        axis.set_ylabel("Probability service remains above threshold")
        axis.set_xlabel("Ticks (administratively censored at horizon)")
        axis.set_ylim(0, 1.02)
        axis.grid(True, alpha=0.25)
        axis.legend(fontsize="xx-small", ncol=2)
    figure.suptitle("Kaplan–Meier service-lifetime curves at the 90% thresholds")
    figure.tight_layout()
    figure.savefig(output_dir / "service_lifetime.png", dpi=150)
    plt.close(figure)


def _kaplan_meier(durations: np.ndarray, events: np.ndarray, horizon: int):
    survival = 1.0
    x_values = [0]
    y_values = [survival]
    for tick in sorted(set(durations[events])):
        at_risk = int(np.sum(durations >= tick))
        failures = int(np.sum((durations == tick) & events))
        if at_risk:
            survival *= 1.0 - failures / at_risk
        x_values.append(int(tick))
        y_values.append(survival)
    if x_values[-1] < horizon:
        x_values.append(horizon)
        y_values.append(survival)
    return np.asarray(x_values), np.asarray(y_values)


def _write_report(
    output_dir: Path,
    runs: pd.DataFrame,
    paired: pd.DataFrame,
    steps: int,
    first_seed: int,
    seed_count: int,
) -> None:
    means = runs.groupby(["scenario", "arm"])[
        [
            "capability_service_continuity",
            "sensor_delivery_fraction",
            "communication_energy_per_delivered_item",
            "total_modeled_energy_consumed",
            "average_remaining_energy",
            "role_migrations",
            "average_role_recovery_time",
        ]
    ].mean()
    comparison = paired[
        paired["metric"].isin((
            "capability_service_continuity",
            "sensor_delivery_fraction",
            "communication_energy_per_delivered_item",
            "total_modeled_energy_consumed",
            "restricted_mean_service_lifetime_capability_service_continuity",
            "restricted_mean_service_lifetime_sensor_delivery_fraction",
            "restricted_mean_service_lifetime_network_lifetime_50",
        ))
    ]
    manifest = (
        f"- Seeds: {first_seed}–{first_seed + seed_count - 1} ({seed_count})\n"
        f"- Horizon: {steps} steps\n"
        f"- Planned/completed runs: {seed_count * len(SCENARIOS) * len(ARMS)} / "
        f"{len(runs)}\n"
        "- Topology: existing 100-node clustered configuration; intercluster gap "
        "1.5 communication ranges; distance-energy weight 1; hierarchical "
        "backhaul enabled\n"
        "- Valid-lease retention: enabled in all arms\n"
        "- Harvest: moderate configured rate 0.0002 normalized units/node/tick; "
        "per-node seeded multiplier; battery capacity 1.0; reserve 0.1\n"
        "- Arm D gate: enabled with existing default horizon and safety margin; "
        "other arms gate disabled\n"
        "- Each seed/scenario event schedule and initial topology are matched "
        "across arms\n"
    )
    commands = f"""```powershell
& .\\.venv\\Scripts\\python.exe .\\patent-study\\run_patent_study.py --output .\\patent-study\\results_20000 --first-seed {first_seed} --seed-count {seed_count} --steps {steps} --workers 8
& .\\.venv\\Scripts\\python.exe .\\patent-study\\analyze_patent_study.py --output .\\patent-study\\results_20000 --first-seed {first_seed} --seed-count {seed_count} --steps {steps}
```"""
    report = f"""# Patent-Study Simulation Metrics

## Run manifest

{manifest}

## Per-arm mean metrics

{_markdown_table(means.reset_index())}

## Paired effects

Effects are paired mean differences (first arm minus second arm) with paired
95% t confidence intervals. Lifetime effects are restricted mean survival
time (RMST) through the administrative horizon; a run censored at the horizon
contributes survival only through that horizon, not an observed failure at
that time.

{_markdown_table(comparison)}

## Metric definitions and limits

- Capability-service continuity is available required role-time intervals
  divided by required role-time intervals. Initial time-zero state is excluded;
  each simulated tick contributes one interval per required role and scope.
- Sensor delivery is the explicit successfully delivered sensor-item count
  divided by the explicit generated sensor-item count. Unrouted generated
  items are included in the denominator.
- Communication energy per delivered item includes modeled control, sensor,
  and backhaul communication energy divided by delivered sensor items. It is
  undefined when no sensor item is delivered.
- Service threshold crossings are the first tick at which cumulative CSC or
  cumulative sensor-delivery fraction falls below 90% or 50%. No crossing
  during the horizon is marked right-censored in `threshold_crossings.csv`.
- Network lifetime retains the simulator's first crossing below its configured
  50% active-node threshold and its existing censor indicator.
- Energy values are normalized model units, not joules. The model omits
  sensing, computation, idle power, contention, retransmissions, and battery
  chemistry. The 20,000-step horizon does not establish field lifetime or
  patentability.

## Reproduction

{commands}

Outputs: `per_run_metrics.csv`, `paired_comparison.csv`,
`threshold_crossings.csv`, `final_report.md`, and PNG figures in this
directory. Per-seed resume data are under `runs/`.
"""
    (output_dir / "final_report.md").write_text(report, encoding="utf-8")


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    rows = [
        [str(value) if not pd.isna(value) else "—" for value in row]
        for row in frame.itertuples(index=False, name=None)
    ]
    widths = [
        max(len(columns[index]), *(len(row[index]) for row in rows))
        for index in range(len(columns))
    ]
    header = "| " + " | ".join(
        column.ljust(widths[index]) for index, column in enumerate(columns)
    ) + " |"
    separator = "| " + " | ".join("-" * width for width in widths) + " |"
    body = [
        "| " + " | ".join(
            value.ljust(widths[index]) for index, value in enumerate(row)
        ) + " |"
        for row in rows
    ]
    return "\n".join((header, separator, *body))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("patent-study/results_20000"))
    parser.add_argument("--first-seed", type=int, default=42)
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--steps", type=int, default=20_000)
    args = parser.parse_args()
    root = args.output.resolve()
    runs, crossings, series_paths = _load_runs(
        root,
        args.first_seed,
        args.seed_count,
        args.steps,
    )
    runs.to_csv(root / "per_run_metrics.csv", index=False)
    crossings.to_csv(root / "threshold_crossings.csv", index=False)
    paired = _paired_comparisons(runs, args.steps)
    paired.to_csv(root / "paired_comparison.csv", index=False)
    _aggregate_series(series_paths, root, args.steps)
    _plot_lifetime(crossings, root, args.steps)
    _write_report(root, runs, paired, args.steps, args.first_seed, args.seed_count)
    print(
        f"validated {len(runs)} runs, {len(crossings)} threshold records, "
        f"{len(series_paths)} seed time-series archives"
    )


if __name__ == "__main__":
    main()
