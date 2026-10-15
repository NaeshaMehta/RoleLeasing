# Simulation Guide

## Run

From the repository root, run the complete four-scenario, five-protocol
comparison:

```powershell
python -m simulation.main
```

Use a smaller deterministic run while developing:

```powershell
python -m simulation.main --steps 20 --seed 42 --output results-smoke
```

Options:

- `--scenarios normal node_failures energy_degradation link_degradation`
- `--protocols hierarchical centralized static dynamic proposed`
- `--steps N`, `--seed N`, `--nodes-per-subnet N`
- `--intercluster-gap-in-ranges N`, `--distance-energy-weight N`
- `--hierarchical-backhaul`
- `--retain-valid-leases-on-epoch`: advance fencing epochs without revoking valid leases
- `--capability-reassessment-interval-steps N`: periodic reassessment interval; state changes still trigger immediate checks
- `--capability-broadcast-interval-steps N`: enable costed, scope-wide capability broadcasts at this interval (0 disables)
- `--hysteresis-delta N`
- `--reassess-affected-scopes-only`: restrict event-triggered migration checks to scopes containing changed nodes
- `--capability-change-threshold N`: cumulative node-capability change needed to dirty its containing scopes
- `--migration-cooldown-steps N`: prevent non-failure migrations until the cooldown has elapsed
- `--adaptive-hysteresis`: increase the migration threshold as network mean energy declines
- `--batch-control-updates`: batch due lease renewals per scope over the union of their routes
- `--lease-min-duration N`, `--lease-max-duration N`, `--lease-renewal-fraction N`
- `--battery-capacity N`, `--solar-harvest-rate N`: normalized battery capacity and per-node harvest input; harvest defaults to zero
- `--solar-harvest-rate N`: normalized energy units harvested per node per tick; defaults to zero
- `--solar-migration-gate`: gate optional proposed-protocol migrations on projected energy benefit
- `--minimum-energy-reserve N`, `--solar-decision-horizon-steps N`, `--solar-migration-safety-margin N`
- `--output PATH`

The default world has 100 nodes, ten subnets distributed 4/3/3 over three
networks, and one internetwork. All modes receive the same topology, initial
node states, and per-scenario seeded event schedule. Each model advances in a
fixed order: apply events, refresh capability, update protocol/leases, route
sensor traffic, refresh capability after communication energy costs, record
metrics.

## Communication abstraction

The physical mesh is an undirected graph generated from node positions and the
communication range. Routing uses deterministic Dijkstra shortest paths with
edge cost `1 + 4 * (1 - link_quality)`. Node failures remove incident links;
link degradation reduces incident-link quality and can make links unusable.
Logical control messages, message-hop transmissions, route cost, delivery
failures, and endpoint energy costs are accounted separately. Each active node offers one sensor-load unit per tick to its subnet gateway.
When hierarchical backhaul is enabled, gateways additionally forward one
aggregate for each active subnet and active network. This is not a packet-,
MAC-, interference-, or radio-level model.

Set `--intercluster-gap-in-ranges` above zero to place nodes in compact subnet
clusters, with long-range inter-cluster backhaul edges. Such edges have an
exponential distance-based quality penalty and still participate in the same
routing/failure model. With `--hierarchical-backhaul`, each active subnet
gateway sends one aggregated data message to its network gateway, then each
active network gateway sends one aggregate to the internetwork gateway.

When `--distance-energy-weight` is non-zero, the abstract radio energy model
charges each transmitting node
`E_base * (1 + weight * (distance / communication_range)^2)` per hop and each
receiving node `E_base`. `E_base` is `data_energy_per_hop` for sensor/backhaul
traffic and `control_energy_per_hop` for control traffic. Energy values are
normalized model units, not calibrated joules or a specific radio technology.
Reports separately track communication energy, data/control energy, gateway
energy, maximum per-node communication energy, and total remaining-energy loss
(which also reflects explicit energy-degradation events).

## Solar energy and optional migration gating

Each node receives a reproducible per-node harvest rate equal to the configured
`--solar-harvest-rate` multiplied by a seeded factor uniformly drawn from
`[0.5, 1.5]`. The rate is constant during a run (no daylight/weather cycle).
Accepted energy is added after lease/failure decisions and before sensor traffic,
and is capped by the normalized battery capacity (default `1.0`). Overflow is
counted as curtailed harvest. A node failed by energy depletion rejoins only
after it is recharged to `minimum_energy_reserve`; explicit node-failure events
still follow their scheduled recovery.

