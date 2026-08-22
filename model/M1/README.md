# M1 boundary

M1 consumes typed PRE support and supported historical tensors. The formal implementation is the
single one-layer unidirectional GRU with ordered IB, OB, and TX categorical heads. Training uses the
fixed chronological episode-safe split; calibration is per head on the calibration split; formal
sampling is ancestral and preserves episode-scenario lineage. Unsupported targets remain ABSTAIN.

Use `M1Service` at the module boundary. Its FAST and STATE_AWARE paths return the same typed
`M1Forecast` contract, with explicit model path, cutoff, horizons, thresholds, support, and
fallback status. Formal hidden-size selection is intentionally unresolved; validation-only smoke
uses an explicit candidate and is not a paper result.

## Stage 1 tuning preparation

`M1_V2_TUNING_STAGE1_MANIFEST.json` defines the no-run H sensitivity contract
for `H={8,16,32}` and the `NO_HISTORY_CURRENT_OBSERVATION` baseline. The
principal Development metric is `EPISODE_BALANCED_JOINT_VALIDATION_LOSS`,
with the five existing episode-balanced primitive diagnostics retained as
secondary outputs. `fast_train_mode` is an explicitly authorized deterministic
Development-subset entry point; it rejects Final Test examples and is never a
paper/full run.
