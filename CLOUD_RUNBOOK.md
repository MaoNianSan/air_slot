# Air Slot Cloud Runbook

## 1. Frozen scope

- Contract: `Y_MOVEMENT_RAW_V1_20260725`
- Formal target: `y_movement_raw`
- Sensitivity-only target: `y_movement_model`
- Frozen Fast model SHA256:
  `422b50378a1f4431813d84efbb0473284debe13fe03bd77864db3da94e026cf2`
- Cloud scientific mode: `CURRENT_DATA_ADAPT_FULL`
- Formal 72-day Full allowed: `false`

The Fast q95 classification is `SYSTEMATIC_CALIBRATION_CONCERN` with
`METRIC_SUPPORT_LIMITED` certification. This does not authorize model, feature,
quantile, calibration, cohort, policy, or seed changes.

## 2. Synchronize in place

1. Synchronize this `explore` tree to one cloud working directory.
2. Synchronize `data/` separately and enforce read-only permissions.
3. Synchronize `pre/cache/` separately and preserve every payload hash.
4. Install Python 3.11 dependencies from `requirements.txt`.
5. Verify frozen data manifests and `FINAL_CODE_FREEZE_SUMMARY.json`.
6. Confirm no Air Slot Python process is already running.

## 3. Clean Fast outputs

Inspect first, then clean downstream to upstream:

```powershell
python part_adv/clean.py --mode fast --dry-run
python overall_adv/clean.py --mode fast --dry-run
python overall_run/clean.py --mode fast --dry-run
python pre/clean.py --mode fast --dry-run

python part_adv/clean.py --mode fast
python overall_adv/clean.py --mode fast
python overall_run/clean.py --mode fast
python pre/clean.py --mode fast
```

Stop if a cleaner reports an active worker, lock, staging file, partial
artifact, or stale checkpoint. Do not use `--stop-owned-processes` unless the
recorded module, mode, run ID, PID, and ownership all match the intended run.

## 4. Authoritative Fast smoke

Run the complete chain with one job:

```powershell
python -u pre/main.py fast --progress normal --n-jobs 1
python -u pre/main.py validate fast --progress normal --n-jobs 1
python -u overall_run/main.py fast --progress normal --n-jobs 1
python -u overall_run/main.py validate fast --progress normal --n-jobs 1
python -u overall_adv/main.py fast --progress normal --n-jobs 1
python -u overall_adv/main.py validate --mode fast --progress normal --n-jobs 1
python -u part_adv/main.py fast --progress normal --n-jobs 1
python -u part_adv/main.py validate --mode fast --progress normal --n-jobs 1
python corrected_fast_post_rebuild_audit.py
```

Stop on the first nonzero exit. The model SHA, prediction SHA, scientific
hashes, formal target hash, cohort hash, q95/q99, coverage, CRPS, twCRPS, and
crossing results must reproduce the frozen baseline.

## 5. Parallel Fast compatibility

After the single-thread smoke passes, clean Fast again and run the same complete
chain with `--n-jobs 2`. Validate zero leakage, zero stale artifacts, stable
task seed hashes, identical cohort and decision keys, and numerical deltas.

Use parallel cloud execution only when this compatibility run passes. Start a
long run at `--n-jobs 2` or `--n-jobs 4`; do not begin a long run with
`--n-jobs -1`.

## 6. CURRENT_DATA_ADAPT_FULL

Use the frozen `data/manifests/current_data_adapt_full_manifest.csv` and
`data/manifests/current_data_adapt_full_manifest.json`. A missing or mismatched
manifest blocks execution.

Run sequentially:

```powershell
python -u pre/main.py adapt_full --progress normal --n-jobs 2
python -u pre/main.py validate adapt_full --progress normal --n-jobs 2
python -u overall_run/main.py adapt_full --progress normal --n-jobs 2
python -u overall_run/main.py validate adapt_full --progress normal --n-jobs 2
python -u overall_adv/main.py adapt_full --progress normal --n-jobs 2
python -u overall_adv/main.py validate --mode adapt_full --progress normal --n-jobs 2
python -u part_adv/main.py adapt_full --progress normal --n-jobs 2
python -u part_adv/main.py validate --mode adapt_full --progress normal --n-jobs 2
python finalize_current_data_adapt_full.py
```

Do not launch the three downstream long modules simultaneously.

## 7. Monitor and resume

Monitor CPU, memory, heartbeat timestamp, current stage, running task IDs,
completed task count, pending task count, checkpoint path, and task throughput.
Reduce `n_jobs` if memory pressure appears.

For an isolated `overall_run` failure, resume only from its explicit staging
directory:

```powershell
python overall_run/main.py fast --resume PATH --progress normal --n-jobs 2
```

For hash-valid incomplete downstream output:

```powershell
python overall_adv/main.py adapt_full --resume --progress normal --n-jobs 2
python part_adv/main.py adapt_full --resume --progress normal --n-jobs 2
```

Resume is rejected when input, scientific configuration, target contract, task
partition, or completed task hashes differ.

## 8. Hard stop conditions

Stop immediately for a formal label other than `y_movement_raw`, label-lineage
ambiguity, future leakage, test-fit use, unsupported Passenger evidence replaced
with zero, input/cache/registry hash mismatch, projected crossing above zero,
stale or incomplete artifacts, unknown workers, or any attempted write under
`data/`.

Do not run formal 72-day Full or Precision in the current stage.
