# Finished Work

## Phase 1 — Contract and topology foundation (sprint plan phases 1–2)

**Status:** Complete

- Added validated, immutable simulation configuration with the planned 100-node,
  10-subnet, 3-network default profile (subnet distribution 4/3/3).
- Defined and validated deterministic simulation parameters, lease settings,
  metric lifetime threshold, energy costs, and migration-cost coefficients.
- Added seed-stable node placement, initial node attributes, and separate logical
  membership maps.
- Built a connected physical mesh from communication range, with normalized
  degree centrality and reproducible edge qualities.
- Added tests for config validation, exact world dimensions, repeatability, and
  physical connectivity.

**Verification:** `tests/test_foundation.py` — 4 passed.

**Not yet complete:** Mesa hierarchy entities and recursive role-capability
aggregation are the next phase.

## Phase 2 — Mesa entities and recursive capability aggregation (plan phase 3)

**Status:** Complete

- Added distinct Mesa agents for subnets, networks, and the internetwork, with
  nodes retaining their existing `NodeAgent` implementation.
- Built a hierarchy factory that preserves physical node IDs while mapping
  candidates at subnet, network, and internetwork scopes.
- Added pure weighted aggregation; declared child weights default to 1, and
  empty child sets produce zero capability.
- Added bottom-up capability refresh from node roles through the hierarchy.
- Verified container availability is recursive and failed nodes contribute zero.

**Verification:** topology, entity, capability, and existing node tests —
34 passed.

**Not yet complete:** routing and communication-cost accounting are next.

## Phase 3 — Deterministic routing and communication accounting (plan phase 4)

**Status:** Complete

- Added deterministic Dijkstra routing over the physical adjacency graph, with
  per-edge link-quality penalties and stable tie-breaking.
- Recompute usable edges from current node availability and link quality, so
  failures and link degradation can remove paths.
- Count abstract control messages separately from data messages, message-hop
  transmissions, route cost, delivery failures, and data deliveries.
- Charge endpoint energy for each routed hop; logical messages are still counted
  when delivery fails.
- Added focused tests for route choice, same-node delivery, failed delivery,
  link partitioning, message accounting, and energy consumption.

**Verification:** routing and all prior tests — 38 passed.

**Not yet complete:** lease lifecycle and protocol policies are next.

## Phase 4 — Lease lifecycle and protocol policies (plan phase 5)

**Status:** Complete

- Added an explicit lease state machine covering activation, renewal, migration,
  expiry, and invalidation, including adaptive duration and 70% renewal timing.
- Added four assignment policies: centralized coordination, static assignment,
  immediate dynamic reassignment, and proposed cost-aware leased assignment.
- Added one assignment per role and hierarchy scope, candidate eligibility and
  route reachability checks, immediate failure reassignment, epoch fencing, and
  migration records with the required columns.
- Implemented the deterministic migration-cost equation using configurable
  control, state-transfer, energy, and disruption terms.
- Added tests for lifecycle transitions, static/dynamic behavior, proposed
  hysteresis migration, one-holder-per-key, and epoch renewal.

**Verification:** lease, protocol, routing, hierarchy, and capability tests —
15 targeted tests passed.

**Not yet complete:** deterministic event schedules and recovery measurement are
next.

## Phase 5 — Deterministic events and recovery measurement (plan phase 6)

**Status:** Complete

- Added validated event records and deterministic seeded schedules for normal,
  failure/recovery, energy-degradation, and link-degradation scenarios.
- Added explicit, idempotent node failure/recovery and bounded degradation
  application; invalid node IDs and invalid event values fail explicitly.
- Added optional discrete-step detection delay to configuration and protocol
  recovery measurement from event-time detection through reassignment.
- Added event schedule, event application, and delayed recovery tests.

**Verification:** event and protocol recovery tests — 12 passed.

## Phase 6 — Simulation runner, required metrics, and experiment matrix (plan phase 7)

**Status:** Complete

- Added deterministic Mesa tick orchestration and abstract sensor-data traffic
  routed through subnet gateways.
- Added per-tick, per-run, recovery, energy, role-availability, migration, and
  gateway-load metrics with CSV exports and comparison plots.
- Added matched scenario/protocol experiments using shared topology, initial
  conditions, and per-scenario event schedules, plus the documented CLI.
