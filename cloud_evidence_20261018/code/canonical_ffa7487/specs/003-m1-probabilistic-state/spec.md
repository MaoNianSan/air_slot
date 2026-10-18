# Feature Specification: M1 Probabilistic Operational State

## User Scenarios & Testing

### User Story 1 - Build admissible training sequences (P1)
A researcher converts PRE histories, masks, ages, evidence and stage into episode-grouped samples without dataset-specific features or split leakage.

### User Story 2 - Train and calibrate ordered event-chain model (P1)
A researcher trains one lightweight one-layer unidirectional GRU with conditional IB -> OB -> TX categorical heads, interval likelihood, episode weights, inactive-target masking, and per-head calibration.

### User Story 3 - Publish aligned scenarios (P1)
Downstream modules receive stable episode/scenario identities, observed-stage contraction, overflow flags, event-time identities, support and probability summaries.

### User Story 4 - Save, load, infer, evaluate (P2)
Weights, bin contracts, feature schema and temperatures are frozen together and can be loaded for deterministic CPU/GPU-equivalent inference.

## Requirements

- M1 MUST consume PRE outputs only and MUST not filter evidence or inspect raw datasets.
- Inputs MUST encode value, missing/stale/fallback mask, age, evidence/support and operational stage; numerical zero placeholders MUST remain masked.
- The model MUST be a one-layer unidirectional GRU, principal hidden size 8, without attention.
- Heads MUST factorize `p(IB|h)p(OB|IB,h)p(TX|IB,OB,h)`; takeoff MUST equal off-block plus taxi and MUST not have a separate head.
- Bins MUST be 5 minutes plus overflow; finite maxima MUST be explicit configuration.
- Exact and interval labels MUST use exact-bin and bin-marginal likelihood respectively; unsupported/inactive targets MUST not contribute labels.
- Rolling nodes MUST receive inverse episode-count weights and remain within one data split.
- Per-head temperature calibration MUST use calibration data only and freeze with model artifacts.
- Scenario random keys MUST use global seed, episode, scenario and target, excluding decision time.
- Observed events MUST not be resampled after stage transition.
- Save/load/inference/evaluation interfaces and deterministic smoke tests MUST exist.

## Success Criteria

- Ordered-head shapes, likelihood, stage contraction, scenario identity, save/load and calibration tests pass.
- A synthetic training smoke decreases finite loss and reloads identical logits.
- Unsupported targets produce no fabricated loss or scenarios.
