"""Command-line entry point for the simulation experiment matrix."""

from __future__ import annotations

import argparse
from pathlib import Path

from simulation.config import PROTOCOLS, SCENARIOS, SimulationConfig
from simulation.experiments import run_experiment_matrix


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run matched hierarchical-routing and role-leasing simulation experiments."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--protocols", nargs="+", choices=PROTOCOLS, default=list(PROTOCOLS))
    parser.add_argument("--nodes-per-subnet", type=int, default=10)
    parser.add_argument("--intercluster-gap-in-ranges", type=float, default=0.0)
    parser.add_argument("--distance-energy-weight", type=float, default=0.0)
    parser.add_argument("--hierarchical-backhaul", action="store_true")
    parser.add_argument("--retain-valid-leases-on-epoch", action="store_true")
    parser.add_argument("--capability-reassessment-interval-steps", type=int, default=1)
    parser.add_argument("--capability-broadcast-interval-steps", type=int, default=0)
    parser.add_argument("--hysteresis-delta", type=float, default=0.05)
    parser.add_argument("--reassess-affected-scopes-only", action="store_true")
    parser.add_argument("--capability-change-threshold", type=float, default=0.02)
    parser.add_argument("--migration-cooldown-steps", type=int, default=0)
    parser.add_argument("--adaptive-hysteresis", action="store_true")
    parser.add_argument("--batch-control-updates", action="store_true")
    parser.add_argument("--lease-min-duration", type=float, default=10.0)
    parser.add_argument("--lease-max-duration", type=float, default=100.0)
    parser.add_argument("--lease-renewal-fraction", type=float, default=0.7)
    parser.add_argument("--battery-capacity", type=float, default=1.0)
    parser.add_argument("--solar-harvest-rate", type=float, default=0.0)
    parser.add_argument("--solar-migration-gate", action="store_true")
    parser.add_argument("--minimum-energy-reserve", type=float, default=0.1)
    parser.add_argument("--solar-decision-horizon-steps", type=int, default=500)
    parser.add_argument("--solar-migration-safety-margin", type=float, default=0.01)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = SimulationConfig(
        seed=args.seed,
        steps=args.steps,
        nodes_per_subnet=args.nodes_per_subnet,
        intercluster_gap_in_ranges=args.intercluster_gap_in_ranges,
        distance_energy_weight=args.distance_energy_weight,
        hierarchical_backhaul=args.hierarchical_backhaul,
        retain_valid_leases_on_epoch=args.retain_valid_leases_on_epoch,
        capability_reassessment_interval_steps=args.capability_reassessment_interval_steps,
        capability_broadcast_interval_steps=args.capability_broadcast_interval_steps,
        hysteresis_delta=args.hysteresis_delta,
        reassess_affected_scopes_only=args.reassess_affected_scopes_only,
        capability_change_threshold=args.capability_change_threshold,
        migration_cooldown_steps=args.migration_cooldown_steps,
        adaptive_hysteresis=args.adaptive_hysteresis,
        batch_control_updates=args.batch_control_updates,
        lease_min_duration=args.lease_min_duration,
        lease_max_duration=args.lease_max_duration,
        lease_renewal_fraction=args.lease_renewal_fraction,
        battery_capacity=args.battery_capacity,
        solar_harvest_rate=args.solar_harvest_rate,
        solar_migration_gate=args.solar_migration_gate,
        minimum_energy_reserve=args.minimum_energy_reserve,
        solar_decision_horizon_steps=args.solar_decision_horizon_steps,
        solar_migration_safety_margin=args.solar_migration_safety_margin,
    )
    summary = run_experiment_matrix(
        config=config,
        output_dir=args.output,
        scenarios=args.scenarios,
        protocols=args.protocols,
    )
    print(summary.to_string(index=False))
    print(f"\nCSV and plots written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
