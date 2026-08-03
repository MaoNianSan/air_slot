# Air Slot

## 1. Project purpose

Air Slot studies airline disruption recovery under delayed information. It
builds a distributional residual-risk model, maps that uncertainty into the
M1-M4 recovery chain, and evaluates both the overall global policy advantage
and the contribution of selected submodules.

The repository is a scientific execution tree, not a package or a service.
Fast is the reproducible engineering baseline. Multi-day scientific evaluation
uses the `middle` / `full` profiles after the Fast gates pass.

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

## 4. Current Development Status

The current implementation includes:

1. M1 predecessor-aware operational state enhancement
2. M3 expanded recovery action library
3. M4 Ranking@1/@2/@3/@5 output contract

The implementation has passed targeted code verification: fault injection is
15/15 PASS and the full test suite is 272/272 PASS (see
`reports/REVERIFICATION_AFTER_FIXES.md`).

On 2026-08-03 the D6 distributional-metric thresholds were frozen in
`overall_run/config/acceptance.yaml` (twcrps, upper_quantile_calibration,
q95_pinball, q99_pinball, upper_shortfall) and `pipeline_finalize.py` now
computes those five metrics. Fast re-ran with `scientific_status=PASS`.
Middle engineering/chain PASS remains, but its scientific gate is still
`STOP_AND_REVIEW` solely because of `PASSENGER_PROXY_SUPPORT_FAIL` (passenger
evidence covers 0.83 of the 72-day window; the gate requires 1.0) — a
data-coverage decision, not a code defect.

## 5. Recent Model Changes

### M1: Previous-leg operational information

M1 now incorporates preceding aircraft-operation information when available.

Only information available before the decision snapshot is used.
The successor operation is never used as an input feature.

### M3: Expanded recovery action library

The recovery library has been expanded from the previous version to include
additional operational actions:

- aircraft reassignment
- crew recovery
- cancellation/network reset
- integrated recovery strategies

All actions remain subject to typed feasibility gates.

### M4: Ranking extension

M4 produces a unified ranking and derives:

Ranking@1
Ranking@2
Ranking@3
Ranking@5

from the same complete ordering.

## 6. Data contract

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

## 7. Installation

Use Python 3.11 (system install, no virtual environment):

```powershell
# System Python 3.11 path:
D:/Python311/python.exe --version   # Python 3.11.6

# Install dependencies once:
D:/Python311/python.exe -m pip install -r requirements.txt
```

There are no module-level requirements files. Virtual environments (`.venv`,
`venv/`) are not used — the system interpreter at `D:/Python311/python.exe`
is the authoritative Python for all commands in this repository.

All commands below use the explicit path `D:/Python311/python.exe`. Replace with
`python` only if your shell resolves to the same 3.11.6 installation.

## 8. Run profiles

The current run modes are fixed as:

```
fast
middle
full
```

### fast

- Engineering validation
- Code correctness
- Regression testing

Fast is **not** the final paper result. It validates the full M1–M4 chain on a
fixed 5 anchor-day subset (`fast` compute).

### middle

- Intermediate-scale validation
- 72-day data window

Middle uses the frozen `FORMAL_72_V1_20260724` calendar. It selects six dates
per month: the first four Mondays plus the Saturdays following the first and
third Mondays. The profile contains 72 anchor dates: 40 model, 20 audit, and 12
final-test dates. November–December are final-test only (not train-eligible).

Middle design readiness is **separate** from local raw-data readiness. A
missing local required-hour inventory makes middle `NOT_READY` for execution,
but does not invalidate the formal middle design. Middle never falls back to
`fast` or `full`.

### full

- Large-scale evaluation
- Continuous multi-month data

Full runs continuous complete calendar months; gated by `full_data_readiness()`.

Special-purpose: `diagnostic` (debug), `precision` (convergence).
Legacy profiles are retained only for backward compatibility:
`acceptance_23d` / `adapt_full` (alias). `adapt_full` is NOT a formal profile
size and is not a current run mode.

See `docs/RUN_PROFILES.md` for the complete profile contract.

