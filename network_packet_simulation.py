"""Two-stage role-leasing packet comparison. Run --help for examples."""

from __future__ import annotations

import argparse
from pathlib import Path

from packet_simulation.analytics import analyze_csv
from packet_simulation.config import PacketConfig, PROTOCOLS, SCENARIOS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("simulate", "analyze", "all"), default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("packet_simulation_output"))
    parser.add_argument("--raw", type=Path, help="Override input/output raw CSV path")
    parser.add_argument("--final", type=Path, help="Override final analytics CSV path")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--protocols", nargs="+", choices=PROTOCOLS, default=list(PROTOCOLS))
    parser.add_argument("--duration", type=float, default=30.0, help="Observation duration in seconds")
    parser.add_argument("--nodes-per-subnet", type=int, default=10, help="10 subnets; default total 100 nodes")
    parser.add_argument("--packet-interval", type=float, default=5.0, help="Seconds between readings per node")
    parser.add_argument("--bandwidth", type=float, default=64000, help="Each physical link's bit/s")
    parser.add_argument("--queue-capacity", type=int, default=12, help="Waiting packets per shared link")
    args = parser.parse_args(argv)
    raw = args.raw or args.output_dir / "raw_simulation_events.csv"
    final = args.final or args.output_dir / "final_network_analytics.csv"
    if raw.resolve() == final.resolve():
        parser.error("raw and final paths must differ")
    try:
        if args.stage in ("simulate", "all"):
            from packet_simulation.model import run_simulation
            config = PacketConfig(duration_s=args.duration, nodes_per_subnet=args.nodes_per_subnet,
                                  packet_interval_s=args.packet_interval, bandwidth_bps=args.bandwidth,
                                  queue_capacity=args.queue_capacity)
            run_simulation(raw, config, args.seeds, args.scenarios, args.protocols)
            print(f"Raw simulation events: {raw.resolve()}")
        if args.stage in ("analyze", "all"):
            analyze_csv(raw, final)
            print(f"Final network analytics: {final.resolve()}")
    except ModuleNotFoundError as exc:
        parser.exit(1, f"Error: {exc}\nInstall the simulation dependency with: python -m pip install -r packet_simulation/requirements.txt\n")
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