Provider ranking remains capability-only. With `--solar-migration-gate`, a
non-emergency migration in the proposed protocol is allowed only when the
difference in projected usable reserve energy between candidate and current
holders, over `solar-decision-horizon-steps`, exceeds the actual routed
migration-control-message energy plus `solar-migration-safety-margin`.
Projections use current battery, constant current harvest, and the holder's
observed mean communication-energy use, and are bounded by battery capacity
and the essential reserve. This conservative gate applies only to optional
migrations; lease assignment/recovery after holder failure remains immediate
and is not blocked. Existing capability hysteresis, migration-cost ranking,
lease retention, and epoch fencing remain in force. The projection is a simple
extrapolation, not a forecast, and does not account for unknown future radio
load. Energy costs include modeled communications only; sensing, computation,
idle draw, battery chemistry, and calibrated solar-panel output are not
represented.

The prior score-bonus experiment is preserved in
`solar-screening/implementation_report.md`. The matched migration-gate
comparison writes separately to `solar-migration-gate/` and compares no
harvest, harvest-only baseline, and harvest with the optional migration gate
across zero-, low-, and moderate-harvest profiles, including scheduled node
failures. Each seed shares topology and event schedules across arms.

Example widespread-cluster experiment:

```powershell
python -m simulation.main --intercluster-gap-in-ranges 1.5 --distance-energy-weight 1 --hierarchical-backhaul --protocols hierarchical proposed --output output
```

The `hierarchical` baseline selects a random fixed controller and random
eligible role holders from the same seeded world. Control operations route
through that controller; holders stay fixed unless one becomes unavailable,
when the baseline selects a reachable replacement without capability-based
optimization or lease-driven migration. This represents conventional,
fixed-hierarchy routed coordination for this model; it is an explicit baseline,
not a packet-level implementation of a particular routing standard.

The original paired 30-seed flat-topology comparison is retained in
`output1/`. A second paired 30-seed widespread-cluster experiment—with
intercluster backhaul, aggregated traffic, and distance-sensitive energy—is in
`output/`. See `output/experiment_report.md` for its findings and
`output/paired_comparison.csv` for paired per-scenario metrics and seed wins.
The saved reports are model-specific; they do not establish a universal win.

The six-idea, 500-step optimization screening is preserved under
`optimization-02/`; see `optimization-02/experiment_report.md` for its matched
seed design, results, and the effect of epoch-wide lease revocation.

The separate `centralized` mode uses a fixed, deterministically selected
controller and highest-capability role assignment with immediate migration.
`static` assignment never changes initial holders. `dynamic` assignment
immediately selects the best reachable capability candidate. `proposed`
assignment adds migration cost, hysteresis, adaptive leases, renewal, and epoch
fencing.

Optimization experiments can retain valid lease holders across fencing epochs,
throttle capability-driven migration checks while still checking immediately
after state changes, and adjust the hysteresis threshold. Periodic capability
broadcasts send one aggregated control message per hierarchy scope through a
deterministic spanning tree of the available scope nodes; message hops and
transmitter/receiver energy are charged. Capability snapshots update only when
the broadcast reaches all currently available nodes in that scope. This is an
explicit communication-cost model, not a simulated MAC-layer broadcast.
Optional controls also support scope-local reassessment, migration cooldowns,
energy-adaptive hysteresis, batched lease renewals, and configured lease duration
and renewal thresholds. Batched renewals are one logical message per scope per
tick, while their unique routed hop transmissions and energy are charged.

## Output files

The output directory contains:

- `summary.csv`: one row per scenario/protocol, including network lifetime,
  whether lifetime is censored at the run horizon, role migrations, control
  messages, message-hop transmissions, energy, role availability/recovery,
  gateway-load variance, sensor/backhaul delivery, and energy by data/control/
  gateway-holder category.
- `timeseries/<scenario>_<protocol>_timeseries.csv`: per-tick state and metric
  observations, including time zero.
- `migrations/<scenario>_<protocol>_migrations.csv`: required migration-record
  fields plus scenario, protocol, and seed.
- `gateway_loads/<scenario>_<protocol>_gateway_loads.csv`: per-tick nonzero
  gateway load by holder node.
- `<scenario>_timeseries.png` and `summary_comparison.png`: comparison plots.

`network_lifetime` is the first tick at which the active-node fraction drops
below the configured threshold; if that never happens, the run horizon is
reported with `network_lifetime_censored=true`. Recovery time is measured in
simulation steps from the recorded failure time through successful
reassignment, with optional fixed detection delay.

## Limits on interpretation

The results compare protocol behavior under this model's assumptions. They do
not prove universal superiority in real deployments. In particular, radio
contention, retransmissions, interference, queueing, and packet-level routing
are not represented. Compare metrics under matched topology, offered traffic,
initial conditions, and event schedules.
