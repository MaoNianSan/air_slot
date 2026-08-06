# M1 Train/Inference Parity Audit

Audit date: 2026-08-02

M1_TRAIN_INFERENCE_PARITY=FAIL

## Evidence

- Training features are selected from the frozen allowlist in `overall_run/src/m1_training.py:8-55` and stored in `M1Artifact.feature_columns`.
- Inference selects `df[self.feature_columns]` before applying the fitted transformer at `overall_run/src/m1.py:61-68`.
- The actual development artifact records `feature_schema_hash`, `feature_columns`, and `M1_PREVIOUS_LEG_V1`; predecessor features are present in both training and inference tests.

## Missing guard

The requested active mutation of feature order was not rejected by the fitted transformer, and there is no separate inference-time assertion that the stored feature-order hash equals the expected contract hash. Named-column selection makes ordinary input column order harmless, but a corrupted artifact/order contract is not explicitly detected. Under the workflow's strict fault-injection rule, parity is therefore FAIL rather than inferred PASS.
