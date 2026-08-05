# PRE Core V2 Membership benchmark

Date: 2026-08-05

## Gate result

```text
MEMBERSHIP_CORRECTNESS_STATUS=PASS
MEMBERSHIP_PERFORMANCE_STATUS=PASS
REAL_PARTITION_BENCHMARK_STATUS=PASS
FULL_FAST_STARTED=NO
```

## Real partition

The benchmark selected the real Fast state/date partition with the largest
Parquet row count and read only the fields required by the V2 Membership join.
The local source staging artifact was not modified.

```text
source_partition=local Core staging/observations/source=state/observation_date=2022-05-16/part-00000.parquet
observation_date=2022-05-16
observation_rows=2094689
request_rows_real=3013
request_rows_total=3014
identity_groups=1702
overlapping_request_rows=244
no_match_request_rows=1
membership_rows=2105225
elapsed_seconds=51.294190
peak_rss_mb=2600.324
peak_incremental_memory_mb=1459.191
observation_rows_per_second=40836.770
membership_rows_per_second=41042.173
result_hash=59097d3c31ffce30035957cc727b841c42139df6a0f26ad99fd5468d1485c1a4
```

The extra request uses an aircraft identity absent from the partition and
produced no Membership row. The complete partition contained multiple
aircraft and overlapping requests. The join operates per identity with sorted
event times and `numpy.searchsorted`; it does not scan the full source frame
once per request.

## Correctness reference

The former brute-force algorithm was restricted to a safe real-data subset.
Its complete Membership output matched the interval join exactly.

```text
subset_observation_rows=16000
subset_request_rows=19
subset_membership_rows=16291
brute_force_seconds=1.458016
interval_join_seconds=0.405778
subset_speedup=3.59x
subset_result_hash=f0c3bae6cb4d5f328d30c587beca416bcde0f36519a7364f1d4bc3945df44557
correctness_status=PASS
```

Unit tests separately cover overlapping many-to-many requests, cross-date
requests, vectorized Membership roles, split neutrality, and partition Resume.

## Join-only projection

The projection uses the largest Fast partition as a conservative per-date
estimate. It excludes state extraction, Observation construction, Parquet I/O,
Weather/Flow work, and finalization.

| Profile | State dates | Sequential | Ideal 4-worker compute |
| --- | ---: | ---: | ---: |
| Fast | 5 | 4.27 min | 1.07 min |
| Middle | 72 | 61.55 min | 15.39 min |
| Full | 181 | 154.74 min | 38.68 min |

Measured memory is bounded to one partition per worker. Worker concurrency must
still be selected against the memory available on the machine running the tool.

## Reproduction

The public tool is read-only and writes no benchmark data:

```powershell
python pre/tools/pre_core_v2_membership_benchmark.py --help
python pre/tools/pre_core_v2_membership_benchmark.py --partition "<local-state-partition.parquet>"
```

Use `--requests "<local-request-dataset>"` when request columns are not embedded
in the selected partition. Missing data or staging paths fail with an explicit
`BENCHMARK_INPUT_ERROR`.

These measurements are implementation and pre-run validation evidence. They
are not a formal Fast V2 bundle result.
