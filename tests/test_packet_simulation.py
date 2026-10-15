"""Independent numerical oracles and end-to-end checks for the packet extension."""

import ast
import csv
import json
import math
import tempfile
import unittest
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from packet_simulation.analytics import analyze_csv, integrate_states
from packet_simulation.config import PacketConfig, ROLE_WEIGHTS
from packet_simulation.model import EVENT_COLUMNS, run_simulation


def load(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def temporary_directory():
    root = Path(__file__).resolve().parents[1] / ".packet_qa"
    root.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


class PacketStudyTests(unittest.TestCase):
    def test_role_weights_match_existing_project(self):
        tree = ast.parse(Path("nodes.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.AnnAssign)
                    and isinstance(n.target, ast.Name) and n.target.id == "ROLE_WEIGHTS")
        self.assertEqual(ast.literal_eval(node.value), ROLE_WEIGHTS)

    def test_state_integral_including_cutoff_and_same_timestamp(self):
        self.assertAlmostEqual(integrate_states([(0, 0), (.1, 2), (.3, 1), (.5, 0)], 1), .6)
        self.assertEqual(integrate_states([(0, 1), (.5, 0), (.5, 1)], 1), 1)
        with self.assertRaises(ValueError):
            integrate_states([(.8, 1), (.3, 0)], 1)

    def fixture(self, path, censor=False):
        config = PacketConfig(duration_s=1, subnet_counts=(1,), nodes_per_subnet=2,
                              packet_size_bytes=100)
        events = []
        def add(time, event, **fields):
            events.append(dict(timestamp_s=time, event=event, **fields))
        add(0, "RUN_START", details_json=json.dumps({"config": asdict(config), "roles": 1}))
        for i in (0, 1):
            add(0, "NODE_INIT", node_id=i, energy=1)
        add(0, "ACTIVE_COUNT", details_json=json.dumps({"active": 2}))
        add(0, "ROLE_STATE", role="gateway", scope="subnet_0", available=1)
        add(0, "QUEUE_STATE", link_id="0-1", queue_size=0, busy=0)
        add(.1, "QUEUE_STATE", link_id="0-1", queue_size=2, busy=1)
        add(.3, "QUEUE_STATE", link_id="0-1", queue_size=1, busy=1)
        add(.5, "QUEUE_STATE", link_id="0-1", queue_size=0, busy=0)
        for packet, created, terminal, end in (("a", .1, "PACKET_DELIVERED", .4),
                                                ("b", .2, "PACKET_DELIVERED", .6),
                                                ("c", .3, "PACKET_CENSORED" if censor else "PACKET_DROPPED", 1 if censor else .5)):
            fields = dict(packet_id=packet, packet_type="data", source=0, size_bytes=100, created_s=created)
            add(created, "PACKET_GENERATED", **fields)
            add(end, terminal, latency_s=end-created, drop_reason="link_loss" if terminal == "PACKET_DROPPED" else "", **fields)
        add(.2, "ROLE_STATE", role="gateway", scope="subnet_0", available=0)
        add(.7, "ROLE_STATE", role="gateway", scope="subnet_0", available=1)
        add(.7, "ROLE_RECOVERED", role="gateway", scope="subnet_0", latency_s=.5,
            details_json='{"cause":"holder_failure"}')
        add(.7, "ENERGY_CHANGE", node_id=0, energy_delta=.1, details_json='{"cause":"tx"}')
        add(.7, "ENERGY_CHANGE", node_id=1, energy_delta=.2, details_json='{"cause":"rx"}')
        add(1, "NODE_SAMPLE", node_id=0, energy=.9)
        add(1, "NODE_SAMPLE", node_id=1, energy=.8)
        add(1, "RUN_END")
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
            writer.writeheader()
            for sequence, row in enumerate(sorted(events, key=lambda row: row["timestamp_s"]), 1):
                writer.writerow(dict(run_id="normal:static:1", scenario="normal", protocol="static",
                                     seed=1, event_seq=sequence, **row))

    def test_analytics_against_hand_calculated_trace(self):
        with temporary_directory() as folder:
            raw, final = Path(folder)/"raw.csv", Path(folder)/"final.csv"
            self.fixture(raw)
            analyze_csv(raw, final)
            rows = load(final)
            values = {r["metric"]: float(r["value"]) for r in rows
                      if r["record_type"] == "run" and not r["entity"] and r["value"]}
            for metric, expected in {
                "offered_data_packets": 3, "delivered_data_packets": 2,
                "average_latency_s": .35, "jitter_s": .1, "drop_rate": 1/3,
                "throughput_bps": 1600, "role_availability": .5,
                "average_role_recovery_time_s": .5, "average_remaining_energy": .85,
                "energy_variance": .0025, "communication_energy_consumed": .3,
                "network_lifetime_censored": 1,
            }.items():
                self.assertAlmostEqual(values[metric], expected, msg=metric)
            link = {r["metric"]: float(r["value"]) for r in rows
                    if r["record_type"] == "run" and r["entity"] == "0-1"}
            self.assertAlmostEqual(link["link_mean_queue"], .6)
            self.assertAlmostEqual(link["link_utilization"], .4)
            self.assertEqual(link["link_max_queue"], 2)

    def test_cutoff_is_not_counted_as_a_drop(self):
        with temporary_directory() as folder:
            raw, final = Path(folder)/"raw.csv", Path(folder)/"final.csv"
            self.fixture(raw, censor=True)
            analyze_csv(raw, final)
            rows = {r["metric"]: r for r in load(final) if r["record_type"] == "run" and not r["entity"]}
            self.assertEqual(float(rows["drop_rate"]["value"]), 0)
            self.assertEqual(float(rows["censored_data_packets"]["value"]), 1)

    def test_rejects_truncated_or_duplicate_packet_logs(self):
        with temporary_directory() as folder:
            raw, final = Path(folder)/"raw.csv", Path(folder)/"final.csv"
            self.fixture(raw)
            rows = load(raw)
            def write(rows):
                with raw.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
                    writer.writeheader()
                    writer.writerows(rows)
            write(rows[:-1])
            with self.assertRaisesRegex(ValueError, "incomplete"):
                analyze_csv(raw, final)
            duplicate = next(dict(r) for r in rows if r["event"] == "PACKET_DELIVERED")
            rows.insert(-1, duplicate)
            for sequence, row in enumerate(rows, 1):
                row["event_seq"] = sequence
            write(rows)
            with self.assertRaises(ValueError):
                analyze_csv(raw, final)

    def test_matched_comparison_and_epoch_fencing(self):
        config = PacketConfig(duration_s=6, subnet_counts=(1,), nodes_per_subnet=3,
                              epoch_s=2, evaluation_s=.25, detection_s=.5,
                              lease_min_s=1, lease_max_s=2, packet_interval_s=.5,
                              bandwidth_bps=1000000, base_link_loss=0, quality_loss_weight=0)
        with temporary_directory() as folder:
            raw, final = Path(folder)/"raw.csv", Path(folder)/"final.csv"
            run_simulation(raw, config, seeds=(8, 9), scenarios=("normal", "node_failures"))
            analyze_csv(raw, final)
            runs = defaultdict(list)
            for row in load(raw):
                runs[row["run_id"]].append(row)
            self.assertEqual(len(runs), 12)
            for seed in (8, 9):
                for scenario in ("normal", "node_failures"):
                    offered, states, disturbances = [], [], []
                    for protocol in ("static", "dynamic", "proposed"):
                        rows = runs[f"{scenario}:{protocol}:{seed}"]
                        offered.append([(r["packet_id"], r["timestamp_s"], r["size_bytes"])
                                        for r in rows if r["event"] == "PACKET_GENERATED" and r["packet_type"] == "data"])
                        states.append([(r["node_id"], r["energy"], r["details_json"])
                                       for r in rows if r["event"] == "NODE_INIT"])
                        disturbances.append([(r["node_id"], r["timestamp_s"], json.loads(r["details_json"])["kind"])
                                             for r in rows if r["event"] == "DISTURBANCE"])
                        active = {}
                        for row in rows:
                            key = (row["role"], row["scope"])
                            if row["event"] in ("LEASE_EXPIRE", "LEASE_VALIDITY_ENDED", "ASSIGNMENT_RELEASED"):
                                active.pop(key, None)
                            if row["event"] in ("LEASE_ACTIVATED", "ASSIGNMENT_ACTIVATED"):
                                # An invalid/failed prior lease may be overwritten by recovery;
                                # each activation remains a single dictionary entry per key.
                                active[key] = row["holder"]
                                if protocol == "proposed":
                                    self.assertEqual(int(row["epoch"]), int(float(row["timestamp_s"]) // config.epoch_s))
                                    self.assertGreater(float(row["expiry_s"]), float(row["timestamp_s"]))
                        for edge_row in (r for r in rows if r["event"] == "QUEUE_STATE"):
                            self.assertLessEqual(int(edge_row["queue_size"]), config.queue_capacity)
                            self.assertIn(int(edge_row["busy"]), (0, 1))
                    self.assertEqual(offered[0], offered[1])
                    self.assertEqual(offered[1], offered[2])
                    self.assertEqual(states[0], states[2])
                    self.assertEqual(disturbances[0], disturbances[2])
            analytics = load(final)
            for row in analytics:
                if row["record_type"] == "paired_difference" and row["value"]:
                    metric = row["metric"]
                    def lookup(protocol, seed):
                        value = next(r["value"] for r in analytics if r["record_type"] == "run"
                                    and r["scenario"] == row["scenario"] and r["metric"] == metric
                                    and r["protocol"] == protocol and r["seed"] == str(seed))
                        return float(value) if value else None
                    pairs = [(lookup(row["protocol"], seed), lookup(row["baseline"], seed)) for seed in (8, 9)]
                    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
                    expected = sum(a - b for a, b in pairs) / len(pairs)
                    self.assertAlmostEqual(float(row["value"]), expected)

    def test_congestion_produces_real_queue_overflow_and_censoring(self):
        config = PacketConfig(duration_s=1, subnet_counts=(1,), nodes_per_subnet=6,
                              bandwidth_bps=200, queue_capacity=0, packet_interval_s=.05,
                              base_link_loss=0, quality_loss_weight=0)
        with temporary_directory() as folder:
            raw, final = Path(folder)/"raw.csv", Path(folder)/"final.csv"
            run_simulation(raw, config, seeds=(2,), scenarios=("normal",), protocols=("dynamic",))
            analyze_csv(raw, final)
            events = load(raw)
            self.assertTrue(any(r["event"] == "QUEUE_DROP" for r in events))
            self.assertTrue(any(r["event"] == "PACKET_CENSORED" for r in events))

    def test_repeatable_bytes_and_invalid_parameters(self):
        config = PacketConfig(duration_s=2, subnet_counts=(1,), nodes_per_subnet=3)
        with temporary_directory() as folder:
            paths = [Path(folder)/"a.csv", Path(folder)/"b.csv"]
            for path in paths:
                run_simulation(path, config, seeds=(1,), scenarios=("normal",), protocols=("proposed",))
            self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())
            with self.assertRaises(ValueError):
                run_simulation(paths[0], config, seeds=(1, 1))
        for settings in ({"duration_s": math.inf}, {"queue_capacity": -1}, {"bandwidth_bps": 0}):
            with self.assertRaises(ValueError):
                PacketConfig(**settings)


if __name__ == "__main__":
    unittest.main()
