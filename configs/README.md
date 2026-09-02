# Configuration Boundary

`configs/scientific/` is the formal scientific specification: horizons, thresholds, supports,
ontology-facing parameters, and freeze states. `configs/evaluation/` contains experiment-only
contrasts and may not silently redefine scientific defaults. `configs/engineering/` controls local
runtime concerns such as device, workers, and raw-root resolution. `configs/reproducibility/`
contains seed and fixture/runtime reproducibility settings.

Unresolved scientific values stay unset. The active M1 runtime is the frozen
single-layer causal GRU with `H=8`; `H=16` is a predefined sensitivity setting,
not a tuning candidate. The active finite supports are `360/180/60` minutes and
the scenario budget is 64 per episode. Evaluation config loading rejects
scientific-default keys.
