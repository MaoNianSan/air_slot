# M1-M2 V2 Rerun Decision

Date: 2026-08-06

```text
PRE_RERUN_REQUIRED = NO
M1_RETRAIN_REQUIRED = YES
M1_RECALIBRATION_REQUIRED = YES
M1_RESAMPLE_REQUIRED = YES
M2_PARAMETER_FREEZE_REQUIRED = YES
M2_FORMAL_RECONSTRUCTION_REQUIRED = YES
M3_MIGRATION_REQUIRED = YES
M4_MIGRATION_REQUIRED = YES
GLOBAL_RERUN_REQUIRED = NO
NEXT_ALLOWED_COMMAND = python -m pytest overall_run/tests/m1/test_config.py -q  # only after the existing m3_v3.yaml source is restored; do not synthesize it
```

## Decision Basis

- This semantic fix does not invalidate PRE data or require a PRE rebuild.
- PRE formal Fast bundle availability is still `NO`; producing that bundle is a separate existing PRE publication prerequisite, not a rerun caused by M1/M2 semantic changes.
- M1 architecture is unchanged, but the current lineage still has no completed formal retraining/calibration/resampling after the V2 contract work.
- M2 formal reconstruction remains blocked by parameter freeze and must be run only after new M1 samples and approved valuation/rule parameters exist.
- M3 still rejects the V2 sample-loss contract. M4 has not migrated and cannot consume unresolved-tail output.
- A global rerun is not meaningful or allowed while M2 parameters and M3/M4 interfaces remain open.

## Current Small-Test Boundary

Allowed verification has been completed. The remaining local test blocker is the missing, untracked `overall_run/config/m3_v3.yaml` required by `overall_run/src/config.py`. Restoring the intended existing source for that file is allowed; inventing a replacement in this task is not.

No training, calibration, production sampling, formal reconstruction, middle/full run, `overall_adv`, `part_adv`, or global rerun was launched.
