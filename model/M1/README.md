# M1 boundary

M1 consumes typed PRE support and supported historical tensors. The formal implementation is the
single one-layer unidirectional GRU with ordered IB, OB, and TX categorical heads. Training uses the
fixed chronological episode-safe split; calibration is per head on the calibration split; formal
sampling is ancestral and preserves episode-scenario lineage. Unsupported targets remain ABSTAIN.

Use `M1Service` at the module boundary. Its FAST and STATE_AWARE paths return the same typed
`M1Forecast` contract, with explicit model path, cutoff, horizons, thresholds, support, and
fallback status. Formal hidden-size selection is intentionally unresolved; validation-only smoke
uses an explicit candidate and is not a paper result.
