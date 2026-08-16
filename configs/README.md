# Configuration Boundary

`configs/scientific/` is the formal scientific specification: horizons, thresholds, supports,
ontology-facing parameters, and freeze states. `configs/evaluation/` contains experiment-only
contrasts and may not silently redefine scientific defaults. `configs/engineering/` controls local
runtime concerns such as device, workers, and raw-root resolution. `configs/reproducibility/`
contains seed and fixture/runtime reproducibility settings.

Unresolved scientific values stay unset. In particular, M1 hidden-size candidates are `[16, 32]`
and no winner is frozen. Evaluation config loading rejects scientific-default keys.