- Ran the full default matrix: four scenarios by four protocols, 100 steps per
  run; produced 49 CSV files and 5 plots. Network lifetime was correctly marked
  as censored at the 100-step horizon for every run.

**Verification:** smoke output schemas, plots, and complete default matrix
completed successfully.

## Phase 7 — Final verification and delivery (plan phase 8)

**Status:** Complete

- Documented run commands, metric definitions, model assumptions, and
  interpretation limits in `SIMULATION_GUIDE.md`; confirmed the archived
  hierarchy module is not a runtime dependency.
- Added regression coverage for finite configuration values, protocol
  hysteresis, lease-object continuity across migration, and renewal timing.
- Full test suite: 59 passed.
- Re-ran the complete default matrix after final changes: 49 CSV files and
  5 plots were generated successfully.
- Under the default 100-step horizon, proposed coordination had fewer role
  migrations than centralized coordination in most scenarios, but generated
  more control messages; network lifetime was censored in every run. These
  results are trade-offs within this model, not proof of universal superiority.

**Verification:** `python -m pytest tests test_nodes.py -q` — 59 passed; the
documented default CLI completed the full four-scenario, four-protocol matrix.

## Phase 8 — Random-controller hierarchical baseline and paired experiment

**Status:** Complete

- Added a separate `hierarchical` baseline: one seeded random fixed controller,
  seeded random eligible hierarchy holders, ordinary graph routing, and
  failure-only holder replacement. Failover assignments are recorded as role
  migrations. The previous deterministic high-centrality `centralized` mode
  remains separate.
- Documented the baseline semantics and their abstraction limits; added tests
  for seeded reproducibility, controller selection, and failure reassignment.
- Ran 30 matched seeds (42–71) for each of four scenarios and both
  `hierarchical`/`proposed` modes: 240 runs total, 100 steps each. Paired modes
  share topology and event schedule. Per-seed timeseries, migrations, gateway
  loads, summaries, and plots are retained under `output/replicates/`.
- Results are mixed rather than an overall win: in node failures, mean role
  availability was 0.901 for hierarchical vs 1.000 proposed and data delivery
  was 0.900 vs 0.999; proposed used substantially more control messages
  (346 vs 60 on average). Under link degradation, delivery was 0.962 vs 0.953,
  favoring the baseline. Network lifetime was censored at 100 steps in every
  run, so it does not distinguish the methods.
- Added aggregate paired metrics and an experiment report under `output/`;
  no parameters were tuned to force a proposed-method win.

**Verification:** full test suite — 60 passed; all 240 seeded runs completed
and aggregate CSV/report generation was verified.

## Phase 9 — Widespread clustered topology and energy accounting

**Status:** Complete

- Moved the prior flat-topology paired experiment intact from `output/` to
  `output1/` before creating the new result directory.
- Added an optional compact-cluster topology with a configurable physical gap;
  the new experiment uses a 1.5 communication-range gap and explicit
  distance-attenuated backhaul links to keep the mesh connected.
- Added aggregated subnet-to-network and network-to-internetwork data traffic,
  making gateway tiers carry both local sensor traffic and upstream aggregates.
- Added distance-sensitive transmit/receive energy accounting and separate
  total/data/control/gateway-holder/max-node energy metrics. Energy is in
  normalized model units, not calibrated joules.
- Ran 30 paired seeds across four scenarios and two protocols (240 runs).
  Normal operation showed lower mean network communication energy for proposed
  (1.964 vs 2.075) but higher control messages (336 vs 56). Under node failures,
  proposed improved mean role availability (1.000 vs 0.896) and sensor delivery
  (1.000 vs 0.896), at higher communication and gateway energy. Under link
  degradation, hierarchical baseline had slightly higher delivery (0.976 vs
  0.973). Lifetime remained censored at 100 ticks.
- Preserved paired per-seed outputs, summaries, topology files, metrics, and
  plots under `output/`; documented assumptions in the experiment report and
  simulation guide.

**Verification:** full test suite — 63 passed; focused clustered-topology,
distance-energy, backhaul, and metrics tests passed; all 240 runs and output
schemas validated.

## Phase 10 — Six-idea optimization screening

**Status:** Complete

