# Research Decisions: M1

- Conditional heads use teacher forcing during training and probability-weighted target embeddings during inference.
- Interval likelihood marginalizes bins intersecting the supported interval; midpoint labels are prohibited.
- Overflow scenarios publish the configured finite-support lower bound plus an overflow flag, not a clipped exact claim.
- Temperatures are positive scalar parameters optimized on a calibration split and stored with weights.
- Stable inverse-CDF streams are SHA-256 keyed by seed/episode/scenario/target without decision time.
