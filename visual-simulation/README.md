# Role-Leasing Simulation PoC

An interactive, local teaching implementation of the supplied **Role-Leasing Agricultural IoT Protocol Project Spec Sheet.pdf**. The existing Python simulator and its study results are unchanged.

The interface is a simulation workbench: configuration, phases, and event injection are in the left panel; execution controls sit above the network canvas. The entity inspector, telemetry, and tick/event/detail log expose the current state. Expand **Role assignment table** to inspect all 14 scopes for the selected role, including holder type, validity, epoch, version, expiry, and capability. Click a scope in the table to inspect its current holder.

## Run

Install Node.js if it is not available, then double-click `start.cmd`, or run:

```powershell
cd visual-simulation
node server.mjs
```

Open **http://127.0.0.1:4173**. No package installation, external service, or account is required. To choose another port, set the `PORT` environment variable before starting. Stop the server with Ctrl+C.

## Demonstration

1. Click **Next phase** to reveal placement, discovery, capability scoring, aggregation, and leasing. The aggregation phase switches to the hierarchy view.
2. Switch between **Field map** and **Hierarchy**. Select a node or entity, and choose a role and scope to inspect candidate scores and ownership.
3. Use **Skip to live**, then **Drain holder** and **Step 1 tick** twice to see preparation and completion of a handover. The journal identifies each role and affected scope.
4. Select the current subnet gateway, choose **Fail selected node**, and step three ticks. The role becomes unavailable immediately; detection and replacement follow the configured two-tick delay.
5. Try **Replay stale grant** to observe epoch fencing, **Recover selected** to restore a failed node, and **Join a new node** to add a candidate.
6. Enable scheduled disturbances for reproducible failures and degradation. Compare the three policies with a matched 120-tick run. Export the current run as JSON.

The default is 60 nodes for readability. Choose **100 nodes** for the existing project's 10-subnet, 3-network profile. Membership stays predefined, independent of distance-based physical links.

## Implemented phases

| Phase | Computation | Visualization |
|---|---|---|
| Placement | Seeded node attributes and clustered positions | Node map, subnet boundaries, three network groups |
| Discovery | Symmetric range graph, HELLO, JOIN_REQUEST, JOIN_ACCEPT | Links and animated routed messages |
| Capability | Role weights from the existing `nodes.py` definitions | Score shading and attribute bars |
| Aggregation | Normalized child means, leaves through root | Hierarchy, vectors, and selected entities |
| Role leasing | Reachability filter, initial maximum capability, grants and acknowledgments | Holder rings, hierarchy ownership edges, epoch and expiry inspector |
| Live operation | Renewals, failures, recovery, cost-aware handover, fencing and joins | Moving messages, failed nodes, handover banner, metrics and journal |

## Small, explicit modeling choices

- Browser JavaScript replaces Mesa/SimPy for this standalone visualization. A single deterministic event loop represents all entities. This is a separate explanatory model, not a front end for the Python engine and not a reproduction of the stored patent-study data.
- Physical links are undirected and limited by range. Quality-weighted shortest paths route abstract messages. Neighbor tables derive directly from the symmetric graph. HELLO illustrates a beacon toward a neighboring contact; it does not reproduce a radio broadcast or collision protocol.
- Container availability requires at least one online, joined descendant. Its first available descendant is its physical representative. A subnet holder at network scope is distinct from that subnet's node gateway.
- Gateway capability is `0.40 energy + 0.35 link + 0.25 normalized current degree`. Anomaly detection and health monitoring use `0.50 energy + 0.50 health`; discoverability uses `0.34 energy + 0.33 link + 0.33 health`. Parent weights are uniform. Failed leaves contribute zero without disappearing from the denominator.
- Initial selection uses maximum reachable capability. For optional moves, proposed utility is `capability - 0.1 × migration_cost`, and must strictly exceed current capability plus `0.05`. Recovery bypasses the discretionary switching threshold. The migration-cost estimate uses fixed message/transfer/disruption terms and a route-quality energy term, following the original project equation.
- A handover begins with `MIGRATE_INTENT`, `PREPARE`, and `PREPARE_ACK`. On the next tick, `STATE_TRANSFER` precedes old-lease expiration, a new `LEASE_GRANT`, and `LEASE_ACK`. Successful handovers therefore model six messages. Route failures can abort the transfer or leave a gap until retry. Emergency grants use two messages.
- Receiver state validates epoch, version, holder, and expiry. Old-epoch and duplicate-version grants are rejected. One assignment map per `(role, scope)` enforces a single modeled owner. This is not a distributed consensus implementation or proof of split-brain safety under arbitrary network delay.
- Proposed leases last `12 + capability × 16` ticks, renew at 70%, and reissue at 40-tick epochs. Failure detection takes two ticks. These short teaching defaults make all stages visible without a long run.
- Each online node offers a sensor load unit per tick to its subnet gateway. Control and data hops consume normalized endpoint energy, plus a small illustrative per-tick battery drain. No calibrated joules, sensing workload, MAC contention, retries, solar model, or end-to-end root-delivery claim is included.
- Static keeps initial holders. Dynamic immediately starts a handover to a strictly higher-capability reachable candidate without cost or hysteresis. Proposed adds cost, hysteresis, renewal, and epoch rollover. Baseline transport and receiver bookkeeping still use the shared model.
- Scheduled event times and node IDs are matched across policies. Comparisons report the final state, not a statistical benchmark or evidence of universal superiority.

## Files and verification

`engine.mjs` contains the deterministic simulation, `app.mjs` handles presentation and interactions, `styles.css` controls layout, and `server.mjs` serves only this directory on loopback. `node --test engine.test.mjs` runs invariant and behavior tests.
