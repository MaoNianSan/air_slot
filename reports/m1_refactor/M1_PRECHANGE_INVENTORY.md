# M1 Pre-change Inventory

Generated: 2026-08-05 (Asia/Hong_Kong)

## Repository identity

- Initial local HEAD before synchronization: `6516edee8840ac8f61e42e28a2d2ea2b8ae19f17`
- Current synchronized HEAD: `7ca041cfd5b9de72a15374b73087c7957265b574`
- Branch: `main`
- Live GitHub `main`: `7ca041cfd5b9de72a15374b73087c7957265b574`
- Initial tracked file count: 199
- Synchronized tracked file count before M1 deletion: 335
- User changes were preserved through a stash-backed three-way synchronization.
- No commit or branch was created.

## Initial user worktree

The initial worktree contained tracked changes in PRE, M3/M4, downstream
analysis, documentation, and tests, plus untracked audit/paper/output material.
The upstream PRE Core V2 migration deleted several locally modified PRE V1
files. Those conflicts were resolved to the single PRE Core V2 contract as
required; the original tracked changes remain recoverable in the safety stash
`codex-m1-refactor-pre-sync-20260805`.

## Legacy M1 source and audit files

| Classification | Path |
|---|---|
| DELETE_WITH_OLD_M1 | `overall_run/src/m1.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_baseline.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_calibration.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_feature_contract.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_metrics.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_sampling.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_training.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_contract.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_dictionary.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_figures.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_history.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_identity.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_lineage.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_reconstruction.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_reports.py` |
| DELETE_WITH_OLD_M1 | `overall_run/src/m1_lineage_runner.py` |
| DELETE_WITH_OLD_M1 | `overall_run/audit_m1_d6_metric_lineage.py` |

The old flat `m1.py` is 348 lines. The largest old lineage modules are
`m1_lineage_reconstruction.py` (344 lines) and `m1_lineage_reports.py` (282
lines).

## Legacy M1 tests

- `overall_run/tests/test_m1_d6_metric_lineage.py`
- `overall_run/tests/test_m1_feature_contract.py`
- `overall_run/tests/test_m1_previous_feature_flow.py`

These tests assert the retired quantile-ensemble, predecessor-leg feature flow,
and D6 historical lineage semantics. They are not M2-M4 or PRE Core V2 tests.

## References requiring replacement

- `overall_run/src/pipeline.py`: imports `prepare_model_frame` and calls the old
  frame/prediction flow.
- `overall_run/src/pipeline_fit.py`: imports and calls `fit_m1` and old
  `predict_distribution`.
- `overall_run/src/pipeline_precision.py`: imports the old model-frame builder.
- `overall_run/src/metric.py`: imports quantile metrics from the flat M1 module.
- `overall_run/src/config.py`: lists retired M1 files as authoritative code.
- `overall_run/src/pipeline_finalize.py`: publishes old M1 hashes, quantile grid,
  and feature-contract metadata.
- `pre_contract_gate.py`, `overall_run/main.py`, `overall_adv/main.py`,
  `part_adv/main.py`, `downstream_common.py`, and `overall_run/src/input.py`:
  integration gates still refer to `require_m1_adapter` or the retired feature
  contract.

## Shared or unrelated references

- `part_adv/src/pipeline_m1.py` is a separate part-adv baseline implementation.
  It is outside the formal overall-run M1 source deletion, but its downstream
  execution remains gated until contract migration.
- M2-M4 source files and ranking tests are shared downstream code and are not
  part of the M1 deletion scope.
- `.workbuddy/`, `code_map/`, paper-review directories, and historical reports
  are non-authoritative user/audit material. They may contain retired terms but
  are excluded from the formal source/config/README zero-residual gate.

## Generated legacy M1 artifacts

Old M1 artifacts exist under `overall_run/output/adapt_full/` and
`overall_run/output/full/`, including large model files, predictive samples,
metrics, checkpoints, and publication tables. They are user experiment results:

- They will not be read, converted, calibrated, or reused by the new M1.
- They are classified `RETIRED_NOT_REUSABLE`.
- They are retained because deletion of user experiment results was not
  separately authorized.

## Phase 0 gate

- `M1_DELETION_SCOPE_CONFIRMED=YES`
- `UNCLASSIFIED_M1_REFERENCES=0`
- `USER_EXPERIMENT_OUTPUT_DELETED=NO`
- `COMPATIBILITY_LAYER_PLANNED=NO`
