# M3 V2 Rerun Decision

Date: 2026-08-06

```text
PRE_RERUN_REQUIRED = NO
M1_RETRAIN_REQUIRED = NO
M1_RECALIBRATION_REQUIRED = NO
M1_RESAMPLE_REQUIRED = NO
M2_FORMAL_RECONSTRUCTION_REQUIRED = NO
M3_PARAMETER_FREEZE_REQUIRED = YES_LATER
M3_FORMAL_LIBRARY_REQUIRED = YES_AFTER_FREEZE
M4_MIGRATION_REQUIRED = YES_LATER
GLOBAL_RERUN_REQUIRED = NO
GLOBAL_RERUN_ALLOWED = NO
```

This change alters only the M3 structural catalog, legacy module placement, readiness gates, tests, and documentation. It does not change PRE, M1, M2 reconstruction, formal M3 parameters, or M4 ranking.

The next allowed instruction is either a human diff review or a separately authorized M3 parameter-freeze task based on development evidence. No formal pipeline command is currently allowed.
