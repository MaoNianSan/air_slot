# Air Slot Performance Closure P0 and Morning Validation

Execution date: Monday, August 17, 2026

## Morning Start Status

```text
MORNING_START_STATUS

REPOSITORY_SHA = 6df4a31bac6c6cbe4d3de9455021976247871e79
WORKTREE_STATUS = DIRTY_P0_IMPLEMENTATION_AND_DIAGNOSTICS

PID_30364_EXISTS = FALSE
OTHER_M1_PROCESSES = NONE

H_SELECTION_TRAINING_ALREADY_STARTED = FALSE
TRAINING_RUNS_COMPLETED = 0

PREPARED_ARTIFACT_EXISTS = FALSE
BASE_CACHE_EXISTS = FALSE_AT_START
PERFORMANCE_P0_ALREADY_PARTIAL = TRUE

FINAL_TEST_ACCESS_COUNT = 0
OLD_BASELINE_PROCESS_STATUS = ALREADY_STOPPED
```

The previously observed run is retained as scale evidence only:

```text
OBSERVED_FULL_PREP_BASELINE_ELAPSED_SECONDS_APPROX = 1560
OBSERVED_SCOPE = Jan-Sep pairing completed; weather preparation in progress
TRAINING_STARTED = FALSE
OBSERVED_PEAK_RSS_MB_APPROX = 4958.3
```

This observation is not used as the controlled speedup denominator because it
did not finish the same endpoint as the optimized full build.

## Controlled Replay

The controlled cohort was fixed before the comparison:

```text
PROFILE_SCOPE = 2019-01:first_50000_projected_rows:SLC:8_episodes
PROFILE_INPUT_HASH = sha256:0f641ff4851d786b8f1d052790a1e6b8d00161844fedab6f7749a9818081095a
PROFILE_ROWS = 50000
PROFILE_EPISODES = 8
PROFILE_DECISION_NODES = 120
```

Old and optimized paths used the same raw rows, episodes, rolling nodes,
weather observations, labels, and tensor contract.

```text
CONTROLLED_BASELINE_SECONDS = 15.136411
CONTROLLED_OPTIMIZED_SECONDS = 7.224516
DATA_PREP_SPEEDUP = 2.095145x

PRIMARY_BOTTLENECK_BEFORE = pre_safe_feature_construction
TOP_3_HOTSPOTS_BEFORE = pre_safe_feature_construction, dtype_datetime_conversion, predecessor_successor_pairing

PRIMARY_BOTTLENECK_AFTER = dtype_datetime_conversion
TOP_3_HOTSPOTS_AFTER = dtype_datetime_conversion, predecessor_successor_pairing, parquet_read (actual source is CSV)
```

The main repair reuses one immutable `ProductionPREPublisher` for a preparation
run instead of reloading registry/config state for every decision node. The
controlled PRE construction stage improved by about 100x. The monthly chain
carry was also reduced from the previous full month to the last row per
aircraft, with a cross-month episode equivalence test.

## Equivalence

```text
DATA_EQUIVALENCE = PASS
NUMERICAL_EQUIVALENCE = PASS

episode IDs = EXACT
rolling decision-node IDs = EXACT
PRE decision-node IDs = EXACT
split = EXACT
labels = EXACT
active masks = EXACT
support states = EXACT
evidence states = EXACT
sequence lengths = EXACT
floating feature max abs difference = 0.0
floating tolerance = rtol 1e-6, atol 1e-7

CACHE_ROUNDTRIP = PASS
MICROBATCH_FULLBATCH_LOSS_ABS_DIFFERENCE = 1.7881393432617188e-07
MICROBATCH_PARAMETER_MAX_ABS_DIFFERENCE = 5.960464477539063e-08
BATCHED_INFERENCE_MAX_ABS_DIFFERENCE = 2.384185791015625e-07
OPTIMIZER_STEPS_PER_EPOCH = 1
```

## Canonical Base Cache

```text
FULL_CACHE_STATUS = PASS
FULL_CACHE_BUILD_SECONDS = 1352.318455
FULL_CACHE_BUILD_MINUTES = 22.538641
WARM_CACHE_LOAD_SECONDS = 0.076606

CACHE_SCHEMA = M1_DEVELOPMENT_BASE_CACHE_V1
CACHE_HASH = sha256:9c647c03a4bb59d8cc6568e14a34f431f5da84b6d179e55d2e416fe7e7ed180a
CACHE_BYTES = 356666

TRAIN_EPISODES = 128
CALIBRATION_EPISODES = 64
DEVELOPMENT_EPISODES = 128
FULL_CACHE_EPISODES = 320
FULL_CACHE_NODES = 4979
FEATURE_COUNT = 103

RAW_PARQUET_FILES_READ_DURING_WARM_LOAD = 0
PAIRING_REBUILT_DURING_WARM_LOAD = 0
WEATHER_REBUILT_DURING_WARM_LOAD = 0
PRE_SEQUENCE_REBUILT_DURING_WARM_LOAD = 0
CACHE_REUSE_STATUS = PASS

FINAL_TEST_INCLUDED_IN_CACHE = FALSE
FINAL_TEST_ACCESS_COUNT = 0
```

