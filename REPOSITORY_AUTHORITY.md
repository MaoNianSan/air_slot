# Repository authority

This file is the single code-authority statement for the Air Slot research
repository. It records durable governance rules only; it does not record
transient migration or quarantine state.

## Canonical authority

- **Canonical root:** `D:\research\air_slot\code\explore` (all runtime paths in
  this repository derive from this location at runtime; do not hard-code it
  in new code — derive the project root from `__file__` or use the existing
  `PROJECT_ROOT` conventions).
- **Long-term main branch:** `v2/paper-primary`.
- **Execution/experiment branch:** `v2/phase7-gate-a` is a stage-gated
  Final-Test / execution branch. Its validated scientific code, validation,
  reporting, and canonical execution changes are merged back into
  `v2/paper-primary`. It is not a second long-term development line.
- **Stage-II solver authority (post-R2 ruling
  `HUMAN_GATE_B0A_SOLVER_AUTHORITY_RULING_20260919`, recorded in
  `registries/v2_stage2_solver_authority_reconciliation.json`):**
  `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID` is the production authority;
  `PYOMO_HIGHS` is parity / regression / historical-artifact compatibility
  only and must never produce a canonical Stage-II decision.

## Rules

1. All new scientific code is developed in this repository
   (`D:\research\air_slot\code\explore`).
2. All official experiments are executed from this repository.
3. All validation is executed from this repository.
4. All paper-facing artifacts originate from this repository.
5. Runtime dependencies must not point to another Air Slot worktree. The
   scanned active-runtime reference count to any historical worktree path
   (`D:\Local_Projects\airslot`, `_v2_phase7_execution`, `_v2_freeze_r2`)
   is zero; the only occurrences of those path strings left in the tree are
   inside sealed provenance records and documentation and are never resolved
   at runtime.
6. Additional worktrees may only be temporary validation environments.
7. No duplicated authoritative scientific implementation is allowed. The
   canonical Stage-I selector is `model/M3/stage1.py`; the canonical Stage-II
   decision is `model/M3/stage2.enumerate_recovery_decision`; the sealed
   Final-Test runner is `formal/v2_phase7/`.
8. Raw input data (`data1/`, `data2/`) is read-only and stays out of Git.
   External optional inputs (e.g. the instruction document copy under
   `D:\Download_all`) are env-overridable and never hard runtime
   dependencies.
9. Frozen artifacts follow the three-class policy: Class alpha (canonical
   artifacts: byte-stable, regeneration forbidden), Class beta (authorized
   deterministic diagnostic re-runs, provenance fields only), Class gamma
   (supplementary re-materialized analyses such as
   `artifacts/paper_results_v2_final_test_rmb/stage_q_sensitivity/`).

## Branch retention policy

- Remote branches are never deleted as part of local cleanup, including
  `v2/phase7-gate-a` and the historical results/docs branches. Deleting a
  local worktree directory never deletes Git branches or history.
- Historical freeze tags (`v2-scientific-freeze`, `v2-scientific-freeze-r2`,
  `jatm-final-test-freeze-20260920`, `jatm-paper-primary-freeze-20260920`)
  are immutable anchors.

## Historical worktree policy

Historical development/execution worktrees (for example
`D:\Local_Projects\airslot\_v2_phase7_execution`) are sealed-epoch execution
environments. Before any such directory is removed, its tracked history must
be reachable (branch ref, migration anchor, or verified bundle), its
non-Git unique artifacts must be migrated or backed up with verified SHA256
manifests, and a per-worktree deletion-eligibility record must pass. See the
migration audit record for the actual state.
