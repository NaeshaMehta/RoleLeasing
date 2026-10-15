# SimPy packet simulation and separate CSV analytics

This is a standalone packet-level extension of the role-leasing project. It
preserves the specification's **Static / Conventional Dynamic / Proposed V1**
comparison and four required scenarios. It does not replace the existing Mesa
experiments or the browser visualization.

The specification documents abstract sensor/control traffic. This extension
adds explicit packet queues, serialization, propagation, loss and end-to-end
latency to meet the packet-analysis request. Its numerical radio/traffic
parameters are configurable teaching assumptions, not hardware measurements.

## Run from the project root

Requires Python 3.10+ and SimPy 4. The analytics stage needs only Python's
standard library.

```powershell
python -m pip install -r packet_simulation/requirements.txt

# Stage 1: simulation only. This closes the raw file before returning.
python network_packet_simulation.py --stage simulate

# Stage 2: separate process; reads the raw CSV without re-running simulation.
python network_packet_simulation.py --stage analyze
```

Or run both stages sequentially:

```powershell
python network_packet_simulation.py
```

Outputs, in `packet_simulation_output/`:

1. `raw_simulation_events.csv` - all raw packet, queue, role and energy events.
2. `final_network_analytics.csv` - performance summaries, node/link detail,
   multi-seed means, standard deviations, standard errors and paired comparisons.

The default matrix has **100 nodes, 10 subnets, 3 networks, 1 internetwork,
4 roles, 14 assignment scopes, 3 protocols, 4 scenarios and 3 seeds**. Each of
the 36 runs observes 30 simulated seconds. These defaults deliberately keep
runtime limited. Raw hop logs can be large.

Quick smaller run:

```powershell
python network_packet_simulation.py --duration 8 --nodes-per-subnet 2 --seeds 42 --output-dir packet_quick
```

Longer, higher-load comparison with more repetitions:

```powershell
python network_packet_simulation.py --duration 120 --packet-interval 2 --seeds 42 43 44 45 46
```

Set `--bandwidth` and `--queue-capacity` for congestion experiments. Use
`--raw` and `--final` to read/write exact paths, or `--output-dir` to relocate
both. Existing files at the selected output paths are overwritten. `--help`
lists the arguments. Defaults in `PacketConfig` expose additional assumptions.

For the isolated environment prepared in this workspace, use
`.venv-packet/Scripts/python.exe` instead of `python`.

## Two independent functions

```python
from packet_simulation.config import PacketConfig
from packet_simulation.model import run_simulation
from packet_simulation.analytics import analyze_csv

config = PacketConfig(duration_s=30, nodes_per_subnet=10)
run_simulation(
    "packet_simulation_output/raw_simulation_events.csv",
    config=config,
    seeds=(42, 43, 44),
)

# Only the persisted CSV is handed to stage 2, not a model or result object.
analyze_csv(
    "packet_simulation_output/raw_simulation_events.csv",
    "packet_simulation_output/final_network_analytics.csv",
)
```

`model.py` contains topology, traffic, queue and protocol processes. `config.py`
contains model parameters and the existing project's role weights.
`analytics.py` never imports SimPy and reads raw events one run at a time.

## Matched experiment design

| Policy | Assignment behavior |
|---|---|
| Static | Choose highest-capability candidates at startup; fixed permanent assignments; no later reassignment or renewal. Lost bootstrap messages may retry the same chosen candidate. |
| Conventional Dynamic | Re-evaluate every evaluation interval; select highest capability without migration cost or hysteresis. Permanent assignments change through packet-based handovers. |
| Proposed V1 | Recursively aggregated capabilities; net utility after migration cost; strict hysteresis; adaptive temporary leases; 70% renewal; epoch invalidation. |

| Scenario | Identical exogenous disturbance schedule across policies |
|---|---|
| Normal | No injected failures or degradation |
| Node failures | Fail 10% of nodes at 25% of the window; recover them at 75% |
| Energy degradation | Subtract 0.25 normalized energy from the same selected nodes at 25% and 50% |
| Link degradation | Subtract 0.35 from selected nodes' link quality at 25% and 50% |

Node 0 is the fixed sink attachment and is excluded from injected disturbances;
its radio still queues, loses packets and consumes energy. Initial attributes,
topology, source packet IDs, offered reading times and exogenous disturbances
depend only on seed, not policy. Link-loss draws use a stable hash of seed,
packet ID, hop and link, rather than an event-order-dependent random stream.
Different paths/hop numbers or link quality can still give different outcomes.
Endogenous communication energy is allowed to differ by policy.

All four role names model assignment and availability. They do not implement
an anomaly classifier or a health diagnosis algorithm. Only gateway assignments
determine the modeled sensor forwarding path.

## Model mechanics and boundaries