The full optimized build includes preparation through immutable cache write and
warm validation. The old 26-minute observation stopped at weather preparation,
so the full-build ratio is contextual evidence, not the controlled 2x gate.

Peak RAM decreased from the observed old value of about 4958.3 MB to 2769.9 MB,
an approximate reduction of 44.1 percent.

## One-Seed H16 Benchmark

Only `H=16`, principal seed `20260813`, was run.

```text
ONE_SEED_H16_STATUS = PASS
CACHE_LOAD_SECONDS = 0.051242
TRAIN_SECONDS_TOTAL = 4.813901
SECONDS_PER_EPOCH = 0.601738
CALIBRATION_SECONDS = 0.137131
DEVELOPMENT_INFERENCE_SECONDS = 0.542238
PEAK_RSS_MB = 318.934
DEVICE = cpu
THREAD_CONFIG = torch intra-op 8, inter-op 16
PARAMETER_COUNT_H16 = 10798
DEVELOPMENT_EPISODE_BALANCED_JOINT_NLL = 4.293847241167518
AVERAGE_CPU_UTILIZATION = NOT_CAPTURED_RETROSPECTIVELY
```

The CPU utilization field is an observability gap in this completed benchmark;
it is not inferred from wall time. Epoch, loss, elapsed time, ETA, RSS, cache
status, month progress, and resume manifests were captured.

## Runtime Estimate

The H32 estimate uses the parameter-count ratio only; H32 was not run.

```text
PARAMETER_COUNT_H32 = 23006
H32_TO_H16_PARAMETER_RATIO = 2.130580

ESTIMATED_H16_FIVE_SEED_SECONDS = 27.466353
ESTIMATED_H32_FIVE_SEED_SECONDS = 58.519255
ESTIMATED_TOTAL_10_RUN_SECONDS = 85.985608
ESTIMATED_TOTAL_10_RUN_MINUTES = 1.433093
```

## Authorization Gate

```text
AIR_SLOT_MORNING_PERFORMANCE_VALIDATION

OLD_BASELINE_PROCESS_STATUS = ALREADY_STOPPED

DATA_EQUIVALENCE = PASS

PRIMARY_BOTTLENECK = dtype_datetime_conversion
TOP_3_HOTSPOTS = dtype_datetime_conversion, predecessor_successor_pairing, CSV read

DATA_PREP_SPEEDUP = 2.095145x

FULL_CACHE_STATUS = PASS
FULL_CACHE_BUILD_TIME = 1352.318455 seconds
WARM_CACHE_LOAD_TIME = 0.076606 seconds

FINAL_TEST_ACCESS_COUNT = 0

ONE_SEED_H16_STATUS = PASS
ONE_SEED_H16_TRAIN_TIME = 4.813901 seconds

ESTIMATED_10_RUN_H_SELECTION_TIME = 85.985608 seconds (engineering estimate)

NUMERICAL_EQUIVALENCE = PASS
CACHE_REUSE_STATUS = PASS

HEARTBEAT_STATUS = PARTIAL_STRICT_CADENCE_GAP
RESUME_STATUS = PASS_MONTH_AND_H_SEED_MANIFESTS

SCENARIO_VECTORIZATION_STATUS = NOT_IMPLEMENTED_NONBLOCKING_P1
M4_VECTORIZATION_STATUS = NOT_IMPLEMENTED_NONBLOCKING_P1

PERF_AUTHORIZE_FULL_H_SELECTION = HUMAN_DECISION_REQUIRED
PAPER_FULL_RUN = FALSE
```

```text
HUMAN_DECISION_REQUIRED

DECISION_ID = PERF_AUTHORIZE_FULL_H_SELECTION

CODEX_RECOMMENDATION = PROCEED
RECOMMENDED_USER_RESPONSE = APPROVE H_SELECTION_RUN
```

No H32 run, additional H16 seed, W comparison, Final Test, paper_full, or
Exp2-Exp4 execution occurred.

The completed full build emitted monthly completion heartbeats at roughly
108-150 second intervals and a 45-second typed/weather phase heartbeat. This is
useful progress evidence but does not fully satisfy the requested 30-60 second
cadence during the monthly pairing phase.
