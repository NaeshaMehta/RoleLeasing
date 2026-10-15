# Final Sprint Plan — Modular Role-Leasing Simulation

## Goal

Deliver a reproducible simulation that compares centralized coordination with the
decentralized role-leasing protocol under the same physical topology, node
conditions, and event schedule. The result is a tested Python project that runs
the required experiments and writes plot-ready metrics and migration records.

This plan supersedes the implementation direction in the older handoff/roadmap:
do not revive or split `archive/hierarchy.py`. Keep the implementation small,
modular, and testable.

## Architecture

Use one thin Mesa `Model` as the simulation clock and world owner. Model the
hierarchy as distinct entity classes/agents (`NodeAgent`, `SubnetAgent`,
`NetworkAgent`, `InternetworkAgent`); do not create nested Mesa models. Keep
calculations and policies in focused modules rather than putting protocol logic
on the coordinator.

Suggested package:

```text
simulation/
  config.py       # validated simulation and protocol configuration
  topology.py     # placement, physical graph, deterministic routing
  entities.py     # node and hierarchy entity classes
  capability.py  # node capability and pure recursive aggregation
  leases.py      # lease data and legal state transitions
  protocols.py   # centralized, static, dynamic, and proposed policies
  events.py      # event definitions, seeded schedules, event application
  metrics.py     # per-step, summary, and migration records
  runner.py      # thin Mesa Model and lifecycle orchestration
  experiments.py # common-condition experiment matrix and exports
  main.py        # command-line entry point
tests/
```

Reuse `nodes.py` behavior where it fits, but keep its tested capability weights
as the single source of truth. `archive/hierarchy.py` is not a runtime dependency.

## Sprint sequence and completion gates

### 1. Lock the simulation contract

- Use the specification as the behavioral source of truth.
- Fix the default profile at **100 nodes, 10 subnets, 3 networks**; distribute
  subnets 4/3/3 across networks. Make the configuration explicit and seeded.
- Keep physical connectivity separate from logical membership.
- Define one model tick and a deterministic ordering for events, capability
  updates, lease decisions, data traffic, and metric collection.
- Specify the meaning of network lifetime, role availability, failed roles,
  control-message counts, and recovery time before implementing metrics.

**Gate:** configuration validation and topology dimensions have unit tests; a
fixed seed reproduces the same topology and initial node attributes.

### 2. Build entities and the physical network

- Generate node positions and logical membership deterministically.
- Build an undirected graph with an edge when node distance is within the
  configured communication range.
- Derive normalized degree centrality and edge link quality from the graph.
- Implement distinct node/subnet/network/internetwork entities with explicit
  membership and availability.

**Gate:** expected counts and memberships are exact; generated links are
reproducible; disconnected and connected cases are tested.

### 3. Implement role capability and aggregation

- Calculate node capability for each role using the existing role weights.
- Aggregate child capability recursively using declared weights, with uniform
  weights as the documented default.
- Keep aggregation deterministic, normalized, and free of hidden state.

**Gate:** tests cover arithmetic, normalization, missing weights, and failed
nodes/empty or unavailable containers.

### 4. Implement communication and routing abstraction

- Route over the physical graph using a deterministic shortest-path algorithm.
- Use hop count plus a documented link-quality penalty as route cost; degraded
  links can increase cost or become unavailable according to configuration.
- Represent control operations as abstract messages and data-plane sensor load
  as abstract traffic flows; do not claim packet-, MAC-, or radio-level fidelity.
- Account separately for logical messages, message-hop transmissions, route
  cost, delivery failure, and per-gateway traffic load.
- In the centralized baseline, route control exchanges to/from a configured
  controller. In decentralized modes, route exchanges to the relevant local
  role/scope. This makes central bottlenecks and multi-hop overhead measurable.

**Gate:** routing tests verify shortest paths, link degradation, unreachable
destinations, and exact communication-accounting deltas.

### 5. Implement leases, selection, and protocol modes

- Define a small lease type with role, scope, holder, epoch, start/expiry,
  renewal time, and explicit lifecycle state.
- Select one valid holder per required role/scope using capability and policy.
- Implement cost-aware utility, hysteresis, adaptive lease duration, renewal,
  migration, and epoch fencing for the proposed protocol.
- Implement comparable modes through policy selection, not separate simulators:
  - **Centralized:** one controller makes assignments and coordinates recovery.
  - **Static:** initial assignments remain fixed.
  - **Dynamic:** highest-capability eligible candidate is selected immediately.
  - **Proposed:** recursive capability, migration cost, hysteresis, and leases.
- Keep policy differences explicit and ensure every mode uses the same world and
  communication accounting.

**Gate:** unit tests cover lease transitions, one-holder invariants, fencing,
renewal, failure invalidation, and expected differences between policy modes.

### 6. Add events and recovery

- Provide explicit failure, recovery, energy-degradation, and link-degradation
  events.
- Generate one seeded event schedule per experiment and replay it unchanged for
  every protocol mode.
- Record failure and successful reassignment times per affected role/scope.

**Gate:** event sequences are deterministic; failure/recovery tests assert
candidate eligibility, reassignment, and measured recovery time.

### 7. Collect required metrics and run experiments

Collect per-step time series, per-run summaries, and exact migration records.

**Required primary metrics:** network lifetime; role migrations; control
messages and message-hop transmissions; average remaining energy; role recovery
time; failed/unavailable roles.

**Required secondary metrics:** gateway load distribution; energy variance;
active-node count; role availability.

Migration records include time, role, scope, old/new holder, old/new capability,
migration cost, and old/new utility.

Run the four specified scenarios—normal operation, node failures, energy
degradation, and link degradation—across all protocol modes with matching seeds,
topology, and event schedules. Export per-step CSV, run-summary CSV, and
migration CSV; generate comparison plots for the primary metrics and gateway
load distribution.

**Gate:** a small smoke experiment produces non-empty, schema-checked outputs;
metrics have tests for expected values and invariants.

### 8. Final verification and delivery

- Run the focused unit and integration suites, then the full test suite.
- Run one short deterministic comparison and one complete experiment matrix.
- Check CSV schemas, plot generation, reproducibility, and absence of accidental
  dependency on the archived module.
- Document run commands, configuration, metric definitions, assumptions, and
  limitations. Frame conclusions as results under the modeled conditions, not
  a universal real-world networking proof.

**Definition of done:** a clean run from the documented command completes all
four scenarios for all protocol modes, writes the required outputs, and passes
the test suite.

## Scope control

Do not add packet-level simulation, MAC contention, radio interference,
retransmission protocols, or additional abstractions in this sprint. The
graph-based routing and abstract message/data-load accounting are the agreed V1
depth. If the centralized comparison does not use the same topology, offered
traffic, failure schedule, and accounting rules, do not claim the comparison is
valid.