## 9. Fast workflow

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
```

`--n-jobs 1` is the authoritative exact-reproduction path.

## 10. Clean and resume

Clean is always an explicit, independent command:

```powershell
python pre/clean.py --mode fast --dry-run
python pre/clean.py --mode fast
python overall_run/clean.py --mode fast
python overall_adv/clean.py --mode fast
python part_adv/clean.py --mode fast
```

Registered development outputs can be cleaned in isolation with `--output-id`:

```powershell
python pre/clean.py --output-id fast_three_change_dev --dry-run
python pre/clean.py --output-id fast_three_change_dev
```

`main.py` never calls `clean.py`. A cleaner removes only its own
`output/<mode>/` or `output/<output-id>/`; it preserves `data/` and `pre/cache/`.
It refuses an active owned run by default. `--stop-owned-processes` is available
only when module, mode, run ID, PID, and ownership metadata all match.

`overall_run` resumes only from an explicit isolated staging path:

```powershell
python overall_run/main.py fast --resume PATH --progress normal --n-jobs 1
```

`overall_adv` and `part_adv` use `--resume` for a hash-valid incomplete mode
output. Input, scientific configuration, task partition, target contract, and
task output hashes must match; changing only `n_jobs` does not change task
identity.

## 11. Parallel execution

`--n-jobs 1` is the default. Use `--n-jobs 2` or `--n-jobs 4` for a bounded
cloud run after the single-thread smoke passes. `--n-jobs -1` resolves to all
but one logical CPU, but it should not be the first setting for a long run.

The runtime enforces one total CPU budget, prevents nested model parallelism,
derives seeds from stable task IDs rather than worker IDs, merges in fixed task
order, and keeps registry publication in the parent process. The implementation
is compatible with Windows spawn and Linux execution.

## 12. Output structure

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

Development and audit outputs (`fast_three_change_dev`, `fast_code_audit_n1`,
archives) are temporary and are removed during cleanup; only the formal `fast`
baseline and `middle` output are retained. Staging or partial artifacts are
never accepted as published output.

## 13. Command semantics (mandatory)

- **`report` is NOT a computation pipeline.** It reads frozen, published
  artifacts and generates tables, figures, and audits. It never re-trains
  models or re-runs M1–M4.
- **`validate` is NOT re-training.** It checks existing output against
  contracts (registry hashes, lineage, schema). It does not modify data,
  models, or scientific parameters.

Publication flow note: `report` publishes a `STOP_AND_REVIEW` run and sets
`publication_status=PASS`; `validate` then accepts it. A run that already has
`scientific_status=PASS` (e.g. Fast after the 2026-08-03 D6 freeze) currently
has no `report` path, so `validate` returns `OVERALL_RUN_PUBLICATION_NOT_PASS`
until a PASS-run publication path is added.
- **`clean` does NOT delete frozen baselines by default.** It only removes
  runtime output for the specified mode, after confirming no active owned
  process is running. `--dry-run` reports without deleting.

## 14. Engineering vs. Scientific status

Engineering and scientific status are **independent**:

- `engineering_status=PASS` — all formal validators pass; the computation
  ran correctly and deterministically.
- `scientific_status=PASS` — all required scientific acceptance gates pass
  (coverage, crossing, passenger support, and the five D6 distributional
  metrics, whose thresholds were frozen on 2026-08-03).
- `scientific_status=STOP_AND_REVIEW` — at least one required acceptance gate
  failed and needs human review; a remaining example is
  `PASSENGER_PROXY_SUPPORT_FAIL` on the 72-day middle window.

Fast engineering PASS does not imply scientific validity. Scientific
acceptance follows a separate review gate.

## 15. P1 integration status

P1 (event reconstruction) is **not yet formally integrated**. Its code
resides in `analysis/p1_event_reconstruction/` and `tests/p1_event_reconstruction/`.
P1 integration will begin only after R1 scientific review is complete and
the formal `FORMAL_P1_INTEGRATION_ALLOWED=YES` gate is authorised.

## 16. Current frozen status

- Round: R1.5 (profile specification freeze)
- Formal target: `y_movement_raw`
- Profiles frozen: `fast` (engineering gate), `middle` (72-day), `full` (continuous months)
- Thread plan frozen: `PRE_N_JOBS=1`, `DOWNSTREAM_N_JOBS=2`
- Code frozen: `true` (defect fixes verified: fault injection 15/15, tests 272/272)
- D6 distributional thresholds frozen: `2026-08-03`
  (twcrps / q95_pinball / q99_pinball / upper_shortfall upper bounds from the
  fast HIST baseline; upper_quantile_calibration ≤ 0.03)
- Fast scientific gate: `PASS` (2026-08-03 re-run)
- Middle scientific gate: `STOP_AND_REVIEW` (`PASSENGER_PROXY_SUPPORT_FAIL`)
- Fast q95 empirical exceedance: `0.0609375`
- q95 classification: `SYSTEMATIC_CALIBRATION_CONCERN`
- Certification: `METRIC_SUPPORT_LIMITED`
- P1 integrated: `false`
- Formal 72-day Full allowed: `false`
- CLI normalization: `overall_run` uses positional mode; `overall_adv`/`part_adv` use `--mode` flag (documented inconsistency, non-breaking)
- Legacy profiles: `adapt_full` / `acceptance_23d` (retained only for backward compatibility; NOT current run modes)

See `docs/` for complete profile, thread, validation, registry, clean, and migration specifications.

The q95 result is a cloud multi-day scientific evaluation target. It is not an
authorization for further local tuning.

## 17. Scientific boundaries

The formal chain prohibits test-derived tuning, silent fallback, unknown-value
zero filling, writes under `data/`, cross-day interpolation, downstream PRE
reconstruction, historical D6 values as formal evidence, and use of
`y_movement_model` as the formal training or evaluation label.
