# Experiment Readiness After Reconciliation

Current engineering snapshot: `2026-08-17`.

Repository HEAD: `bfd3d34f83aa895b228492d90571047ad68d4492` with an
uncommitted split-containment closure worktree.

Scientific config hash:
`sha256:dbcc3c5360ce23047b1f40d48fe207abb8c6e8e645b0f8ba3e50b10e71314662`

Registry manifest hash:
`sha256:dbe3da2d8f8b74cf920d2b1bfc75519970ce7e6d71133bba8d19208b90f56aaa`

## Current engineering gates

| Gate | Status | Current evidence |
| --- | --- | --- |
| PRE ownership | PASS | `PRE_DATA_CONSTRUCTION_OUTSIDE_PRE=0` |
| Static volume | PASS | no `REFACTOR_REQUIRED` files |
| Dependency boundaries | PASS | focused static tests |
| V5 split containment | PASS | boundary-complete June-September audit |
| Migration equivalence | PASS | `14 passed` |
| Full regression suite | PASS | `393 passed, 1 skipped` |
| Final Test isolation | PASS | `FINAL_TEST_ACCESS_COUNT=0` |

Compilation command:
`python -m compileall -q model exp validation tests`.

Full regression command: `python -m pytest -q`.

## Split closure

The current PRE publisher rejects episodes whose predecessor service date,
successor service date, closed episode interval, or canonical decision-node
interval spans more than one V5 split. Monthly carry remains enabled for
ordinary same-split month boundaries.

Authoritative artifacts:

- `artifacts/diagnostics/v5_development_freeze/PRE_SPLIT_CONTAINMENT_AUDIT.json`
- `artifacts/diagnostics/v5_development_freeze/PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json`
- `docs/reconciliation/V5_SPLIT_CONTAINMENT_CLOSURE.md`

Corrected Development counts are `946981` eligible episodes and `13608096`
eligible nodes. The historical successor-date pool contained `4378`
cross-split Development episodes and `113444` associated nodes.

## Scientific readiness

The current H/W values remain the historical selections `H_STAR=32` and
`W_STAR=30`, but their shared 320-episode cache contains three cross-split
episodes. Consequently:

- `H_W_FREEZE_STATUS = REQUIRES_RECONSIDERATION`
- `H_W_RERUN_THIS_ROUND = FALSE`
- `D_TO_TAIL_IDENTIFIABILITY = NOT_IDENTIFIED_FROM_CURRENT_M1_OUTPUTS`
- `OPTION_A_REQUIRES_NEW_H_W_FREEZE = TRUE`
- `CURRENT_H_W_ARTIFACTS_REUSABLE = NO_FOR_NEW_MODEL_SELECTION`

No H/W retraining, warning inference, threshold search, M2-M4 run, Final Test,
or `paper_full` run was performed in this closure.

Therefore:

- `GLOBAL_RECONCILIATION = PASS`
- `EXPERIMENT_READINESS = CONDITIONAL`
- `NEXT = READY_FOR_AGGRESSIVE_M1_SIGNED_TARGET_REFREEZE`
