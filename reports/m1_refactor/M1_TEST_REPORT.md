# M1 Test Report

Generated: 2026-08-05 (Asia/Hong_Kong)

## Commands

```powershell
D:/Python311/python.exe -m compileall -q pre/src pre/tests pre/tools
D:/Python311/python.exe -m pytest -q pre/tests
D:/Python311/python.exe -m compileall -q overall_run/src/m1 overall_run/tests/m1
D:/Python311/python.exe -m pytest -q overall_run/tests/m1
git diff --check
```

## Results

| Gate | Result |
|---|---|
| PRE compile | PASS |
| PRE tests | PASS, 71 tests |
| M1 compile | PASS |
| M1 tests | PASS, 46 tests |
| Synthetic published bundle | PASS |
| Future-information counterexample | PASS |
| Membership many-to-many join | PASS |
| Duplicate state update | PASS, zero duplicate commit |
| Temporary state pollution | PASS, zero committed preview state |
| Fixed-random sampling | PASS |
| Physical sample identity | PASS |
| Retired-token scan | PASS, zero formal matches |
| `git diff --check` | PASS |

Four sklearn warnings arise from deliberately single-class threshold fixtures;
they do not indicate test failures.

The user explicitly limited this close-out to M1, so the unrelated historical
overall_run M2-M4 suite is not an M1 acceptance gate in this report.
