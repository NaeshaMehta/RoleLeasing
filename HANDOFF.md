# Handoff — Decentralized Role-Leasing IoT Protocol (v1)

Last updated: 2026-09-24. Written during **Phase 4** of `Roadmap.md` — Phase 4 code
(items 14–16) has landed and been smoke-verified, but is **not complete**: the first
`test_hierarchy.py` (user requirement) does not exist yet.

## What this project is

A Mesa-based simulation of a decentralized role-leasing protocol for agricultural
IoT sensor networks (spec in `Project.md`). Nodes recursively aggregate
capabilities up a fixed logical hierarchy (Node → Subnet → Network → Internetwork)
and lease four roles — `gateway`, `anomaly_detection`, `health_monitoring`,
`discoverability` — at every scope, with migration cost, hysteresis, adaptive
lease durations, and epoch fencing. Three protocol variants (static / dynamic /
proposed) must later be compared under identical topology/seed/event schedules.

## Files

| File | Role | State |
|---|---|---|
| `Project.md` | Spec sheet (§1–§11). Source of truth for semantics. | Read-only reference |
| `Roadmap.md` | 10-phase plan, dependency-ordered. Phases 0–3 done; 4 in progress. | Track progress here |
| `nodes.py` | `NodeAgent`: attributes, `capability(role)` (§3.2), transitions SM (online/failed), degradation events. `ROLE_WEIGHTS` / `SUPPORTED_ROLES` are the **single source of truth** for node capability. | Done, well-tested |
| `test_nodes.py` | 26 unittests for NodeAgent. All pass. | Green |
| `hierarchy.py` | `RoleLeasingModel`: hierarchy, §3.3 aggregation, §3.4 selection/leasing, hysteresis, Lease lifecycle SM + epoch fencing (Phase 4), failure invalidation + immediate reassignment, DataCollector. | Phase 4 code landed, **untested** — needs `test_hierarchy.py` |
| `placer.py` | Deterministic 2D topology generator → `network_map.csv`. | Works; node-count decision still open |
| `network_map.csv` | 150 nodes (3 nets × 5 subnets × 10), columns NetworkNo/SubnetNo/NodeNo/LocalNodeID/X/Y. Loaded by the model when present. | Generated |
| `requirements.txt` | mesa>=3, transitions, numpy, pandas, matplotlib, pytest | Installed & resolving |

## Environment notes (important)

- Windows host; commands actually run in **Git Bash** (the WSL/Bubblewrap sandbox is
  unavailable — `bwrap` not installed). Python 3.11.9, Mesa 3.3.1, all deps import
  fine at runtime.
- The language server's "Import could not be resolved" diagnostics for
  mesa/numpy/pandas/transitions are **false positives** (wrong interpreter selected);
  don't chase them. Real validation = run the code + pytest.
- New since Phase 4: pyright errors like `Cannot access attribute "activate" for class
  "Lease"` on the lease trigger calls (`lease.renew()`, `lease.invalidate()`, …) are
  also **false positives** — `transitions` binds trigger methods onto instances at
  runtime in `__post_init__`, invisible to static analysis. Same category as the
  import noise; verified working by running.
- Mesa 3.3.1 detail: `Model.steps` is a plain attribute incremented *before* the user
  `step()` body runs (wrapped step), so inside `step()` on the first call
  `self.steps == 1`. Passing `seed=` to `super().__init__()` seeds both Mesa's shuffle
  RNG and `self.rng`.
- Verify commands:
  - `python -c "from hierarchy import RoleLeasingModel; m = RoleLeasingModel(); [m.step() for _ in range(30)]; print(m.current_epoch, len(m.active_leases))"` → `4 76`
  - `python -m pytest test_nodes.py -q` → currently **26 passed**

## Roadmap status

### Phases 0–2 — already done (verified, not written by me)
requirements.txt exists and resolves; `test_nodes.py` named for discovery;
`hierarchy.py` imports `ROLE_WEIGHTS`/`SUPPORTED_ROLES` from `nodes.py`; uses the real
NodeAgent API (`capability()`, `is_available()`, `fail()`/`recover()` wrapped against
double-trigger `MachineError`); Mesa-3.x constructor with `subnet_id`; `nodes_by_id`
dict; loads `network_map.csv`; degree centrality from positions + comm_range (§3.1
step 2); Mesa DataCollector with per-step reporters.

