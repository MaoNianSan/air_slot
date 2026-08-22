# AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0A

- Status: `TARGET_SUPPORT_C0A_WEIGHTING_REVIEW_REQUIRED`
- Repository HEAD: `0c0a8227dfb1dfbda9853bbaa6ee22899b954da7`
- Scope: audit-only; Train/Calibration/Development and Jan-Sep source paths only.

## DST / Source Clock

- All departure mismatches: `29`.
- Classification counts: `{'DST_CLOCK_BASIS_EXPLAINED': 27, 'DIRECT_CLOCK_SIGNED_DELAY_CONFLICT': 1, 'DATE_OFFSET_AMBIGUOUS': 1}`.
- Canonical timestamp changes (all/B2): `0` / `0`.
- 265-minute case: `{"CRSDepTime": "0800", "Carrier": "EV", "DepDelay": -9.0, "DepDelayMinutes": 0.0, "DepTime": "1216", "Dest": "EWR", "FlightDate": "2019-03-27", "Flight_Number": "4304", "Origin": "JAX", "Tail_Number": "N14542", "actual_direct_local_datetime": "2019-03-27T12:16:00-04:00", "actual_direct_utc": "2019-03-27 16:16:00+00:00", "actual_utc_offset_minutes": -240.0, "canonical_timestamp_changed": false, "classification": "DIRECT_CLOCK_SIGNED_DELAY_CONFLICT", "current_canonical_timestamp": "2019-03-27 16:16:00+00:00", "date_offset_resolved": false, "direct_utc_elapsed_minutes": 256.0, "dst_aware_candidate_timestamp": "2019-03-27 11:51:00+00:00", "expected_actual_local_wall_datetime": "2019-03-27T07:51:00", "expected_utc_elapsed_from_local_delay": -9.0, "flight_id": "flight:07fd9753f1c56843f97b7902ee64eff5e8e575830feb5f227133f62730008179", "forensic_interpretation": "RAW_BTS_DIRECT_CLOCK_SIGNED_DELAY_CONTRADICTION", "local_wall_clock_candidate_count": 1, "local_wall_clock_residual_minutes": 265.0, "offset_change_minutes": 0.0, "old_difference_minutes": 265.0, "residual_minutes": 265.0, "schedule_local_datetime": "2019-03-27T08:00:00-04:00", "schedule_utc": "2019-03-27 12:00:00+00:00", "schedule_utc_offset_minutes": -240.0, "signed_dep_delay": -9.0, "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 271497, "split": "train", "timezone": "America/New_York"}`.
- Cohort intersection: `{"conflict_flights_in_a2_cohort": 0, "in_a2_episode_cohort": 0, "in_b2_frozen_samples": 0, "in_c0_calibration_overflow": 0, "in_c0_development_overflow": 0, "in_c0_train_d_ob_overflow": 0, "in_c0_train_overflow": 0, "total_inconsistent_flights": 29}`.

## Episode-Balanced Support

- `T_IB_REMAINING_HAZARD`: rows=342, unique episodes=40, episode profile={"active_count": 40, "current_support_count": 1, "current_support_fraction": 0.025, "max": 365.0, "mean": 65.9, "min": 2.0, "p50": 20.5, "p75": 99.25, "p90": 176.9, "p95": 200.49999999999974, "p97.5": 287.9749999999999, "p99": 334.18999999999994, "positive_count": 40, "std": 83.80268492118853, "zero_count": 0}
- `D_OB`: rows=1793, unique episodes=128, episode profile={"active_count": 128, "current_support_count": 3, "current_support_fraction": 0.0234375, "max": 343.0, "mean": 16.5234375, "min": 0.0, "p50": 0.0, "p75": 8.5, "p90": 55.89999999999999, "p95": 88.29999999999998, "p97.5": 118.825, "p99": 196.30000000000004, "positive_count": 50, "std": 44.191515878996434, "zero_count": 78}
- `D_TX`: rows=1880, unique episodes=128, episode profile={"active_count": 128, "current_support_count": 0, "current_support_fraction": 0.0, "max": 40.0, "mean": 2.7109375, "min": 0.0, "p50": 0.0, "p75": 3.0, "p90": 8.299999999999997, "p95": 13.299999999999983, "p97.5": 19.125000000000014, "p99": 25.190000000000012, "positive_count": 47, "std": 5.731154366364053, "zero_count": 81}

## Overflow Episodes

| Split | Target | Value | Row repetitions | Source verification |
|---|---|---:|---:|---|
| train | T_IB_REMAINING_HAZARD | 365.0 | 10 | SOURCE_CONSISTENT |
| train | D_OB | 189.0 | 12 | SOURCE_CONSISTENT |
| train | D_OB | 199.0 | 12 | SOURCE_CONSISTENT |
| train | D_OB | 343.0 | 10 | SOURCE_CONSISTENT |
| calibration | D_OB | 202.0 | 19 | SOURCE_CONSISTENT |
| calibration | D_OB | 269.0 | 7 | SOURCE_CONSISTENT |
| development | D_TX | 98.0 | 12 | SOURCE_CONSISTENT |
| development | D_TX | 78.0 | 9 | SOURCE_CONSISTENT |
| development | D_TX | 60.0 | 7 | SOURCE_CONSISTENT |

## Training Weighting

- `M1_EPISODE_WEIGHTING_CONTRACT_REVIEW_REQUIRED`
- M1Lifecycle._global_loss_counts counts active rows and _loss normalizes by row counts; model/M1/data.py defines episode_normalized_weights but lifecycle does not consume it.

## Human Review Recommendations

### C0A-D01
- `KEEP_360`
- Train episode-max tail=1; row tail=2; episode-max max=365.0 and support remains a survival/overflow state.

### C0A-D02
- `EXPAND_TO_210`
- Train unique D_OB tail episodes=3 with values=[189.0, 199.0, 343.0]; at 210 min episode tail=1 and row tail=10.

### C0A-D03
- `KEEP_60`
- Train unique D_TX tail episodes=0; D_TX parent-conditioning role is NONE; Development-only tails remain generalization diagnostics.

## B2 Immutability / Safety

- B2 schema: `sha256:1f4b886a9bddc67f3fe72b977ea957cf5828b6cdd20dcc69655dcf3f2ec2972a`
- B2 cache: `sha256:157c0d555c40efd9d7dc5ecebc5dda60a902b855d42bdab9a3657aa601e6f919`
- Labels unchanged: `True`
- Active masks unchanged: `True`

```text
M1_TRAINING_RUNS = 0
TUNING_RUNS = 0
FINAL_TEST_ACCESS_COUNT = 0
M1_TARGET_SUPPORT_FROZEN = false
```

No support/config update, training, tuning, C0B, C1, Final Test, FULL, or paper_full was run.
