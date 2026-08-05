# PRE Core V2 contract gate

Date: 2026-08-05

```text
PRE_CORE_V2_CONTRACT_STATUS=PASS
RESEARCH_RESUME_IDENTITY_STATUS=PASS
FROZEN_CONFIG_STATUS=PASS
PASS_EMPTY_STATUS=PASS
MEMBERSHIP_INTERVAL_JOIN_STATUS=PASS
MEMBERSHIP_PARTITION_STATUS=PASS
MEMBERSHIP_CORRECTNESS_STATUS=PASS
MEMBERSHIP_PERFORMANCE_STATUS=PASS
REFERENCE_MEMBERSHIP_ADAPTATION_STATUS=PASS
INDEPENDENT_VALIDATION_STATUS=PASS
EXTRA_FILE_DETECTION_STATUS=PASS
STATISTICS_RECOMPUTATION_STATUS=PASS
COMPILE_STATUS=PASS
TEST_STATUS=PASS_74_TESTS
SYNTHETIC_SMOKE_STATUS=PASS
REAL_PARTITION_BENCHMARK_STATUS=PASS
FULL_FAST_RERUN_ALLOWED=YES
NEXT_ALLOWED_STEP=RESUME_FAST_CORE_BUILD_AND_FINALIZATION
```

## Contract evidence

- Resume hard identity is `AIR_CHAIN_CORE_V2_R2` plus the frozen scientific
  configuration, source/request identity, episode intervals, cache key, and
  expected partitions.
- Git and implementation changes are provenance warnings, not hard Resume
  gates.
- Observation and Membership manifests support `PASS`, `PASS_EMPTY`, `FAIL`,
  and `IN_PROGRESS`; legal empty partitions have no Parquet file.
- Membership is partitioned by `source/observation_date`, written atomically,
  validated before manifest completion, and resumed by hash, schema, and row
  count.
- Reference construction reads matching training Membership and Observation
  partitions with only the columns required for sufficient statistics.
- Independent validation detects unregistered, missing, and duplicate files;
  `PASS_EMPTY` file conflicts; partition identity violations; and stored versus
  recomputed key-statistics mismatches.

## Validation snapshot

- `python -m compileall -q pre/src pre/tests pre/tools`: PASS.
- `python -m pytest -q pre/tests`: 74 passed in 17.39 seconds.
- Synthetic partition smoke: 5 passed in 1.55 seconds, including Observation
  `PASS_EMPTY`, Membership `PASS_EMPTY`, and partition Resume reuse.
- Largest real state/date benchmark: PASS on 2,094,689 observations; see
  `PRE_CORE_V2_MEMBERSHIP_BENCHMARK.md`.
- `git diff --check`: PASS; only line-ending conversion warnings were emitted.
- Full Fast started: NO.

This report authorizes the next engineering step but does not execute it. It is
implementation and pre-run validation evidence, not a formal Fast V2 bundle.