### Phase 3 — completed (all three items, in `hierarchy.py`)

**Item 11: one holder per (role, scope).**
`perform_initial_role_assignment` previously picked a single winner across all four
roles per subnet (loop order inverted). Now roles iterate outer / candidates inner via
a shared `_best_holder(role, scope)` helper. Result: **76 leases = 4 roles × 19 scopes**
(15 subnets + 3 networks + 1 internetwork), was 15.

**Item 12: network- and internetwork-scoped selection.** New machinery:
- `INTERNETWORK_SCOPE = "internetwork"` module constant.
- `_scope_kind(scope)` → `"subnet" | "network" | "internetwork"`. Careful: subnet ids
  look like `network_0_subnet_1` — they *contain* `_subnet_`; network ids are exactly
  `network_<i>`. Naive `startswith("network_")` misclassifies subnets.
- `_all_scopes()` → all subnet + network scopes + internetwork.
- `_candidate_ids_for_scope(scope)` → member ids: nodes for subnet scopes, member
  subnet ids for network scopes, member network ids for the internetwork scope.
- `_entity_capability(holder_id, kind, role)` / `_entity_available(holder_id, kind)`:
  node capability via `NodeAgent.capability()`; container capability from the §3.3
  aggregated dict; a container is "available" iff it has ≥1 online descendant
  (recursive).
- `Lease.holder_id` is now `Any` — int node id at subnet scope, str container id at
  higher scopes. All lifecycle paths go through the kind-aware helpers.
- `calculate_utility(capability, migration_cost)` now takes a capability float (was
  `(agent, role)`) since candidates aren't always agents.
- `fail_node` invalidation extended: removes leases held by the failed node *and* any
  lease whose holder container lost its last online member.

**Item 13: weighted aggregation (§3.3).**
- Model attribute `child_weights: Dict[str, Dict[Any, float]]` — parent scope id →
  {child id → weight}. No entry = uniform weights (plain averaging); children missing
  from a declared table default to weight 1.0.
- `_aggregate(parent_id, child_ids, caps)` computes `Σ(wᵢ·Cᵢ)/Σ(wᵢ)`; used at all three
  levels in `update_capabilities()`. Deterministic, normalized to [0,1].

### Phase 4 — IN PROGRESS (items 14–16 code landed in `hierarchy.py`; tests missing)

**Item 14: Lease transitions machine. DONE.**
`Lease` is a `@dataclass` with a strict `transitions.Machine` (`auto_transitions=False`)
built in `__post_init__`:
- States: `pending / active / renewing / migrating / expired`.
- Triggers: `activate` (PENDING→ACTIVE), `renew` (ACTIVE→RENEWING),
  `commit_renewal` (RENEWING→ACTIVE), `begin_migration` (ACTIVE→MIGRATING),
  `migrated` (MIGRATING→ACTIVE), `expire` (ACTIVE→EXPIRED), plus `invalidate`
  (from active/renewing/migrating → EXPIRED) for external invalidation (holder
  failure, epoch bump).
- `_create_lease` constructs at PENDING then immediately `activate()`s — a lease is
  usable on creation.
- Renewal in `step()`: only leases in state `active` are renewal candidates; the loop
  does `renew()` → `_renew_lease()` → `commit_renewal()`. If the holder vanished
  mid-renewal (`_renew_lease` now returns `bool`), the lease is invalidated and
  reassigned instead.
- Migration in `check_for_migrations`: only state-`active` leases are migration
  candidates; on a hysteresis win the **same Lease object** goes
  ACTIVE→MIGRATING, swaps `holder_id`, restarts its period with the new holder's
  adaptive duration, then `migrated()` → ACTIVE. (No lease recreation — verified the
  dict entry stays the identical object.)

**Item 15: epochs advance. DONE.**
- Constructor param `epoch_length=10` → `self.EPOCH_LENGTH`; `step()` calls
  `advance_epoch()` when `steps % EPOCH_LENGTH == 0`.
- `advance_epoch()`: bumps `current_epoch` and a new `epoch_bumps` counter, fences every
  lease whose epoch ≠ current (`invalidate()`), removes it, and reassigns immediately
  via `_handle_lease_expiry` (§3.9 flow). Returns the fenced count.