- Physical topology is a connected undirected grid mesh. It is independent of
  the predefined logical Node -> Subnet -> Network -> Internetwork hierarchy.
  Deterministic breadth-first search chooses shortest-hop paths through currently
  available physical nodes. A route is fixed for a leg; intermediate failures
  cause a drop. There are no fabricated direct hierarchy edges.
- Each undirected link has one SimPy `Resource` shared by both directions. It
  is half duplex, FIFO, with a finite waiting queue. Buffer size excludes the
  packet in service. Data and control compete for the same link server.
- A hop holds the server for `size_bytes * 8 / bandwidth_bps`. Propagation then
  occurs outside the server. Loss is sampled after serialization with probability
  `base_link_loss + quality_loss_weight * (1 - min(endpoint_quality))`.
- Every attempted transmission debits normalized transmitter and receiver energy.
  These linear per-byte costs are assumptions, not joules or a calibrated RF
  model. Exogenous energy loss is kept separate. Solar harvesting, radio
  interference, contention domains, retransmission timers and MAC are absent.
- Sensor traffic follows source -> subnet gateway -> network gateway ->
  internetwork gateway -> sink attachment (node 0). Aggregate holders delegate
  through their own child gateway assignments to a physical node. Local legs
  need no physical transmission. Forward counts count scope visits, so one
  sensor packet can produce several forwards on the same physical node.
- Capability vectors use the weights in the project's `nodes.py`. Failed or
  depleted leaves contribute zero; each parent takes the uniform mean of its
  immediate children. Anomaly detection and health monitoring have identical
  weights in the existing project and therefore identical node scores.
- A successful proactive handover sends intent, prepare, ready, state transfer,
  grant/assignment and acknowledgment (six logical packets). Reassignment after
  failure needs grant/assignment plus acknowledgment. Failed control delivery
  aborts the transaction. Dynamic/proposed retry at later evaluations.
- The cost estimate uses the document's configurable alpha/beta/gamma/delta
  expression with six control messages, state-transfer cost, estimated routing
  energy and disruption. Proposed switches only when
  `C_new - lambda * cost > C_current + delta`. Failed holders use recovery
  assignment, rather than requiring a nonexistent current holder to approve.
- Adaptive leases use `T_min + capability * (T_max - T_min)`. Renewal exchanges
  control packets. Older epochs are invalid; the observation includes the gaps
  and control load introduced by strict epoch replacement. Data checks the
  delegation chain's versions and validity before accepting gateway service.
- A failed/depleted holder is detected after a fixed configured delay plus
  evaluation polling. Actual recovery also includes queueing and control
  delivery. The script does not assert an ideal recovery bound in a lossy mesh.
- This is a single SimPy process space with an atomic assignment dictionary,
  not distributed consensus. Evaluators read current simulated capabilities;
  CAP_UPDATE/SUMMARY packets model overhead, not stale local knowledge.
  Contact points for aggregate control are their first available physical member.
  Discovery/HELLO and joins are not simulated; the newer DOCX makes them optional.

## Raw CSV contract

Each row has experiment identity, monotonically increasing `event_seq`,
`timestamp_s`, event name and relevant fields. Nonapplicable fields are blank.

| Raw event family | Recorded information |
|---|---|
| RUN_START / RUN_END | Full configuration, role weights, disturbance schedule, completed observation boundary |
| NODE_INIT / NODE_SAMPLE | Initial attributes/positions/membership; sampled and final energy/availability |
| PACKET_GENERATED | Unique ID per run, type, message, source/destination, bytes, creation time |
| HOP_ARRIVAL / TX_START / TX_END / HOP_RECEIVED | Packet path, hop index, current node, link, queue waiting and service timing |
| QUEUE_STATE / QUEUE_DROP / HOP_FAILED | Every queue transition, occupancy, busy flag and failure cause |
| PACKET_DELIVERED / PACKET_DROPPED | One terminal outcome, delivered latency or confirmed drop reason |
| PACKET_CENSORED | Packet still in flight when the observation window ends |
| ENERGY_CHANGE / DISTURBANCE | Radio energy debits, forced energy loss, node failures/recovery and link changes |
| ROLE_STATE / ROLE_RECOVERED / ROLE_UNRECOVERED | Exact availability transitions, outage cause, completed and censored outage durations |
| ASSIGNMENT_* / LEASE_* / ROLE_MIGRATION / TRANSACTION_* | Holders, scope, epoch/version, expiry, handover result and migration decision record |
| GATEWAY_FORWARD / RUN_SAMPLE | Per-node forwarding events; cumulative delivered bytes, cumulative goodput and total queued packets |

`throughput_bps` in raw delivery/sample events is a running observation counter
(`delivered_payload_bits / elapsed_time`). Stage 2 independently derives the
final rate from packet outcomes. It does not trust the running field as its
summary. `details_json` contains event-specific structured details.

