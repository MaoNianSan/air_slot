# AirSlot V2 - Phase 7 Final Status

Phase 7 (Final Test) is executed once, audited and **closed**. This page is the
status of record; it contains no new scientific computation.

## Execution chain

| Step | Value |
|---|---|
| Gate A commit | `68f4f9c5ddfb8b3e8fee6772af267402a8152518` |
| Human release | approved, `2026-09-19T14:32:58+08:00` (bound to R2 freeze tag object) |
| Freeze tag object / target | `2dcca6c159dedde3803e63cb48bd8bfefff574cf` / `3834eed33d4a2ea4bdba111fc29cca3529525a3a` |
| Access epoch id | `sha256:7ba42fed0934a3d2f787d9e52b9170a7d2914c5d233a6d1e10c91c80f1ee3a69` |
| Access accounting | historical total 1, Phase-7 increment 1, current total 2 |
| Same-epoch retries | `retry_count = 2`, binding/I-O only, `retry_within_same_epoch = true` |
| Sealed run commit | `aebd7bb` (message `v2(phase7-gate-b): execute sealed final test`) |
| Post-run integrity audit commit | `d78183f` (message `v2(phase7-postrun): add checkpoint scientific integrity audit`) |
| Post-run verdict | `SCIENTIFIC_RESULT_INTEGRITY_PASS` |

The epoch ran to completion: final ledger
`artifacts/experiment/final_test_v2/PHASE7_ACCESS_AUDIT.json` has
`status = PHASE7_ACCESS_EPOCH_COMPLETE`, `raw_read_started = true`,
`raw_read_completed = true`. No further epoch is open or planned.

## Frozen authority during the run

- Stage-II primary solver: `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID`
  (`deterministic_tie_break = SMALLEST_U`); Pyomo+HiGHS only as an independent
  parity oracle (`highs_required_for_production_rows = false`).
- `solver_status` carries backend identity (`EXACT_ENUMERATION` on actionable
  rows, `NOT_RUN` on non-actionable rows); HiGHS termination condition is a
  separate parity diagnostic.
- Reference representation `H_g^{C,*} = H_g^{C,History+Joint}`; fixed cohort
  `R_g*` of 166 support-qualified nodes shared by all comparator evaluations.
- Bootstrap: paired episode-level, seed `20260906`, 2000 replicates,
  percentile 95%, pre-lock provenance recorded (seed predates the lock commit).
- Typed states preserved (`ABSTAIN_NO_COMMON_SUPPORT`,
  `UNDEFINED_ZERO_RECOVERABLE_VALUE`, `NOT_ACTIONABLE`, `N/A_NOT_DEFINED`);
  no silent coercion, zero filling or illegal actions.
- Fixed-window history sensitivity: `NOT_AVAILABLE_NOT_FROZEN`.

## Persisted results

Nine immutable checkpoints (587,375,479 bytes) stay local;
`CHECKPOINT_MANIFEST.json` carries their stage order, dependencies, file and
payload hashes with `status = LOCAL_ONLY_NOT_COMMITTED`. Paper-facing numbers
for Sections 5.2-5.5 are committed in `PAPER_FACING_SECTION5_VIEWS.md`.

## Stop state

Phase 7 is closed; Phase 8 is not entered; nothing is pushed from this run other
than this branch publication. Any Final-Test sensitivity result would require a
new, explicitly authorized access epoch.