- Implemented and tested material capability-change detection for
  affected-scope reassessment. Capability refresh now occurs before the
  threshold comparison so changes from the current event/energy state are
  observable.
- Ran six individual optimization arms plus proposed and hierarchical
  references: 30 matched seeds, four scenarios, 500 steps, 12 workers (960
  runs total). No combinations were tested.
- Validated 960 summary rows and 480,960 time-series rows (501 per run), and
  generated per-scenario aggregates and paired deltas under `optimization-02/`.
- Retaining leases across epochs was the only clear standalone improvement:
  mean paired route-hop transmissions fell by 3,205.6 and normalized
  communication energy by 0.2002, with no measurable average service change.
  Scope checks, cooldown, adaptive hysteresis, batched renewals, and longer
  renewal settings showed no material gains in this setup.
- Identified a material confounder for renewal-oriented ideas: the default
  20-step epoch revokes leases before the tested longer leases renew, masking
  independent renewal and batching effects. Reported this limitation rather
  than claiming those mechanisms do not work.
- All network-lifetime values remained censored at 500 steps.

**Verification:** full test suite — 69 passed; `git diff --check` passed;
batch output count and every 501-row time series validated.

## Phase 11 — Minimal solar-aware protocol screening

**Status:** Complete

- Added seeded per-node constant solar input, battery-capacity clamping,
  harvested/curtailed energy accounting, and energy-depletion recovery after
  reaching a configured reserve.
- Added an optional proposed-protocol sustainable-energy provider score using
  current capability, residual battery, current harvest, recent communication
  consumption, reserve, and a decision horizon. Existing migration cost,
  hysteresis, leases, and epoch fencing remain in use.
- Added metrics for accepted/curtailed harvest, residual energy, depleted
  nodes, communication energy per delivered sensor measurement, and migration
  cost records.
- Ran three matched arms (no harvest, harvest with unchanged selection, and
  harvest-aware selection) over four profiles × 30 seeds × 1,000 ticks:
  360 runs and 360,360 time-series rows. All arms used lease retention
  identically; the exact topology and failure schedule were matched.
- Harvest alone raised mean ending battery by about 0.181 normalized units
  under moderate harvest in normal operation. Harvest-aware selection had
  unchanged delivery/role availability (100% in all arms at this horizon),
  but added 15–25 control messages, about 1,885–3,221 hop transmissions, and
  32–39 migrations per run compared with harvesting baseline. Communication
  energy was higher in all four profiles; the paired interval included zero
  only for moderate-harvest normal operation. No efficiency gain is claimed.
- All lifetime results were censored at 1,000 ticks; the experiment is too
  short to show service lifetime differences.
- Documented assumptions, results, and reproduction commands in
  `solar-screening/implementation_report.md`.

**Verification:** baseline before changes — 69 tests passed; focused solar,
lease, route, and metrics tests passed; final full test suite — 79 passed;
Pylance reports no errors in modified Python files; `git diff --check` passed.

## Phase 12 — Conservative solar-aware migration gate

**Status:** Complete

- Restored capability-only provider ranking and replaced the solar score bonus
  with a gate on optional proposed-protocol migrations. The gate compares
  projected usable reserve-energy benefit over 500 ticks against the routed
  migration-control-message energy plus a configurable 0.01-unit margin.
- Kept failure assignment/recovery outside the gate and preserved leases,
  epoch fencing, hysteresis, and valid-lease retention. Added tests for
  migration acceptance/rejection, capability-only ranking, failure recovery,
  and epoch retention.
- Ran a matched 30-seed, four-profile, three-arm experiment (360 runs,
  360,360 time-series rows). In the moderate-harvest node-failure profile, the
  gate reduced migrations by 2.67 per run (paired 95% CI [-3.96, -1.38]) while
  delivery and role availability remained 100%; mean communication energy
  increased by 0.205 units, with an interval crossing zero. In normal
  moderate-harvest operation the gate changed no measured outcomes. No energy
  efficiency improvement is claimed.
- Documented the mechanism, results, reproduction commands, and limitations in
  `solar-migration-gate/implementation_report.md`. Preserved the prior
  score-bonus experiment results as historical evidence.

**Verification:** full suite — 80 passed; focused solar-gate tests — 11
passed; paired aggregation validated all 360 runs and 360,360 time-series
rows; Pylance reported no errors in changed Python files.
