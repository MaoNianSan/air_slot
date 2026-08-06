# M1-M2 V2 Rerun Decision

Date: 2026-08-06

    PRE_RERUN_REQUIRED=NO
    M1_RETRAIN_REQUIRED=YES
    M1_RESAMPLE_REQUIRED=YES
    M2_RECONSTRUCTION_REQUIRED=YES
    M3_MIGRATION_REQUIRED=YES
    M4_MIGRATION_REQUIRED=YES
    GLOBAL_RERUN_REQUIRED=NO_CURRENTLY
    NEXT_ALLOWED_COMMAND=python -m pytest overall_run/tests/m1 overall_run/tests/m2 -q

## Rationale

- PRE can be reused from an accepted published bundle.
- M1 architecture is unchanged, but feature schema, snapshot semantics,
  checkpoint identity, and sampling/tail artifacts changed.
- Existing M1 samples must be regenerated.
- M2 losses must be reconstructed from regenerated scenarios.
- M3 and M4 must migrate before a global formal rerun.
- A global rerun is not meaningful while M3/M4 remain mismatched.

## Approved Order After Parameter Freeze

    1. python -m compileall -q overall_run/src/m1 overall_run/src/m2
    2. python -m pytest overall_run/tests/m1 overall_run/tests/m2 -q
    3. Freeze M1 training config, empirical-tail support, M2 rules, and v[g,j]
    4. Wire and run the approved M1 training/checkpoint CLI
    5. Fit and save the calibration temperature artifact
    6. Regenerate M1ScenarioBundle samples
    7. Run M2 DIRECT_STRUCTURAL_COMPACT reconstruction
    8. Migrate and validate M3
    9. Migrate and validate M4
    10. Decide whether guarded fast overall_run is allowed

No training command is invented here because the current runner is a Python
API and hyperparameters are intentionally REQUIRES_DEVELOPMENT_FREEZE.
