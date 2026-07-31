# overall_adv

## 1. Role

`overall_adv` tests whether the frozen global policy outperforms the local
policy on one common-support cohort. It is not a new main model, an M1 tuning
experiment, an M2-M4 reimplementation, or a new action library.

## 2. Comparison target

The only formal comparison is `LOCAL_F` versus `GLOBAL_FPR`. `GLOBAL_FPR` is a
stable external policy ID; it does not restore any historical internal F/P/R
policy-channel meaning.

## 3. Inputs

The module loads `../overall_run/output/<mode>/` and verifies its registry,
hashes, cohort, and formal target. It does not rebuild M1-M4, read `data/raw/`,
or choose a label independently. Upstream `y_movement_raw` lineage is required.

## 4. Cohort

Both policies use the same common-support cohort, recovery cases, events, and
stable random task sequence. Cases are never selected after observing policy
results.

## 5. Policies

`LOCAL_F` ranks the registered local policy evidence. `GLOBAL_FPR` loads the
frozen global M4 decision output. The policy definitions and action library are
not modified in this module.

## 6. Metrics and inference

The experiment uses paired recovery-case metrics and cluster/bootstrap
inference, including network-propagation and high-disruption cases. Replicate
results are merged by stable replicate ID, so inference does not depend on
worker completion order.

## 7. CLI

```powershell
python -u overall_adv/main.py fast --progress normal --n-jobs 1
python -u overall_adv/main.py validate --mode fast --progress normal --n-jobs 1
python overall_adv/main.py report --mode fast --n-jobs 1

python -u overall_adv/main.py adapt_full --progress normal --n-jobs 2
python -u overall_adv/main.py adapt_full --progress normal --n-jobs 2 --resume
```

The CLI also recognizes `diagnostic` and `full`; formal Full is not allowed in
the current stage.

## 8. Parallelism

Benchmark rows and bootstrap replicates may run concurrently. Paired tasks use
stable seeds, workers return isolated results, and the parent process performs
ordered merge, checkpoint publication, and the single registry write.

## 9. Outputs

`output/<mode>/` contains policy decisions, paired metrics, event-cluster
bootstrap results, uncertainty summaries, the common-support cohort contract,
checkpoints, logs, run state, summary, and artifact registry. The principal
Local–Global comparison is exported as 300-DPI PNG, PDF, and SVG with paired
regret, tail-regret, harmful-intervention, and selection diagnostics.

## 10. Boundaries

The module does not compare unregistered policies, adjust `overall_run`, retrain
from PRE raw inputs, change the cohort, or use a weak local result to tune the
global model.
