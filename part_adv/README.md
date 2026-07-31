# part_adv

## 1. Role

`part_adv` validates selected submodule choices without redefining the
authoritative M1-M4 chain.

## 2. Inputs

The experiment reads the PRE formal contract and frozen
`../overall_run/output/<mode>/` artifacts. Every M1 model uses the same
evaluation index, split, and formal `y_movement_raw` label.

## 3. M1 comparison

The fixed comparison is `HIST`, `QRF`, `NGB`, `PROP`, and `POINT_OOF`.
`POINT_OOF` is diagnostic-only. All five use the same cohort, label, split, and
evaluation metrics; only the registered model definition changes.

## 4. M2 comparison

M2 retains the registered `DAG_BASE`, `ADD_BASE`, and one-at-a-time experiment
labels for downstream compatibility. These are experiment-side perturbations,
not alternative definitions of the authoritative M2 implementation. Their
scientific interpretation belongs to the rewritable Experiment III protocol and
must not be used to explain Sections 3–4.

## 5. M4 comparison

M4 compares `EV`, `Mean-CVaR`, and `CVaR` risk criteria on the frozen action
library and common-support keys. The comparison changes the risk criterion,
not the available actions.

## 6. Excluded scope

`part_adv` does not compare M3, add an M3 baseline, or claim identification of
true action effects.

## 7. CLI

```powershell
python -u part_adv/main.py fast --progress normal --n-jobs 1
python -u part_adv/main.py validate --mode fast --progress normal --n-jobs 1
python part_adv/main.py report --mode fast --n-jobs 1

python -u part_adv/main.py adapt_full --progress normal --n-jobs 2
python -u part_adv/main.py adapt_full --progress normal --n-jobs 2 --resume
```

The CLI recognizes `diagnostic`, `full`, and `precision`. Formal Full remains
subject to its gate; Precision requires an accepted upstream `adapt_full` or
formal Full artifact set.

## 8. Parallelism

Registered M2 OAT tasks and M4 risk variants may run concurrently. The stable
M1 order is `HIST`, `QRF`, `NGB`, `PROP`, `POINT_OOF`; M2 and M4 also use fixed
task IDs. Final tables are ordered by those IDs, not by future completion time.

## 9. Outputs

`output/<mode>/` contains M1 model metrics and propagation tables, M2 structure
and sensitivity results, M4 variant scores and metrics, checkpoints, logs,
common-support metadata, run state, summary, and artifact registry. Formal
figures separate predictive and downstream decision quality, show M2 cost and
ranking sensitivity, and display the M4 mean–tail trade-off; each is exported
as 300-DPI PNG, PDF, and SVG.

## 10. Validation gates

Required gates include all M1 models using the raw formal target, equal cohort
keys, test-fit use `0`, future leakage `0`, stale artifacts `0`, no M3
comparison, and a passing registry.
