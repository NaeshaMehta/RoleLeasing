## Plan: get back on track

Ordered by dependency — each phase is small enough to verify before moving on. Phases 0–2 are pure fixes; 3+ build the missing behavior.

### Phase 0 — Environment & guardrails (~30 min)
1. Add `requirements.txt` pinning `mesa>=3`, `transitions`, `numpy`, `pandas`, `matplotlib`. Currently neither `mesa` nor `transitions` resolves in this environment (confirmed by diagnostics), so nothing has ever been run end-to-end.
2. Rename `nodes.test.py` → `test_nodes.py` — pytest's default discovery pattern won't collect the current name, so your one good test suite is silently invisible.

### Phase 1 — Reconcile `hierarchy.py` with the real `NodeAgent` (the blocker)
This is the "get it in the right direction" fix; everything else builds on it.

3. **Delete the duplicated `role_weights` dict** in `RoleLeasingModel.__init__` and import `ROLE_WEIGHTS` / `SUPPORTED_ROLES` from `nodes.py`. The two copies already disagree (`0.4/0.3/0.3` vs `0.40/0.35/0.25`) — pick `nodes.py` as the single source of truth since it's tested.
4. **Fix every call against the real API:**
   - `agent.get_capability(role)` → `agent.capability(role)` (6 sites)
   - `agent.is_active()` → `agent.is_available()` (3 sites)
   - `agent.set_active(False/True)` in `fail_node`/`recover_node` → `agent.fail()` / `agent.recover()`, wrapped so double-fail doesn't raise (`transitions` throws on invalid triggers by default)
5. **Fix the constructor:** `NodeAgent(self, node_counter)` → `NodeAgent(self, subnet_id=sub_id)` (Mesa 3.x assigns IDs; `subnet_id` is required). Then maintain `self.nodes_by_id: dict[int, NodeAgent]` and replace all six `next(a for a in self.agents if a.unique_id == ...)` scans — O(n) lookups everywhere, plus they're the source of two lint errors.
6. Fix the real bug at `hierarchy.py:209`: initialize `best_holder = None` alongside `best_role`/`best_utility`.
7. Drive-by cleanup in the same pass: unused imports (`Optional`, `field`, `auto`), dead locals (`total_cap`, unused `agent` in `fail_node`).

**Verify:** `python -c "from hierarchy import RoleLeasingModel; m = RoleLeasingModel(); m.step()"` runs without exceptions, and `pytest test_nodes.py` passes.

### Phase 2 — Topology ingestion & centrality (finish M1)
8. **Resolve the node-count conflict.** Spec says 100 nodes / 10 subnets; `placer.py` + `network_map.csv` produce 3×5×10 = 150. Recommend regenerating with subnet counts 4/3/3 across the three networks (or 2 nets × 5 — your call), and making the model *load* `network_map.csv` instead of ignoring it. This is a decision only you can make, so tell me which way before I touch it.
9. **Compute centrality once at init.** Right now every node has `centrality = 0.0`, which silently zeroes the gateway role's third term — spec §3.1 step 2 requires it. Since NetworkX is out of scope: derive adjacency from positions + comm range with plain NumPy (distance matrix, threshold), then degree centrality normalized to [0,1]. ~15 lines, no new dependency.
10. Add a Mesa `DataCollector` with per-step reporters (mean energy, active nodes, control messages, lease count) — the spec's "outputs CSV metrics" requirement has exactly zero implementation today.

### Phase 3 — Correct role-selection semantics (M4 correctness)
11. **One holder per (role, scope), not one role per subnet.** `perform_initial_role_assignment` currently picks a single winner across all four roles per subnet; the loop order is inverted. Roles outer, candidates inner → 4 leases per subnet.
12. **Add network- and internetwork-scoped selection.** The spec's central claim ("a subnet can act as a gateway just like a node") requires candidate pools at those scopes: network-scope roles select among member subnets using aggregated capability; same for the single internetwork scope. Today only subnets ever get leases, so the recursive aggregation feeds nothing.
13. **Weighted aggregation per §3.3:** `Σ(wᵢ·Cᵢ)` with an explicit child-weight table (default uniform = current averaging behavior, but now declared rather than implicit) and normalized output.

### Phase 4 — Lease lifecycle & epochs (M5)
14. Give `Lease` a `transitions` machine: `PENDING → ACTIVE → RENEWING → ACTIVE`, plus `ACTIVE → EXPIRED` and `ACTIVE → MIGRATING → ACTIVE`. Keep it on the lease, not the node — the node SM in `nodes.py` is already right.
15. **Make epochs actually advance** (e.g., bump `current_epoch` every E steps). Fencing logic exists but `current_epoch = 1` forever, so §3.7 is inert. On bump: invalidate leases whose epoch ≠ current → reassignment path.
16. Fix renewal spam: after the 70% threshold passes, `renew_keys` fires *every step* until expiry. Set a flag/state on renew so it happens once per lease period.

### Phase 5 — Real migration cost + migration record (§3.5, §7)
17. Replace the stub (`return base_cost * (alpha + beta)` = constant 0.15) with `α·ControlMessages + β·StateTransfer + γ·EnergyCost + δ·Disruption` as a frozen config dataclass — each term an abstract deterministic quantity per spec §3.8, all four coefficients configurable.
18. Emit the exact migration-record row from §7 (time, role, scope, old/new holder, old/new capability, cost, old/new utility) into a list → DataFrame at teardown.

### Phase 6 — Events & recovery measurement (§3.9, §4)
19. Model-level event API (`fail_node`, `degrade_energy`, `degrade_link`, `recover_node`) driving the transitions triggers, plus a **deterministic seeded event schedule** generated once and replayed identically for all three protocols (spec §6 requirement).
20. Record `failure_time` per invalidated lease; compute recovery time at reassignment; optional fixed detection-delay parameter.

### Phase 7 — Data plane (§5)
21. Node/gateway load counters: each step, node traffic routes to its subnet's current gateway holder, so role placement visibly shifts load distribution (feeds the "Gateway load distribution" secondary metric).

### Phase 8 — Protocol variants (M7)
22. One `protocol ∈ {"static", "dynamic", "proposed"}` flag on the model gating behavior rather than a second simulator:
    - **Static:** assign at init; skip migration checks, renewals, reassignment.
    - **Dynamic:** best capability wins immediately — λ=0, Δ=0, no adaptive lease.
    - **Proposed:** full mechanism.
    Same topology/seed/event-schedule constructor enforces §6's identical-conditions rule by construction.

### Phase 9 — Experiments & analysis (M8/M9)
23. `run_experiment(config) → CSV` using the DataCollector; four scripts for normal operation, node failures, energy degradation, link degradation; Matplotlib plots for the primary metrics (lifetime, migrations, control messages, remaining energy, recovery time, failed roles).

### Phase 10 — Ablation (M10, optional)
24. Config flags: no hysteresis / no migration cost / fixed lease duration / flat (non-recursive) aggregation.

**Notes on judgment calls:**
- Phases 0–1 are non-negotiable; the model literally cannot run against `nodes.py` today.
- Phase 2 item 8 needs your decision (150 vs 100 nodes) before I edit `placer.py`.
- Centrality metric choice (degree vs eigenvector-style power iteration from positions) — degree is defensible and cheap for V1; flag it if you want something fancier.