- DataCollector gained `epoch` and `epoch_bumps` reporters.

**Item 16: renewal spam fixed. DONE.**
Renewal now fires only when `state == "active"` (the ACTIVE→RENEWING→ACTIVE cycle
consumes the trigger) and only before expiry (`elif` after the expiry check, so a lease
at both thresholds expires rather than renews). Verified: exactly one 0.5-cost renewal
event per lease period at the 70% mark, none in steps 8–9 of that period.

**Related change made while here:** `fail_node` now *reassigns immediately* after
invalidating (was: leave the scope vacant until the next expiry/migration pass) —
matches §3.9's recovery flow and keeps roles continuously available. Also,
`super().__init__(seed=seed)` replaces the old `self.rng = default_rng(seed)` override,
so Mesa's agent-shuffle RNG is seeded too (prerequisite for §6 identical-conditions
across protocol variants; verified two same-seed models produce identical control
totals and holder maps after 20 steps).

**Still left in Phase 4 before it can be called done:**
1. **`test_hierarchy.py` does not exist.** User explicitly asked for hierarchy tests to
   live there (Phase 3's validation scripts were throwaway; worth keeping as real
   tests: lease inventory 76 = 4×19, one holder per (role,scope), scope-kind-aware
   holders, weighted-aggregation arithmetic incl. default-weight-1 fill-in, failure
   invalidation across levels).
2. Lease-SM-specific tests: full cycle coverage (activate/renew/commit_renewal/expire;
   begin_migration/migrated; invalidate from each non-expired state), renewal-once-per-
   period via control-message deltas, epoch bump fences + reassigns all leases to the
   new epoch, migration keeps the same lease object and restarts its period.
3. Optional polish: `EPOCH_LENGTH` naming (module style is UPPER_CASE attrs but it's now
   constructor-driven), and deciding whether expiry+renewal collision should prefer
   renewal instead of current expire-wins.

### Phase 5–10 — not started (see Roadmap.md)
Next up after tests: **Phase 5** real migration cost (§3.5 α/β/γ/δ frozen config
dataclass; stub still returns constant `base_cost*(alpha+beta)` = 0.15, so hysteresis
currently compares raw capabilities — keep the `best_cost` reuse in
`check_for_migrations` when swapping the formula in) + §7 migration record rows (item
18). Note the migration path now mutates the existing lease, so a migration record can
read old/new holder+capability directly off it before the swap.

## Validation performed for Phase 4 (all passed; throwaway scripts — port to test_hierarchy.py)

- 30-step run: epoch advanced 1→4 with `epoch_bumps == 3`, lease count steady at 76,
  all leases state `active` and stamped with the current epoch.
- Renewal-once: duration pinned to 10; renewal (0.5 ctrl delta) observed exactly once,
  at the step crossing 70%; zero renewals in steps after that until expiry.
- Epoch fencing: with E=5 and 12 steps → epoch 3, every lease carries the current epoch.
- Failure + immediate reassignment: failing a gateway holder → lease still present,
  reassigned to a different available node, state `active`.
- Migration SM cycle: degrading the current holder's attributes → hysteresis win →
  same Lease object retained in `active_leases`, holder swapped, period restarted at
  current step, back to `active` (a broken `migrated()` trigger would have raised).
- Determinism: two models with seed=7, 20 steps each → identical
  `total_control_messages` and identical sorted (role, scope)→(holder, epoch) maps.
- Strict SM sanity: `expire()` from active works; follow-up `invalidate()` from expired
  raises (`transitions` strictness intact).
- `pytest test_nodes.py` → 26 passed after all edits.

## Things noticed / open issues (not fixed — deliberately out of scope)

1. **Node-count conflict unresolved (Roadmap item 8 decision pending).** Spec §2 says
   100 nodes/10 subnets; `placer.py` + `network_map.csv` produce 150 nodes/15 subnets.
   User note: "ignore the node count in placer.py and network_map.csv, you may change
   the count ... if needed to simplify/unify calculations" — Phase 4 did not need it;
   still open for whoever wants 4/3/3 or 2×5 regeneration.
2. **Migration cost is still the constant stub** = 0.15 → hysteresis compares raw
   capabilities. Real α/β/γ/δ model + frozen config dataclass is Phase 5 item 17.
