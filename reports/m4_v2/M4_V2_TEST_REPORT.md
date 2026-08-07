# M4 V2 Test Report

Date: 2026-08-07

## Results

```text
compileall overall_run/src and ranking_contract.py = PASS
M4 tests = 105 passed
Ranking@1/@2/@3/@5 tests = 7 passed
M1 regression = 61 passed, 4 existing sklearn single-label warnings
M2 regression = 59 passed
M3 regression = 31 passed
```

Tests were launched from the repository root with `PYTHONPATH=overall_run` so
the existing `src` package layout resolves consistently. The raw command
without that environment setting stopped during collection with
`ModuleNotFoundError: src`; no test body ran in that attempt.

The M4 suite now covers strict config rejection, authoritative implementation
hash membership, fixture-only M3 gate passage into M4, one authoritative sort,
cost tie-break preservation, status priority, publication reason codes,
bundle-level output, evaluation configuration, evaluation failure isolation,
formal hash equality with evaluation on/off, and active legacy absence.

Only synthetic or explicitly mocked frozen fixtures were used. Pytest formal
output was written only under temporary test directories. No Fast, Middle,
Full, PRE rebuild, M1 retraining, M2 freeze, M3 freeze, or formal M3 library run
was performed.
