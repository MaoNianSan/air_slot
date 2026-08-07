# M4 V2 Legacy Cleanup Report

Date: 2026-08-07

## Active module state

The ambiguous active modules are absent:

```text
overall_run/src/m4.py
overall_run/src/m4_screening.py
overall_run/src/m4_evaluation.py
```

Historical source is isolated as:

```text
overall_run/src/legacy/m4_v1_api.py
overall_run/src/legacy/m4_v1_screening.py
overall_run/src/legacy/m4_v1_evaluation.py
```

Each file declares `LEGACY_M4_NOT_FORMAL = True` and is excluded from
`AUTHORITATIVE_CODE`. The active import resolves to
`overall_run/src/m4/__init__.py`; the formal pipeline imports that package.

The `m4_pnb_*` modules and `audit_m4_positive_net_benefit.py` remain historical
audit code. They already declare `LEGACY_M4_NOT_FORMAL = True`, are not imported
by the formal M4 V2 pipeline, and are not part of the M4 V2 authoritative
package. Historical report consumers and generated legacy outputs were not
deleted.