3. **No migration record** (§7 row: time/role/scope/old/new holder/capability/cost/
   utility). Phase 5 item 18.
4. **Event API incomplete:** `fail_node`/`recover_node` exist (and now reassign);
   `degrade_energy` / `degrade_link` model-level wrappers and the seeded deterministic
   event schedule are Phase 6 items 19–20 (NodeAgent already has both methods).
5. **Recovery-time measurement** (§3.9: failure_time → reassignment_time) unstarted —
   Phase 6 item 20; note Phase 4's immediate-reassignment change makes recovery time
   ≈ detection delay, so the fixed-detection-delay parameter matters there.
6. **Data plane (§5)** unimplemented — Phase 7 item 21.
7. **Protocol variants flag** — Phase 8 item 22; constructor should take
   `protocol ∈ {"static","dynamic","proposed"}` plus shared seed/topology/event
   schedule (seed plumbing is now correct for this).
8. **Container capability = weighted mean of children.** Defensible for V1; switching to
   max/capacity-weighted is a one-line change where `_aggregate` is used.
9. **Centrality** uses degree centrality normalized by observed max degree (Phase 2
   item 9 choice). Fallback generated topology (no CSV) leaves centrality at 0 — only
   matters if `map_path` missing.
10. **Style lint noise:** pre-existing warnings in `hierarchy.py` (`typing.List/Dict/
    Tuple` deprecation, import sort order). Left alone; cosmetic, matches existing style.
11. **Mesa DataCollector reporters** reference `m.steps`; fine on installed Mesa 3.3.1.

## Design decisions made this session (rationale)

- Kept "holder" polymorphic (`Any` id + scope-kind dispatch) rather than wrapping every
  candidate in a common interface — smallest diff, keeps NodeAgent untouched and its
  tests green. If Phase 5+ grows more per-entity behavior, consider an `Entity` protocol.
- `_best_holder` returns `(id, utility)` with `-inf` sentinel when no candidate is
  available; callers must check `is not None`.
- Initial assignment uses pure capability (U = C per §3.4); migration-cost-adjusted
  selection only in `check_for_migrations`, matching spec.
- Availability of containers is *recursive* over descendants, so a network-scope lease
  held by a subnet dies exactly when that subnet has no online nodes left — checked at
  both failure time and each migration pass.

## Design decisions made during Phase 4 (rationale)

- **Lease SM on the dataclass** via `__post_init__` + strict machine
  (`auto_transitions=False`), mirroring `NodeAgent`'s pattern; trigger methods are
  instance-bound, hence the pyright false positives noted above.
- **Migration reuses the same Lease object** (holder swap in place) rather than delete+
  `_create_lease`: matches §3.8's ACTIVE→MIGRATING→ACTIVE as a property of *one* lease,
  and gives Phase 5's migration record old/new values on one object.
- **`invalidate` trigger** added beyond the roadmap's minimal set so holder-failure and
  epoch-fencing paths end leases in `expired` through the SM instead of bypassing it;
  every removal path now transitions before deleting from `active_leases`.
- **Expiry wins over renewal** when both fall due on the same step (renewal is the
  `elif`). Arbitrary tie-break; flagged as open polish above.
- **Epoch bump reassigns immediately** (same step) rather than leaving scopes vacant —
  keeps "at most one active holder per (role, scope, epoch)" true at every observation
  point and makes lease-count a stable metric.
- **`fail_node` reassigns immediately** for the same reason; recovery-time semantics
  deferred to Phase 6's detection-delay parameter.

## Suggested next step

Finish Phase 4: write `test_hierarchy.py` (unittest, mirroring `test_nodes.py` style)
covering the "Still left in Phase 4" list — port the throwaway checks above verbatim,
plus the Phase 3 validation cases from earlier sessions. Then Phase 5 items 17–18
(real migration cost + §7 migration record).

## User Note

- Implement the tests in test_hierarchy.py (move any hierarchy tests to that as well) —
  **still outstanding**, no `test_hierarchy.py` exists yet; all Phase 3/4 validation so
  far was throwaway scripts.
- ignore the node count in placer.py and network_map.csv, you may change the count in
  placer and run if needed to simplify/unify calculations
