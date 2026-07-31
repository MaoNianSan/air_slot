# Air Slot

## 1. Project purpose

Air Slot studies airline disruption recovery under delayed information. It
builds a distributional residual-risk model, maps that uncertainty into the
M1-M4 recovery chain, and evaluates both the overall global policy advantage
and the contribution of selected submodules.

The repository is a scientific execution tree, not a package or a service.
Fast is the reproducible engineering baseline. Multi-day scientific evaluation
uses the frozen current-data workflow after the Fast gates pass.

## 2. Repository architecture

```text
data/
pre/
overall_run/
overall_adv/
part_adv/
```

The only formal dependency graph is:

```text
data -> pre -> overall_run
                      |-> overall_adv
                      `-> part_adv
```

`data/` is strictly read-only. PRE is the only raw-data processing layer.
Downstream modules read published PRE or overall-run artifacts; they do not
read `data/raw/`, read PRE staging data, or rebuild episodes, snapshots, rules,
or evidence.

## 3. Scientific modules

- M1: calibrated LightGBM quantile ensemble for residual movement risk.
- M2: three-channel operational-quantity construction and RMB cost conversion
  for flight operation, passenger service, and recovery resources.
- M3: one frozen, episode-independent stochastic action-response library.
- M4: physical screening, decision-value screening, total-RMB residual-risk
  scoring, and action ranking.
- `overall_adv`: paired `LOCAL_F` versus `GLOBAL_FPR` evaluation.
- `part_adv`: M1, M2, and M4 baselines and ablations. It does not compare M3.

## 4. Data contract

PRE publishes exactly five formal tables:

```text
episodes.parquet
snapshots.parquet
calibration.parquet
rules.parquet
evidence_audit.parquet
```

The formal label is `y_movement_raw`. `y_movement_model` is sensitivity-only.
The contract version is `Y_MOVEMENT_RAW_V1_20260725`.

Passenger evidence uses `DESTINATION_LAGGED_MONTH`. Insufficient historical
support is `UNSUPPORTED`: it is not replaced with zero and it is not filled by
cross-day interpolation.

## 5. Installation

Use Python 3.11 and the root dependency contract:

```powershell
python -m pip install -r requirements.txt
```

There are no module-level requirements files.

## 6. Run modes

- `fast`: engineering regression and scientific precheck.
- `diagnostic`: independent diagnostic evaluation, not a substitute for Full.
- `adapt_full`: `CURRENT_DATA_ADAPT_FULL`, using the frozen available-data
  manifest for multi-day scientific evaluation.
- `full`: formal 72-day design. It is not allowed in the current stage.
- `precision`: convergence evaluation after an accepted `adapt_full` or formal
  Full run. It remains blocked until the parent scientific status is PASS.

Mode availability is enforced by each module CLI and its scientific gates.

## 7. Fast workflow

Run from this directory, in order:

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

`--n-jobs 1` is the authoritative exact-reproduction path.

## 8. CURRENT_DATA_ADAPT_FULL workflow

After the cloud Fast smoke passes, run the long chain sequentially:

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

Do not launch the three downstream long chains concurrently. The formal 72-day
Full remains prohibited.

## 9. Clean and resume

Clean is always an explicit, independent command:

```powershell
python pre/clean.py --mode fast --dry-run
python pre/clean.py --mode fast
python overall_run/clean.py --mode fast
python overall_adv/clean.py --mode fast
python part_adv/clean.py --mode fast
```

`main.py` never calls `clean.py`. A cleaner removes only its own
`output/<mode>/`; it preserves `data/` and `pre/cache/`. It refuses an active
owned run by default. `--stop-owned-processes` is available only when module,
mode, run ID, PID, and ownership metadata all match.

`overall_run` resumes only from an explicit isolated staging path:

```powershell
python overall_run/main.py fast --resume PATH --progress normal --n-jobs 1
```

`overall_adv` and `part_adv` use `--resume` for a hash-valid incomplete mode
output. Input, scientific configuration, task partition, target contract, and
task output hashes must match; changing only `n_jobs` does not change task
identity.

## 10. Parallel execution

`--n-jobs 1` is the default. Use `--n-jobs 2` or `--n-jobs 4` for a bounded
cloud run after the single-thread smoke passes. `--n-jobs -1` resolves to all
but one logical CPU, but it should not be the first setting for a long run.

The runtime enforces one total CPU budget, prevents nested model parallelism,
derives seeds from stable task IDs rather than worker IDs, merges in fixed task
order, and keeps registry publication in the parent process. The implementation
is compatible with Windows spawn and Linux execution.

## 11. Output structure

Each module owns `output/<mode>/`. A mode directory is created by its cleaner
or runner. The published Fast directories contain the module-specific
`run_summary.json`, `run_state.json`, artifact registry, metrics or tables,
figures where applicable, logs, heartbeats, and checkpoints.

Key current locations are:

```text
pre/output/fast/
overall_run/output/fast/
overall_adv/output/fast/
part_adv/output/fast/
overall_run/output/fast/audit/
pre/cache/
```

Staging or partial artifacts are never accepted as published output.

## 12. Current frozen status

- Formal target: `y_movement_raw`
- Code frozen: `true`
- Fast q95 empirical exceedance: `0.0609375`
- q95 classification: `SYSTEMATIC_CALIBRATION_CONCERN`
- Certification: `METRIC_SUPPORT_LIMITED`
- Cloud mode: `CURRENT_DATA_ADAPT_FULL`
- Formal 72-day Full allowed: `false`

The q95 result is a cloud multi-day scientific evaluation target. It is not an
authorization for further local tuning.

## 13. Scientific boundaries

The formal chain prohibits test-derived tuning, silent fallback, unknown-value
zero filling, writes under `data/`, cross-day interpolation, downstream PRE
reconstruction, historical D6 values as formal evidence, and use of
`y_movement_model` as the formal training or evaluation label.
