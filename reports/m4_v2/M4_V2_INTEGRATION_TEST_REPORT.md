# M4 V2 Integration Test Report

Date: 2026-08-07

## Commands and results

```text
D:/Python311/python.exe -m compileall -q overall_run/src ranking_contract.py
PASS

PYTHONPATH=overall_run pytest -q overall_run/tests/m4
105 passed

PYTHONPATH=overall_run pytest -q overall_run/tests/test_ranking_1235.py
7 passed

PYTHONPATH=overall_run pytest -q overall_run/tests/m1
61 passed, 4 existing sklearn warnings

PYTHONPATH=overall_run pytest -q overall_run/tests/m2
59 passed

PYTHONPATH=overall_run pytest -q overall_run/tests/m3
31 passed
```

## Integration evidence

- The real current config still stops at `M3_PARAMETER_NOT_FROZEN`.
- A mocked future fixture with M3 gates passed reaches M4 V2, writes the formal
  bundle, runs the configured evaluation after freeze, and reaches finalization.
- Test-only M2/M3 inputs cannot bypass formal mode.
- Evaluation on/off produces identical formal episode, action, and manifest
  hashes.
- Evaluation failure with `fail_on_error=false` leaves formal status PASS and
  records evaluation FAIL.
- Ranking prefixes preserve the supplied authoritative order and padding does
  not enter metrics.
- No active `m4.py`, `m4_screening.py`, or `m4_evaluation.py` exists.

The direct pytest command without `PYTHONPATH=overall_run` failed during import
collection before running tests. The documented command now includes the
required environment setting.
