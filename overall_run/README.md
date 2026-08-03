# overall_run

## 1. Role

`overall_run` is the authoritative model and decision chain:

```text
PRE five tables -> M1 -> M2 -> M3 -> M4
```

`overall_adv` and `part_adv` are separate downstream experiments, not internal
stages of this runner.

## 2. Inputs

The module reads only `../pre/output/<mode>/`. It does not read `data/raw/`, PRE
staging data, old Fast output, or historical D6 artifacts. The formal label is
`y_movement_raw`; `y_movement_model` is sensitivity-only. There is no alternate
label fallback.

## 3. M1

M1 is a calibrated LightGBM quantile ensemble. The frozen grid is:

```text
0.01, 0.025, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50,
0.60, 0.70, 0.80, 0.90, 0.95, 0.975, 0.99
```

Calibration is fit on validation data only and uses
`airport_stage -> stage -> global`. Raw crossings are audit evidence;
monotonic-projected crossings are the formal gate. Scenario samples from the
projected distribution feed M2-M4.

The current Fast selection is `LGB_Q_01`: `num_leaves=15`, `max_depth=8`,
`min_child_samples=100`, `learning_rate=0.05`, `feature_fraction=0.7`,
`bagging_fraction=0.8`, and `reg_lambda=1.0`. The frozen model parameter hash is
`b2d32346703a71bd3cdec03f03ef10ebf7caf5608965b3db78a8bf71bd5ba76c`.

## 4. M2

M2 first constructs channel-specific raw operational quantities, then converts
those quantities to development-frozen common internal units and finally to RMB
costs. The current reporting conversion is `1 internal unit = 1 RMB`, but the
quantity, unit-price, and RMB fields remain separate. `graph_edges` contains the
frozen F→P, F→R, and P→R exposure couplings; every edge uses the unchanged base
exposure, so YAML order cannot create an implicit cycle. `R_to_F` is prohibited.
Passenger evidence missingness remains unsupported rather than zero.

## 5. M3

M3 generates one frozen stochastic response library for each formal run. It is
independent of the episode, snapshot, M1 draw level, M2 cost level, and M4 rule
state. Recovery rates use bounded Beta draws with an implementation-success
indicator; implementation costs use a shared action-level lognormal shock.
These are declared scenario responses, not identified causal action effects.
The null action is exactly zero.

## 6. M4

M4 first applies capacity, execution-window, resource, authority, and lead-time
conditions, then applies the recovery-ratio, burden-ratio, and positive-net-
benefit gates. A00 is always retained. The formal score is computed from the
total post-action RMB distribution:

```text
(1 - lambda) * mean(total post-action cost)
+ lambda * CVaR_alpha(total post-action cost)
```

The primary values are `lambda=0.25` and `alpha=0.90`. No channel median
normalization or equal channel weight is applied inside M4. EV, Mean-CVaR, and
CVaR comparisons belong to `part_adv`.

## 7. Configuration

`config/scientific.yaml` is the scientific source of truth. Mode overlays,
compute limits, and acceptance gates are also under `config/`. Runtime resource
choices such as `--n-jobs`, `--progress`, and `--resume PATH` are not scientific
parameters and do not belong in `scientific.yaml`.

## 8. CLI

```powershell
# Fast (engineering gate)
python -u overall_run/main.py fast --progress normal --n-jobs 2
python overall_run/main.py validate --mode fast
python overall_run/main.py report --mode fast --n-jobs 2

# Diagnostic
python -u overall_run/main.py diagnostic --progress normal --n-jobs 1

# Legacy adapt-full / acceptance (backward compatibility only)
python -u overall_run/main.py adapt_full --progress normal --n-jobs 2
python overall_run/main.py validate --mode adapt_full

# Full (gated)
python -u overall_run/main.py full --progress normal --n-jobs 2

# Precision (requires accepted formal Full or legacy adapt_full)
python -u overall_run/main.py precision --progress normal --n-jobs 2
```

Fast is allowed. `diagnostic` and legacy `adapt_full` are true configuration
modes; they are not aliases for Full. `adapt_full` and formal Full require
accepted Fast gates unless explicitly overridden. Precision requires an
accepted `adapt_full` or formal Full parent.

`validate` and `report` require `--mode` flag (preferred). The legacy positional
form (`validate fast`) is still accepted for backward compatibility but
deprecated.

## 9. Parallelism

Independent M1 quantile tasks are parallelized under one outer CPU budget.
M3 action-response and M4 snapshot/action computations preserve stable task
identity. When outer tasks run concurrently, each model receives one inner
thread. Results are merged in fixed quantile or task-ID order.

## 10. Checkpoint and resume

Stage checkpoints cover M1 fit/evaluation, M2 fit/evaluation, M3 contract and
evaluation, and M4 fit/evaluation. They record input, configuration,
implementation, formal-target, partition, and task hashes.

Resume requires an explicit isolated staging path:

```powershell
python overall_run/main.py fast --resume PATH --progress normal --n-jobs 2
```

Changing `n_jobs` is allowed only when stable task IDs, seeds, and all completed
task hashes still match.

## 11. Outputs

`output/<mode>/` contains the M1 model, evaluation predictions and predictive
samples, M2 raw-quantity/common-unit/RMB summaries, M3 response parameters and
samples, M4 physical and decision-value screening, scores, rankings and
recommendations, parameter manifests, checkpoints, scientific gates, model
contract, summary, state, and artifact registry. Core figures are published as
300-DPI PNG plus PDF and SVG.

## 12. Validation gates

Required engineering gates include formal-target mismatch `0`, future leakage
`0`, test-fit use `0`, stale artifacts `0`, Passenger/M2/M3/M4 PASS, M4
available, and projected crossing `0`. The current Fast q95 calibration concern
is a scientific review result, not an engineering pipeline failure.

## 13. Scientific boundaries

The formal model never trains on `y_movement_model`, never tunes offsets from
Fast test outcomes, never adds a tail model in response to the current Fast
result, and never treats historical D6 values as formal evidence. q95 and q99
certification is assigned by the formal multi-day evaluation (`middle` / `full`).
