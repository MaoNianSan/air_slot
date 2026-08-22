# Configuration Boundary

`configs/scientific/` is the formal scientific specification: horizons, thresholds, supports,
ontology-facing parameters, and freeze states. `configs/evaluation/` contains experiment-only
contrasts and may not silently redefine scientific defaults. `configs/engineering/` controls local
runtime concerns such as device, workers, and raw-root resolution. `configs/reproducibility/`
contains seed and fixture/runtime reproducibility settings.

Unresolved scientific values stay unset. M1 retains hidden-size candidates `[8, 16, 32]`, while the
approved signed-target Development freeze selects `H=32` and `W=30`. Evaluation config loading
rejects scientific-default keys.
