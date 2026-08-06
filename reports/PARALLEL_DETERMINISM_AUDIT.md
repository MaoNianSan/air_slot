# Parallel Determinism Audit

Audit date: 2026-08-02

PARALLEL_DETERMINISM_STATUS=PASS

- Shared PRE input: `pre/output/fast_three_change_dev`.
- 1-thread downstream output: `fast_code_audit_n1`.
- 14-thread comparison output: `fast_three_change_dev`.
- Compared parquet file-set entries: 63; missing-side failures: 0.
- Compared parquet files: 63; scientific-content failures: 0.
- Numeric tolerance: atol=1e-10, rtol=1e-12.
- Maximum scientific numeric absolute difference: 0.0.
- Ranking/candidate/recommendation parquet files: 15; failures: 0.
- Compared summary/registry logical files: 6; failures: 0.
- Runtime-only exclusions: run IDs, timestamps, paths, config/implementation/artifact hashes, worker metadata, and performance timing fields.

Detailed comparisons are in `PARALLEL_DETERMINISM_FILE_SET.csv`, `PARALLEL_DETERMINISM_FILE_COMPARISON.csv`, and `PARALLEL_DETERMINISM_REGISTRY_COMPARISON.csv`.
