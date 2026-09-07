# Air Slot Final Test Cohort Authority

Date: 2026-09-07.

Status: `FINAL_TEST_COHORT_AUTHORITY_LOCKED`.

This document freezes the Final Test cohort selection authority before the
held-out split is opened. It does not read Q4 data, materialize a Test cohort,
run model inference, or produce experiment results.

## Lineage

- Parent lock: `formal/FINAL_TEST_LOCK_20260907.md`
- Parent lock commit:
  `99114195f11d7cb3446e53729daab611c88f4d36`
- Development scientific code lock:
  `c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6`
- Scientific source diff: `none`
- Machine-readable authority:
  `formal/FINAL_TEST_COHORT_AUTHORITY_V1.json`
- Machine-readable authority SHA-256:
  `9832b198e221042bff6f40c718f07c82169885514030308b7d50d6172d7e0088`

## Frozen Selection

- `FINAL_TEST_EPISODE_COUNT = 128`
- `SELECTION_RULE =
  SEEDED_RESERVOIR_OVER_SPLIT_CONTAINED_EPISODES_FROZEN_SOURCE`
- `SELECTION_SEED = 20260813`
- `FINAL_TEST_RNG_SCOPE = FINAL_TEST_ONLY_FRESH_SEED`
- RNG initialization: `random.Random(20260813)`
- Selection is pre-outcome and uses no target, prediction, consequence,
  support, stage-balance, or experiment result fields.
- Selected episodes are retained in lineage even when later analytical
  targets are unsupported. No later episode replacement is permitted.

## Frozen Source And Containment

- Source months: `2019-10`, `2019-11`, `2019-12`
- Service-date window: `2019-10-01` through `2019-12-31`
- Split authority: `DATA2_TEMPORAL_SPLIT@1.0.0`
- Assignment authority: successor canonical service date
- Candidate construction: existing canonical BTS parsing, aircraft-chain
  construction, `build_data2_episode_records`, and frozen episode contract.
- Processing order: October, November, December, with existing cross-month
  aircraft carry semantics and deterministic episode ordering.
- Eligibility requires predecessor, successor, episode interval, and all
  relevant decision-time support to belong to Test under the existing
  containment authority.
- Cross-split episodes, including September-to-October episodes, are excluded.

## Prohibitions

Old H32 episode IDs, sampler state, and result artifacts are not authorities.
The budget cannot be reduced because the eligible pool or later support
coverage is small. Raw date filtering cannot replace the repository split or
containment authorities.

## Pre-Opening State

- `FINAL_TEST_ACCESS_COUNT = 0`
- `test_data_read = false`
- `test_cohort_materialized = false`
- `test_inference_run = false`
- `model_retrained = false`
- `calibration_refit = false`
- `parameter_reselected = false`
- `paper_result = false`
