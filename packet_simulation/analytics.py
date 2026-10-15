"""Stage 2: derive every result from the closed raw CSV, never model objects.

Streaming at run granularity bounds memory to one experiment. Only Python's
standard library is required, so analytics can run separately without SimPy.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path

SUMMARY_COLUMNS = (
    "record_type", "scenario", "protocol", "seed", "baseline", "metric", "entity",
    "value", "unit", "seed_count", "stddev", "standard_error", "baseline_mean",
    "relative_change_pct", "censored_runs", "definition",
)


def mean_or_none(values):
    return statistics.fmean(values) if values else None


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    left, right = math.floor(position), math.ceil(position)
    return values[left] + (values[right] - values[left]) * (position - left)


def integrate_states(events, end, initial=0.0):
    """Exact left-continuous state integral; preserve CSV order for ties."""
    previous_t, state, area = 0.0, initial, 0.0
    for time, new_state in events:
        if not previous_t <= time <= end:
            raise ValueError("state timestamps outside observation window or out of order")
        area += (time - previous_t) * state
        previous_t, state = time, new_state
    return area + (end - previous_t) * state


class RunAnalytics:
    def __init__(self, first):
        metadata = json.loads(first["details_json"])
        self.cfg = metadata["config"]
        self.duration = self.cfg["duration_s"]
        self.role_count = metadata["roles"]
        self.identity = {key: first[key] for key in ("scenario", "protocol", "seed")}
        self.run_id = first["run_id"]
        self.last_seq = 0
        self.last_time = 0.0
        self.ends = 0
        self.generated, self.terminal = {}, {}
        self.latencies, self.flows, self.queue_waits = [], defaultdict(list), []
        self.bytes_delivered = 0
        self.counts = Counter()
        self.initial_energy, self.final_energy = {}, {}
        self.active_events = []
        self.role_events = defaultdict(list)
        self.recoveries, self.unresolved = [], 0
        self.fault_recoveries, self.unresolved_faults = [], 0
        self.loads = Counter()
        self.links = defaultdict(lambda: {"queue": [], "busy": [], "max_queue": 0,
                                          "drops": 0, "bytes": 0, "waits": []})
        self.radio_energy = self.degradation_energy = 0.0

    def consume(self, row):
        event, time = row["event"], float(row["timestamp_s"])
        seq = int(row["event_seq"])
        if seq != self.last_seq + 1 or time < self.last_time or not 0 <= time <= self.duration:
            raise ValueError(f"invalid event ordering in {self.run_id}")
        self.last_seq, self.last_time = seq, time
        self.counts[event] += 1
        packet_id = row["packet_id"]
        if event == "PACKET_GENERATED":
            if packet_id in self.generated:
                raise ValueError(f"duplicate generated packet {packet_id}")
            self.generated[packet_id] = (row["packet_type"], time, int(row["size_bytes"]))
            if row["packet_type"] == "control":
                self.counts["control_messages"] += 1
        elif event in ("PACKET_DELIVERED", "PACKET_DROPPED", "PACKET_CENSORED"):
            if packet_id not in self.generated or packet_id in self.terminal:
                raise ValueError(f"unknown or duplicate packet termination {packet_id}")
            self.terminal[packet_id] = event
            kind, created, size = self.generated[packet_id]
            self.counts[f"{kind}:{event}"] += 1
            if event == "PACKET_DROPPED":
                self.counts[f'drop_reason:{kind}:{row["drop_reason"]}'] += 1
            if kind == "data" and event == "PACKET_DELIVERED":
                latency = time - created
                if not math.isclose(latency, float(row["latency_s"]), abs_tol=1e-9):
                    raise ValueError("logged latency disagrees with packet timestamps")
                self.latencies.append(latency)
                self.flows[row["source"]].append((time, seq, latency))
                self.bytes_delivered += size
        elif event == "TX_START":
            wait = float(row["queue_wait_s"])
            self.links[row["link_id"]]["waits"].append(wait)
            self.queue_waits.append(wait)
            self.counts[f'{row["packet_type"]}_hop_transmissions'] += 1
        elif event == "TX_END":
            self.links[row["link_id"]]["bytes"] += int(row["size_bytes"])
        elif event in ("QUEUE_DROP", "HOP_FAILED"):
            self.links[row["link_id"]]["drops"] += 1
        elif event == "QUEUE_STATE":
            link = self.links[row["link_id"]]
            queue, busy = int(row["queue_size"]), int(row["busy"])
            link["queue"].append((time, queue))
            link["busy"].append((time, busy))
            link["max_queue"] = max(link["max_queue"], queue)
        elif event == "NODE_INIT":
            node = row["node_id"]
            self.initial_energy[node] = float(row["energy"])
            self.final_energy[node] = float(row["energy"])
        elif event == "NODE_SAMPLE":
            self.final_energy[row["node_id"]] = float(row["energy"])
        elif event == "ENERGY_CHANGE":
            if json.loads(row["details_json"])["cause"] in ("tx", "rx"):
                self.radio_energy += float(row["energy_delta"])
            else:
                self.degradation_energy += float(row["energy_delta"])
        elif event == "ACTIVE_COUNT":
            self.active_events.append((time, json.loads(row["details_json"])["active"]))
        elif event == "ROLE_STATE":
            self.role_events[(row["role"], row["scope"])].append((time, int(row["available"])))
        elif event == "ROLE_RECOVERED":
            self.recoveries.append(float(row["latency_s"]))
            if json.loads(row["details_json"] or "{}").get("cause") == "holder_failure":
                self.fault_recoveries.append(float(row["latency_s"]))
        elif event == "ROLE_UNRECOVERED":
            self.unresolved += 1
            if json.loads(row["details_json"] or "{}").get("cause") == "holder_failure":
                self.unresolved_faults += 1
        elif event == "GATEWAY_FORWARD":
            self.loads[row["node_id"]] += 1
        elif event == "RUN_END":
            self.ends += 1

    def rows(self):
        if self.ends != 1 or self.last_time != self.duration:
            raise ValueError(f"incomplete raw run {self.run_id}; RUN_END is required")
        if self.generated.keys() != self.terminal.keys():
            raise ValueError(f"packet conservation failed in {self.run_id}")
        if len(self.role_events) != self.role_count:
            raise ValueError("missing initial role states")
        generated = sum(kind == "data" for kind, _, _ in self.generated.values())
        delivered = self.counts["data:PACKET_DELIVERED"]
        dropped = self.counts["data:PACKET_DROPPED"]
        censored = self.counts["data:PACKET_CENSORED"]
        controls = self.counts["control_messages"]
        ratio = lambda numerator: numerator / generated if generated else None
        energy = list(self.final_energy.values())
        loads = [self.loads[node] for node in self.initial_energy]
        availability = sum(integrate_states(events, self.duration) for events in self.role_events.values())
        required = self.role_count * self.duration
        unavailable_final = sum(not events[-1][1] for events in self.role_events.values())
        threshold = len(energy) * self.cfg["minimum_active_fraction"]
        crossing = next((time for time, active in self.active_events if active < threshold), None)
        jitter = []
        for samples in self.flows.values():
            samples.sort()  # receive-time order within each source flow, ties by event_seq
            jitter.extend(abs(b[2] - a[2]) for a, b in zip(samples, samples[1:]))

        def result(metric, value, unit, definition, entity="", record_type="run"):
            return {**self.identity, "record_type": record_type, "metric": metric,
                    "entity": entity, "value": value, "unit": unit, "seed_count": int(value is not None),
                    "censored_runs": int(crossing is None) if metric == "network_lifetime_s" else "",
                    "definition": definition}

        metrics = (
            ("offered_data_packets", generated, "packets", "All scheduled sensor readings, including unavailable sources"),
            ("delivered_data_packets", delivered, "packets", "Unique end-to-end delivered data packets"),
            ("dropped_data_packets", dropped, "packets", "Confirmed terminal data drops; in-flight packets excluded"),
            ("censored_data_packets", censored, "packets", "In-flight data at fixed observation cutoff; not confirmed drops"),
            ("packet_delivery_ratio", ratio(delivered), "fraction", "Delivered / offered data packets"),
            ("drop_rate", ratio(dropped), "fraction", "Confirmed dropped / offered data packets"),
            ("censored_fraction", ratio(censored), "fraction", "In-flight at cutoff / offered data packets"),
            ("average_latency_s", mean_or_none(self.latencies), "s", "Mean delivered data end-to-end latency, including every gateway leg"),
            ("p95_latency_s", percentile(self.latencies, .95), "s", "Linear-interpolated 95th percentile of delivered data latency"),
            ("jitter_s", mean_or_none(jitter), "s", "Mean absolute successive delivered latency change, per source in receive order; not RFC3550 estimator"),
            ("throughput_bps", self.bytes_delivered * 8 / self.duration, "bit/s", "Delivered useful sensor payload bits / full observation duration (goodput)"),
            ("offered_load_bps", generated * self.cfg["packet_size_bytes"] * 8 / self.duration, "bit/s", "Offered sensor payload bits / observation duration"),
            ("average_served_hop_queue_wait_s", mean_or_none(self.queue_waits), "s", "Mean queue wait for TX_START events, data and control; censored waits excluded"),
            ("network_lifetime_s", self.duration if crossing is None else crossing, "s", "First time active fraction < configured threshold; right-censored at duration if never crossed"),
            ("network_lifetime_censored", int(crossing is None), "flag", "1 if active-node threshold was never crossed within observation window"),
            ("role_migrations", self.counts["ROLE_MIGRATION"], "migrations", "Successful holder changes, including failure reassignments; bootstrap excluded"),
            ("control_messages", self.counts["control_messages"], "messages", "Generated logical control packets, including failed and zero-hop local messages"),
            ("control_drop_rate", self.counts["control:PACKET_DROPPED"] / controls if controls else None, "fraction", "Confirmed dropped control / generated control packets; censored packets excluded from numerator"),
            ("censored_control_packets", self.counts["control:PACKET_CENSORED"], "packets", "Control packets in flight at observation cutoff"),
            ("control_hop_transmissions", self.counts["control_hop_transmissions"], "hops", "Actual control TX_START events over physical links"),
            ("data_hop_transmissions", self.counts["data_hop_transmissions"], "hops", "Actual sensor data TX_START events over physical links"),
            ("average_remaining_energy", mean_or_none(energy), "normalized", "Final mean node energy; normalized model units, not joules"),
            ("energy_variance", statistics.pvariance(energy), "normalized^2", "Final population variance across all nodes, including failed nodes"),
            ("communication_energy_consumed", self.radio_energy, "normalized", "Sum of logged transmit and receive energy debits"),
            ("injected_energy_loss", self.degradation_energy, "normalized", "Exogenous energy degradation; separate from communication consumption"),
            ("energy_per_delivered_packet", self.radio_energy / delivered if delivered else None, "normalized/packet", "All communication energy, including control and failed attempts, / delivered sensor packets"),
            ("average_role_recovery_time_s", mean_or_none(self.fault_recoveries), "s", "Mean completed holder-failure role outage; excludes bootstrap, epoch, expiry and unresolved outages"),
            ("average_all_role_outage_duration_s", mean_or_none(self.recoveries), "s", "Mean completed post-activation role outage, including epoch/expiry gaps; unresolved outages excluded"),
            ("completed_fault_recoveries", len(self.fault_recoveries), "outages", "Completed holder-failure outages"),
            ("unresolved_fault_outages", self.unresolved_faults, "outages", "Holder-failure outages still open at cutoff; right-censored"),
            ("completed_role_recoveries", len(self.recoveries), "outages", "Completed post-activation outages, including epoch/expiry outages"),
            ("unresolved_role_outages", self.unresolved, "outages", "Post-activation outages still open at cutoff; right-censored"),
            ("failed_unavailable_roles_final", unavailable_final, "roles", "Unavailable role-scope assignments at cutoff"),
            ("mean_unavailable_roles", (required - availability) / self.duration, "roles", "Time-weighted unavailable assignments, including bootstrap"),
            ("role_unavailable_seconds", required - availability, "role*s", "Integral of unavailable assignments over observation window"),
            ("role_availability", availability / required, "fraction", "Available role-seconds / required role-seconds; holder availability, not path connectivity"),
            ("active_node_count", self.active_events[-1][1], "nodes", "Final available nodes: not failed and energy > 0"),
            ("gateway_load_variance", statistics.pvariance(loads), "forwards^2", "Population variance of gateway forward counts over all physical nodes, including zeros"),
            ("gateway_load_max", max(loads), "forwards", "Largest cumulative gateway forward count on one physical node"),
        )
        rows = [result(*metric) for metric in metrics]
        for kind in ("data", "control"):
            for reason in ("no_route", "queue_overflow", "node_unavailable", "link_loss",
                           "gateway_unavailable", "lease_changed_in_transit", "source_unavailable"):
                rows.append(result(f"{kind}_drops_by_reason", self.counts[f"drop_reason:{kind}:{reason}"],
                                   "packets", "Confirmed terminal packet drops grouped by reason", entity=reason))
        for node in self.initial_energy:
            rows.append(result("gateway_load", self.loads[node], "forwards",
                               "Successful gateway-leg arrivals per physical node; a packet may visit three scopes",
                               entity=f"node_{node}"))
        ranked = []
        for link_id, state in sorted(self.links.items()):
            queue = integrate_states(state["queue"], self.duration) / self.duration
            busy = integrate_states(state["busy"], self.duration) / self.duration
            ranked.append((queue, busy, state["drops"], link_id))
            for metric, value, unit, definition in (
                ("link_mean_queue", queue, "packets", "Time-weighted waiting queue; excludes in-service packet"),
                ("link_max_queue", state["max_queue"], "packets", "Maximum waiting queue from all queue transitions"),
                ("link_utilization", busy, "fraction", "Serialization busy time / observation duration; propagation does not hold link"),
                ("link_drops", state["drops"], "drops", "Queue-overflow plus failed hop events on this link"),
                ("link_serialized_bps", state["bytes"] * 8 / self.duration, "bit/s", "Completed serialization bits/s, including control and later-lost packets"),
            ):
                rows.append(result(metric, value, unit, definition, entity=link_id))
        if ranked:
            queue, busy, drops, link_id = max(ranked)
            rows.append(result("bottleneck_mean_queue", queue, "packets",
                               "Link ranked by mean queue, then utilization, then drops, then link ID",
                               entity=link_id, record_type="bottleneck"))
        return rows


def analyze_csv(raw_path="raw_simulation_events.csv", output_path="final_network_analytics.csv"):
    """Read only raw CSV, validate complete runs, write per-run and paired results.

    Summary rows are tidy: record_type=run/aggregate/paired_difference/bottleneck.
    Paired differences are protocol minus baseline for the same scenario/seed.
    Blank values mean undefined (e.g. latency when zero packets arrive).
    """
    raw_path, output_path = Path(raw_path), Path(output_path)
    if raw_path.resolve() == output_path.resolve():
        raise ValueError("raw and final paths must differ")
    all_rows, seen_runs = [], set()
    with raw_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"run_id", "event", "event_seq", "timestamp_s", "details_json", "packet_id", "packet_type"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("raw CSV is missing required columns")
        for run_id, events in groupby(reader, key=lambda row: row["run_id"]):
            if run_id in seen_runs:
                raise ValueError("raw CSV must contain contiguous runs without duplicate run IDs")
            seen_runs.add(run_id)
            first = next(events)
            if first["event"] != "RUN_START":
                raise ValueError(f"missing RUN_START for {run_id}")
            analytics = RunAnalytics(first)
            analytics.consume(first)
            for row in events:
                if any(row[key] != analytics.identity[key] for key in analytics.identity):
                    raise ValueError("mixed experiment identity within a run")
                analytics.consume(row)
            all_rows.extend(analytics.rows())
    if not all_rows:
        raise ValueError("raw CSV contains no complete runs")

    groups = defaultdict(list)
    for row in all_rows:
        if row["record_type"] == "run":
            groups[(row["scenario"], row["protocol"], row["metric"], row["entity"])].append(row)
    for group, rows in sorted(groups.items()):
        values = [row["value"] for row in rows if row["value"] is not None]
        count = len(values)
        stddev = statistics.stdev(values) if count > 1 else None
        all_rows.append({**rows[0], "record_type": "aggregate", "seed": "all",
                         "value": mean_or_none(values), "stddev": stddev,
                         "standard_error": stddev / math.sqrt(count) if stddev is not None else None,
                         "seed_count": count,
                         "censored_runs": sum(int(row["censored_runs"]) for row in rows)
                         if group[2] == "network_lifetime_s" else ""})
        scenario, protocol, metric, entity = group
        if entity:
            continue  # Keep paired policy summaries separate from per-node/link distributions.
        for baseline in ("static", "dynamic"):
            if protocol == baseline:
                continue
            reference = {row["seed"]: row for row in groups.get((scenario, baseline, metric, entity), [])}
            pairs = [(row, reference[row["seed"]]) for row in rows
                     if row["seed"] in reference and row["value"] is not None
                     and reference[row["seed"]]["value"] is not None]
            deltas = [a["value"] - b["value"] for a, b in pairs]
            baseline_mean = mean_or_none([b["value"] for _, b in pairs])
            difference = mean_or_none(deltas)
            stddev = statistics.stdev(deltas) if len(deltas) > 1 else None
            all_rows.append({**rows[0], "record_type": "paired_difference", "seed": "paired",
                             "baseline": baseline, "value": difference, "stddev": stddev,
                             "standard_error": stddev / math.sqrt(len(deltas)) if stddev is not None else None,
                             "baseline_mean": baseline_mean, "seed_count": len(deltas),
                             "relative_change_pct": 100 * difference / baseline_mean
                             if difference is not None and baseline_mean else None,
                             "censored_runs": sum(bool(a["censored_runs"] or b["censored_runs"]) for a, b in pairs)
                             if metric == "network_lifetime_s" else "",
                             "definition": "Paired protocol minus baseline; " + rows[0]["definition"]})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
    return output_path
