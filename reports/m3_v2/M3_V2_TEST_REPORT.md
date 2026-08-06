# M3 V2 Test Report

Date: 2026-08-06

## Acceptance Checks

```text
python -m compileall -q overall_run/src/m3 overall_run/tests/m3
PASS

python -m pytest -q overall_run/tests/m3 \
  -k "not old_m4_rejects_v4_artifact_and_catalog"
23 passed, 1 deselected in 1.50s
```

Covered behaviors include explicit V4 loading, V3 exclusion from the active path, exact 18-action identity, forbidden action IDs and combination names, footprint schema and structural zeros, A00 identity, fixed-seed reproducibility, stable hashes, shared response intensity, non-negative costs, M2 compatibility failure codes, parameter-freeze blocking, and M3/M1 sample separation. The M4 mismatch test was deliberately excluded from the final M3-only verification scope.

Only synthetic fixtures marked `test_only` were used to exercise stochastic structure. They are not formal response or cost parameters and are not publication evidence.

## Historical Checks

Three retired V2/V3 M3 test modules were skipped by their explicit `LEGACY_AUDIT_ONLY` or retired-contract markers. The broader historical `test_refactor_contract.py` suite was also inspected but is not an M3 V4 acceptance suite; it reported failures from unavailable archived Parquet fixtures, historical M2 configuration expectations, and a subprocess import environment. No full or production run was started to satisfy those historical checks.
