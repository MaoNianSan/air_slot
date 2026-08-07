# M4 V2 Test Report

Date: 2026-08-07

## Results

```text
compileall M4/package/legacy/pipeline/tests = PASS
M4 tests = 70 passed
M1 tests = 61 passed, 4 sklearn single-label warnings
M2 tests = 59 passed
M3 tests = 31 passed
Ranking@1/@2/@3/@5 tests = 7 passed
```

The M4 suite covers contract rejection, PRE evidence boundaries, explicit
stage and opportunity handling, stable draw pairing, row/worker invariance,
nine-subitem post loss, A00 identity, channel-cost single addition, weighted
mean/Var/CVaR, paired improvement, all four decision lanes, one authoritative
ranking, null padding, synthetic publication isolation, and evaluation output
isolation.

Only synthetic M2/M3 fixtures marked test-only were used for M4 execution.
No formal output directory or publication registry was written.
