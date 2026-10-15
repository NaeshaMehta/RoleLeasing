# Test Plan — Role-Leasing Debloat (split `archive/hierarchy.py`)

## Why this plan exists

`archive/hierarchy.py` is a 671-line god class packing six protocol concerns into one
`RoleLeasingModel`. The debloat task splits it into cohesive modules. There is currently
**no test suite for the model** — every Phase 3/4 validation was a throwaway script in
`HANDOFF.md`. Splitting blind would let behavior drift silently, so these tests are both
the regression net that makes the split safe and the per-module unit tests for the new
modules.

## Anchors (verified in this environment)

- Behavioral anchor: `python -c "from hierarchy import RoleLeasingModel; m = RoleLeasingModel(); [m.step() for _ in range(30)]; print(m.current_epoch, len(m.active_leases))"` → **epoch 4 / 76 leases** (seed 42).
- Existing suite: `python -m pytest test_nodes.py -q` → **26 passed**. Must stay green.

## Guiding principles

1. **Public-API-first regression net.** The anchor drives `RoleLeasingModel.step()` and inspects `active_leases`; it never imports internal method names. It survives the split because `hierarchy.py` stays a thin orchestrator with an unchanged public surface (`step()`, `fail_node()`, …).
2. **Anchor-driven.** The behavioral anchor (epoch 4 / 76 leases, seed 42) is one of the tests — it pins the whole system end-to-end.
3. **Determinism over wall-clock.** Lease timing uses `float(self.steps)`; given a fixed seed every step sequence is reproducible. No `time.time()`, no real RNG in assertions.
4. **Two phases, one file first.** Write `test_hierarchy.py` against the current monolith as the regression net (Phase A). After each module lands, add focused unit tests importing from the new modules (Phase B).

## Phase A — Regression net now (`test_hierarchy.py`)

Ported from the throwaway checks in `HANDOFF.md`, plus coverage gaps. Mapped to spec sections.

| Test | Spec | Pins |
|---|---|---|
| `30_step_anchor` | §all | epoch == 4, `len(active_leases) == 76` — **the anchor** |
| `lease_count_is_4x19` | §3.4 | 76 = 4 roles × (15 subnets + 3 networks + 1 internetwork); one holder per (role, scope) at every level |
| `all_active_and_stamped` | §3.7 | after 30 steps every lease.state == "active" and lease.epoch == current_epoch |
| `determinism_seed7` | §6 | two seed=7 models → identical control totals + holder map after N steps |
| `lease_full_cycle` | §3.8 | activate/renew/commit_renewal→active; expire; begin_migration/migrated; invalidate from each non-expired state (direct `Lease` unit test) |
| `renewal_once_per_period` | §3.4/§3.7 | pin duration, step one period → exactly one 0.5 ctrl delta at ~70%, none elsewhere |
| `epoch_fencing_bumps` | §3.7 | E=5, 12 steps → epoch 3; every lease carries current epoch after each bump |
| `failure_reassigns_immediately` | §3.9 | fail a gateway holder → (role, scope) still present, reassigned to available holder, epoch preserved |
| `recover_restores_node` | §3.9 | recover → node online again, becomes a candidate |
| `migration_same_lease_object` | §3.5/§3.6 | degrade holder → hysteresis win → **same Lease object** retained in dict, holder swapped, period restarted, back to active; ctrl += migration cost |
| `hysteresis_blocks_marginal` | §3.6 | improvement < Δ does NOT migrate |
| `aggregation_arithmetic` | §3.3 | all-1.0 nodes → aggregated caps == 1.0; weighted Σ(wᵢCᵢ)/Σ(wᵢ) with a child-weight table |
| `best_holder_sentinel` | §3.4 | `_best_holder` returns `-inf` when no candidate available; initial assignment picks highest-cap holder |
| `recursive_availability` | §3.1/§3.9 | network-scope lease held by a subnet dies when that subnet's last node fails (container availability is recursive) |

## Phase B — Module unit tests after the split

Once each module exists, add targeted imports so failures localize to the offending concern:

- `test_lease.py` → `Lease` SM full cycle (§3.8)
- `test_aggregation.py` → `_aggregate` / `update_capabilities` arithmetic with/without weight tables (§3.3)
- `test_selection.py` → `_best_holder`, initial assignment, candidate/entity helpers (§3.4)
- `test_migration.py` → cost stub + hysteresis gating (§3.5/§3.6)
- `test_lifecycle.py` → epoch fencing + renewal orchestration (§3.7/§3.8)
- `test_containers.py` → subnet/network/internetwork construction (§3.1)

The Phase A integration tests stay pointed at `hierarchy.RoleLeasingModel` and run unchanged against the split modules — that is what proves the split preserved behavior.

## Execution & scope notes

- Run: `python -m pytest test_hierarchy.py -q` (mirrors `test_nodes.py`).
- **Out of scope:** the migration-cost stub value (0.15) — tests assert it's *used*, not its magnitude; centrality-from-CSV positions (optional, depends on `network_map.csv`); the 150-vs-100 node-count conflict (orthogonal).
- The anchor test is tightly coupled to current constants (`EPOCH_LENGTH`, lease durations), so it will need updating if Phase 5/8 change those — that coupling is exactly what makes it a reliable regression guard during this split.
