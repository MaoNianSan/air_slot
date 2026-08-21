# AIR_SLOT_M1_V2_FEATURE_GATE_B1

- Status: `FEATURE_GATE_B1_DATA_INCONSISTENCY`
- A2 cache: `sha256:7cb35178323aecdd288010b0b70daf15112695baf627b53d2bef03136393b082`
- A2 turnaround: 57.0 min, `sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57`
- A2 taxi: 15.0 min, `sha256:be1a68b0c51c77da35f0ec631c2f846a79dd073d8b29ca49ee42b2d1de4e5c66`
- Dynamic / static / total: 103 / 2 / 105
- Exp1B history separation: `HISTORY_DUPLICATED_IN_RFAST`
- Target support review required: `YES`

## Feature Inventory

- CURRENT_STATE: 3
- CURRENT_SCHEDULE: 1
- CURRENT_WEATHER: 8
- LOCAL_DELTA: 7
- AR_SUMMARY: 6
- RAW_MISSING_MASK: 11
- STALE_MASK: 11
- FALLBACK_MASK: 11
- DERIVED_MISSING_MASK: 13
- CEILING_STATUS: 1
- OBSERVATION_AGE: 1
- EVIDENCE_ENCODING: 21
- SUPPORT_ENCODING: 9
- STATIC_REFERENCE: 2

## Encoder Semantics

- Delta: `PREVIOUS_NODE_LOCAL`, `DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES`.
- AR actual semantics: `FULL_PREFIX_CUMULATIVE_MEAN`; any earlier missing value invalidates the current summary.
- Exp1B: ADAPTIVE history enters through both `GRU(history)` and full-prefix summaries in `r_fast`.
- Structural-zero state masks: 9; recommendation `REMOVE`.
- Static references currently enter as raw minutes; recommendation `TRAIN_STANDARDIZED` pending B1-D06.

## Blockers

- `MISSING_NUMERIC_NOT_ZERO`: 3087
- `STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK`: 4
- `weather.wind_direction_deg.cos` with `weather.wind_direction_deg.missing_mask`: 3087 violations; split counts {'train': 1221, 'calibration': 771, 'development': 1095}.

## Train-Only Review

- Constant features: 54.
- Recommendation counts: `{'COLLAPSE_OBJECT_LEVEL_PENDING_B1_D02': 14, 'KEEP_CANDIDATE': 39, 'KEEP_TRAIN_STANDARDIZE_PENDING_B1_D06': 2, 'METADATA_ONLY_PENDING_B1_D03': 21, 'REDUCE_PENDING_B1_D04': 9, 'REMOVE': 14, 'REMOVE_PENDING_B1_D05': 6}`.
- Exact duplicate groups: 7.
- Deterministic complements: 4.
- Near-linear pairs: 1; report only.
- Weather stale/fallback masks are row-wise identical across all seven weather fields in Train.

## Shift Diagnostics

- Calibration KEEP-candidate rows: 50.
- Development KEEP-candidate rows: 50.
- These diagnostics do not alter any Train-based recommendation.

## Target Support

- train: D_OB: active=1793, zero=1124, positive=669, overflow=34, abstain=0; D_TX: active=1880, zero=1216, positive=664, overflow=0, abstain=0; T_IB_REMAINING_HAZARD: active=342, zero=0, positive=342, overflow=2, abstain=0
- calibration: D_OB: active=1006, zero=545, positive=461, overflow=26, abstain=0; D_TX: active=1060, zero=660, positive=400, overflow=0, abstain=0; T_IB_REMAINING_HAZARD: active=203, zero=0, positive=203, overflow=0, abstain=0
- development: D_OB: active=1671, zero=1032, positive=639, overflow=0, abstain=0; D_TX: active=1765, zero=870, positive=895, overflow=28, abstain=4; T_IB_REMAINING_HAZARD: active=217, zero=0, positive=217, overflow=0, abstain=0

## Human Decisions

### B1-D01

Question: Should structural-zero state missing/stale/fallback masks remain numeric features?

Options: KEEP / REMOVE

Recommendation: `REMOVE`

### B1-D02

Question: Should weather stale/fallback masks be repeated per field or collapsed per object?

Options: REPEAT / COLLAPSE_OBJECT_LEVEL

Recommendation: `COLLAPSE_OBJECT_LEVEL`

### B1-D03

Question: Should constant evidence-class one-hots remain numeric predictors?

Options: NUMERIC / METADATA_ONLY

Recommendation: `METADATA_ONLY`

### B1-D04

Question: How should object support-state one-hots enter the feature schema?

Options: KEEP / REDUCE / METADATA_ONLY

Recommendation: `REDUCE`

### B1-D05

Question: How should full-prefix cumulative weather summaries be handled?

Options: REMOVE / SHORT_WINDOW / RETAIN_RENAME

Recommendation: `REMOVE`

### B1-D06

Question: How should turnaround and taxi reference minutes be numerically encoded?

Options: RAW / TRAIN_STANDARDIZED

Recommendation: `TRAIN_STANDARDIZED`

### B1-D07

Question: What static missingness contract should replace unmasked whole-block zero fill?

Options: REQUIRE_COMPLETE_BLOCK / PER_FEATURE_MASKED_BLOCK / ABSTAIN_SAMPLE

Recommendation: `PER_FEATURE_MASKED_BLOCK`

## Safety State

```text
M1_TRAINING_RUNS = 0
TUNING_RUNS = 0
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = false
GATE_B_ENTERED = true
GATE_B2_FEATURE_FREEZE = false
```
