# 003 M1 Validation Summary

Engineering status: PASS for first-implementation scope; scientific predictive performance is not asserted.

- M1-specific tests: 4 passed.
- Full suite after M1: 52 passed.
- Smoke training loss decreased from 5.4880 to 3.9493.
- Saved artifact reloaded and produced identical probability tensors.
- Architecture is one-layer unidirectional GRU with ordered R_IB -> R_OB -> T_TX heads.
- Interval marginal likelihood, inactive target masking, stable episode/scenario streams, observed-stage contraction, overflow flags, evaluation metrics and CLI are implemented.

Local VS validation remaining: train/calibration/chronological split on real PRE sequences; choose development-frozen finite maxima; run calibration diagnostics and predictive evaluation independently per dataset profile.
