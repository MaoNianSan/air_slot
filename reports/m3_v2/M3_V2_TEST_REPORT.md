# M3 V2 Test Report

Date: 2026-08-06

## Acceptance Checks

```text
python -m compileall -q overall_run/src/m3 overall_run/src/legacy overall_run/tests/m3
PASS

python -m pytest -q overall_run/tests/m3
31 passed in 1.99s

python -m pytest -q overall_run/tests/m3/test_compatibility_and_gates.py
8 passed in 0.73s

python -m pytest -q overall_run/tests/test_m2_m4_contract.py
1 passed, 7 legacy scalar tests skipped in 3.92s
```

Covered behaviors include explicit V4 loading, exact 21-action identity, A51-A53 aircraft semantics, A54-A55 rejection, combination-token rejection, footprint schema and structural zeros, A00 identity, fixed-seed reproducibility, stable hashes, shared response intensity, non-negative costs, M2 compatibility failure codes, legacy import isolation, staged pipeline blocking, M3/M1 sample separation, and explicit old-M4 rejection of both the V4 artifact and catalog.

Only synthetic fixtures marked `test_only` were used to exercise stochastic structure. They are not formal response or cost parameters and are not publication evidence.

## Historical Checks

The seven skipped tests in `test_m2_m4_contract.py` exercise the retired scalar M2-to-M4 path. The active V4 rejection test in that file executed and passed; the M4 boundary was not skipped, deselected, or xfailed. No full or production run was started.
