# M1-M2 V2 Semantic Fix Test Report

Date: 2026-08-06

## Executed Checks

| Check | Result | Notes |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m compileall -q overall_run/src/m1 overall_run/src/m2` | PASS | M1/M2 compile only |
| `python -m pytest overall_run/tests/m1 --ignore=overall_run/tests/m1/test_config.py -q` | 58 passed | Four existing sklearn single-label warnings |
| `python -m pytest overall_run/tests/m2 -q` | 59 passed | Includes PRE-to-M2 integration and pipeline mismatch smoke |
| Combined allowed M1/M2 suite with the same exclusion | 117 passed | No long run |
| `python -m pytest overall_run/tests/test_m2_m4_contract.py -q` | 1 skipped | Expected retired scalar-contract block |
| `git diff --check` | PASS | Only repository LF/CRLF conversion warnings |

The repository `.venv` does not contain pytest, so compilation used `.venv` and tests used the available system Python 3.11 environment. No package installation was performed.

## Acceptance Coverage

- `None`, NaN, unsupported, and unresolved values do not become zero.
- Observed zero and predicted zero remain distinct, valid zero events.
- All nine subitems are parameterized across missing event, missing context, missing rule, missing `v_gj`, proxy, disabled, and tail states.
- Availability, margin, flexibility, and airport-flow direction monotonicity is tested.
- Multipliers vary on `[0,1]`, respect configured bounds, and reject missing parameters.
- PRE synthetic published bundle flows through context builder, adapter, reconstruction, summary, and provenance checks.
- Unresolved probability bounds, resolved-only q95/CVaR, formal q95/CVaR block, and M4 tail gate are tested.
- Missing currency channels fail; changed rates affect RMB only; identity mapping remains exact.
- Channel shares sum to one for positive total loss; zero total loss reports `ZERO_TOTAL_LOSS`.
- Empirical turnaround reference activates `F_TURN` as proxy without changing the M1 hard-floor reference.
- Joint-tail evaluation does not change the sampling model.
- `run_experiment()` continues to raise `M3_CONTRACT_MISMATCH`.

## Existing Repository Blocker

Running the unexcluded full M1/M2 command produced:

```text
116 passed, 1 skipped, 3 failed
```

All three failures are in `overall_run/tests/m1/test_config.py` before their intended assertions. `overall_run/src/config.py` requires `overall_run/config/m3_v3.yaml`, but that file does not exist and is not tracked in the current repository. The failure is `ConfigError: Missing configuration file: .../overall_run/config/m3_v3.yaml`.

This task did not synthesize an M3 configuration or relax the loader because that would cross the explicit M3 migration boundary. The one-line missing `pytest` import in the already module-skipped `test_m2_m4_contract.py` was repaired so the intended skip can be collected.

## Runtime Boundary

No PRE rebuild, model training, calibration, production sampling, formal M2 reconstruction, M3/M4 migration, middle/full run, global rerun, `overall_adv`, or `part_adv` was executed.
