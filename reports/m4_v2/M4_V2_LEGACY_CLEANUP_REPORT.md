# M4 V2 Legacy Cleanup Report

Date: 2026-08-07

## Isolated

```text
overall_run/src/m4.py -> overall_run/src/legacy/m4_v1_api.py
overall_run/src/m4_screening.py -> overall_run/src/legacy/m4_v1_screening.py
overall_run/src/m4_evaluation.py -> overall_run/src/legacy/m4_v1_evaluation.py
```

The active import is now `overall_run/src/m4/__init__.py`. Retired calls to
`fit_m4`, `evaluate_m4`, or `screen_physical_actions` raise
`M4_LEGACY_CONTRACT_RETIRED` and do not fall back to the old channel contract.

The `m4_pnb_*` modules and `audit_m4_positive_net_benefit.py` remain in place
only for historical audit reproducibility and are marked
`LEGACY_M4_NOT_FORMAL = True`. They are absent from the authoritative
implementation manifest and formal pipeline.

No historical report or generated output was deleted.