## Metrics and interpretation

All specification metrics are present:

| Metric | Definition |
|---|---|
| Network lifetime | First active-node fraction below 50%; observation duration plus censor flag if never reached |
| Role migrations | Successful holder changes, including failure reassignment; not bootstrap |
| Control messages | Generated logical packets; actual physical control-hop transmissions reported separately |
| Average remaining energy | Final mean over all physical nodes, normalized model units |
| Role recovery time | Mean completed holder-failure outage; initial, epoch and expiry gaps excluded; unresolved failures separately counted |
| Failed/unavailable roles | Final count and exact time integral of unavailable role-scope assignments |
| Gateway load distribution | Forward counts for every physical node, including zero loads; maximum and population variance |
| Energy variance | Final population variance of normalized energy |
| Active node count | Final nodes that are not failed and have positive energy |
| Role availability | Available role-seconds / required role-seconds; includes bootstrap downtime |

Additional packet metrics include delivery ratio, confirmed drop rate, censored
fraction, mean/p95 end-to-end latency, goodput, offered load, jitter, queue waits,
per-link queue mean/maximum, utilization, serialized bit rate, drops and bottleneck
identity. Drop reasons are broken down separately for data and control.

Jitter is the mean absolute difference between consecutive delivered packet
latencies **within each source flow in arrival order**, pooling eligible pairs.
It is not an RFC 3550 exponentially smoothed estimator. Fewer than two delivered
packets per flow gives an undefined (blank) value. The bottleneck is the link
with largest time-weighted mean queue, then utilization, then drop count.

At cutoff:

```
offered data = delivered data + confirmed drops + censored in-flight data
```

Unfinished packets are not silently classified as drops or successful deliveries.
Latency estimates describe delivered packets and may have selection/censoring
bias under heavy loss/congestion. Queue state integrals include waiting and busy
intervals that cross the cutoff; served-hop queue means exclude unfinished waits.

Role availability tests a live holder with a valid assignment/lease; packet
delivery additionally needs routes and the complete gateway delegation chain.
The two measures are intentionally separate. Fault recovery is reported only
for completed holder-failure gaps; a blank mean does not mean instantaneous
recovery. Check completed and unresolved counts alongside it.

## Read the comparison file

The final file uses tidy rows with `metric`, `value`, `unit`, `scenario`,
`protocol`, `seed`, `entity` and the following `record_type` values:

- `run`: one metric for one policy/scenario/seed. Nonempty `entity` identifies
  a particular node, physical link or drop reason.
- `aggregate`: metric mean over defined seed values, with sample standard
  deviation, standard error and actual contributing `seed_count`.
- `paired_difference`: mean of policy minus baseline for **matched seeds**;
  includes baseline mean, paired standard deviation/error and relative change.
  Positive means larger, not automatically better. Baseline zero gives a blank
  percentage. Undefined values are omitted from pairs and their count is shown.
- `bottleneck`: per-run worst link, recorded in `entity`.

To compare the policies, filter `record_type=aggregate`, `entity` blank, then
choose a scenario and metric. For Proposed vs Dynamic, filter
`record_type=paired_difference`, `protocol=proposed`, `baseline=dynamic`.

Lower latency, drops, overhead, energy cost and outage duration generally help;
higher delivery, goodput and availability generally help. Fewer migrations
alone can reflect poor adaptation. Read stability together with availability.

No policy is forced to win. Strict epochs, renewal traffic and migration
thresholds can make Proposed V1 worse in particular settings. The short default
run may never cross the lifetime threshold: its reported duration is then a
restricted observation, not a measured lifetime. Paired lifetime differences
with `censored_runs > 0` are differences of restricted observations, not proof
of longer survival. Three seeds are a demonstration, not a conclusive study.

The analytics rejects truncated runs, duplicate packet outcomes, missing packet
terminations and invalid event ordering instead of emitting plausible summaries.

## Validation

```powershell
python -m unittest discover -s tests -p test_packet_simulation.py -v
```

The tests cover hand-calculated latency/jitter/goodput/queue/energy/availability,
cutoff censoring, corrupted logs, matched traffic/worlds/disturbances, epoch
validity, paired arithmetic, real congestion, repeatability, parameter validation
and consistency with the existing project's role weights.

Protocol sources: `cn_proj_spec_sheet.docx`, sections 3-8, and
`Role-Leasing Agricultural IoT Protocol Project Spec Sheet.pdf`, pages 2-5.
The DOCX's abstract traffic design is extended explicitly here. SimPy resource
semantics follow the [official SimPy Resource documentation](https://simpy.readthedocs.io/en/stable/api_reference/simpy.resources.html).
