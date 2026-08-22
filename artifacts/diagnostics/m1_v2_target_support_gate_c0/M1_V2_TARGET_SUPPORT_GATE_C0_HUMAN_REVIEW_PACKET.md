# AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0

- Status: `TARGET_SUPPORT_C0_DATA_ANOMALY`
- Repository HEAD: `ba7717c26e6cf7089696b1dd08ac209643598b57`
- Scope: frozen B2 labels/active masks and retained lineage only; no raw BTS target reconstruction.

## B2 Baseline

- Frozen schema: `sha256:1f4b886a9bddc67f3fe72b977ea957cf5828b6cdd20dcc69655dcf3f2ec2972a`
- Frozen cache: `sha256:157c0d555c40efd9d7dc5ecebc5dda60a902b855d42bdab9a3657aa601e6f919`
- Feature schema/hash contract unchanged: `True`

## Current Support

- T_IB_REMAINING_HAZARD: `360 min`
- D_OB: `180 min`
- D_TX: `60 min`
- Bin width: `5 min` (out of scope)

## Provenance

| Target | Legacy source | Transfer status |
|---|---|---|
| T_IB_REMAINING_HAZARD | V1 R_IB support statistics | PARTIALLY_TRANSFERABLE; cohort changed |
| D_OB | V1 signed DELTA_OB support | PARTIALLY_TRANSFERABLE / REESTIMATION_REQUIRED |
| D_TX | V1 raw T_TX support | NOT_SEMANTICALLY_TRANSFERABLE / REESTIMATION_REQUIRED |

## TRAIN_SELECTION_EVIDENCE

- `T_IB_REMAINING_HAZARD`: active=342, zero=0, positive=342, p50=73.5, p90=184.60000000000014, p99=347.9499999999999, max=365.0, current-tail=2 (0.005848).
- `D_OB`: active=1793, zero=1124, positive=669, p50=0.0, p90=55.0, p99=199.0, max=343.0, current-tail=34 (0.018963).
- `D_TX`: active=1880, zero=1216, positive=664, p50=0.0, p90=10.0, p99=26.0, max=40.0, current-tail=0 (0.000000).

## CALIBRATION_DIAGNOSTIC

- Calibration: `{"D_OB": {"active_count": 1006, "current_support_count": 26, "current_support_fraction": 0.02584493041749503, "max": 269.0, "mean": 19.354870775347912, "min": 0.0, "p50": 0.0, "p75": 31.0, "p90": 43.0, "p95": 104.0, "p97.5": 193.25, "p99": 202.0, "p99.5": 269.0, "p99.9": 269.0, "positive_count": 461, "std": 41.70735296545312, "zero_count": 545}, "D_TX": {"active_count": 1060, "current_support_count": 0, "current_support_fraction": 0.0, "max": 24.0, "mean": 2.8726415094339623, "min": 0.0, "p50": 0.0, "p75": 4.0, "p90": 8.0, "p95": 11.0, "p97.5": 19.0, "p99": 20.0, "p99.5": 24.0, "p99.9": 24.0, "positive_count": 400, "std": 4.957156690724045, "zero_count": 660}, "T_IB_REMAINING_HAZARD": {"active_count": 203, "current_support_count": 0, "current_support_fraction": 0.0, "max": 274.0, "mean": 83.13300492610837, "min": 1.0, "p50": 63.0, "p75": 129.0, "p90": 193.8, "p95": 223.4999999999999, "p97.5": 248.74999999999994, "p99": 263.9, "p99.5": 268.95000000000005, "p99.9": 272.99, "positive_count": 203, "std": 70.09266944331362, "zero_count": 0}}`
- Calibration is diagnostic only and was not used to select support.

## DEVELOPMENT_DIAGNOSTIC

- Development: `{"D_OB": {"active_count": 1671, "current_support_count": 0, "current_support_fraction": 0.0, "max": 132.0, "mean": 7.444643925792938, "min": 0.0, "p50": 0.0, "p75": 6.0, "p90": 23.0, "p95": 43.0, "p97.5": 62.0, "p99": 82.0, "p99.5": 132.0, "p99.9": 132.0, "positive_count": 639, "std": 17.655162004349943, "zero_count": 1032}, "D_TX": {"active_count": 1765, "current_support_count": 28, "current_support_fraction": 0.01586402266288952, "max": 98.0, "mean": 4.828895184135978, "min": 0.0, "p50": 1.0, "p75": 6.0, "p90": 11.0, "p95": 17.59999999999991, "p97.5": 28.0, "p99": 78.0, "p99.5": 98.0, "p99.9": 98.0, "positive_count": 895, "std": 11.608981731962382, "zero_count": 870}, "T_IB_REMAINING_HAZARD": {"active_count": 217, "current_support_count": 0, "current_support_fraction": 0.0, "max": 142.0, "mean": 29.078341013824886, "min": 1.0, "p50": 17.0, "p75": 43.0, "p90": 69.0, "p95": 91.99999999999994, "p97.5": 114.99999999999997, "p99": 131.20000000000002, "p99.5": 136.59999999999994, "p99.9": 140.91999999999996, "positive_count": 217, "std": 30.097665004488626, "zero_count": 0}}`
- Development is diagnostic only and was not used to select support.

## Forensic Gate

- Overflow rows: `{'T_IB_REMAINING_HAZARD': {'train': 2, 'calibration': 0, 'development': 0}, 'D_OB': {'train': 34, 'calibration': 26, 'development': 0}, 'D_TX': {'train': 0, 'calibration': 0, 'development': 28}}`.
- A2 global signed departure consistency: `FAIL`.
- A2 departure detail: `{"calibration": {"deterministic_inconsistency_samples": [], "exact_agreement_rate": 1.0, "max_abs_difference_minutes": 0.0, "within_1min_rate": 1.0}, "development": {"deterministic_inconsistency_samples": [], "exact_agreement_rate": 1.0, "max_abs_difference_minutes": 0.0, "within_1min_rate": 1.0}, "train": {"deterministic_inconsistency_samples": [{"CRS_time": "2015", "Dest": "SEA", "FlightDate": "2019-03-09", "Origin": "ORD", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "0616", "direct_date_resolved": "2019-03-10T06:16:00-05:00", "reporting_delay_minutes": 601.0, "signed_delay": 601.0, "signed_target": "2019-03-10T07:16:00-05:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 10942}, {"CRS_time": "1437", "Dest": "PHL", "FlightDate": "2019-03-09", "Origin": "AUS", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "0946", "direct_date_resolved": "2019-03-10T09:46:00-05:00", "reporting_delay_minutes": 1149.0, "signed_delay": 1149.0, "signed_target": "2019-03-10T10:46:00-05:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 33503}, {"CRS_time": "1055", "Dest": "JAC", "FlightDate": "2019-03-09", "Origin": "DFW", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "0803", "direct_date_resolved": "2019-03-10T08:03:00-05:00", "reporting_delay_minutes": 1268.0, "signed_delay": 1268.0, "signed_target": "2019-03-10T09:03:00-05:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 39063}, {"CRS_time": "1338", "Dest": "ORD", "FlightDate": "2019-03-09", "Origin": "JAC", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "1034", "direct_date_resolved": "2019-03-10T10:34:00-06:00", "reporting_delay_minutes": 1256.0, "signed_delay": 1256.0, "signed_target": "2019-03-10T11:34:00-06:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 40786}, {"CRS_time": "2315", "Dest": "JFK", "FlightDate": "2019-03-09", "Origin": "SFO", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "1629", "direct_date_resolved": "2019-03-10T16:29:00-07:00", "reporting_delay_minutes": 1034.0, "signed_delay": 1034.0, "signed_target": "2019-03-10T17:29:00-07:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 50815}, {"CRS_time": "0131", "Dest": "MIA", "FlightDate": "2019-03-10", "Origin": "DEN", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "0358", "direct_date_resolved": "2019-03-10T03:58:00-06:00", "reporting_delay_minutes": 147.0, "signed_delay": 147.0, "signed_target": "2019-03-10T04:58:00-06:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 54210}, {"CRS_time": "2020", "Dest": "IAH", "FlightDate": "2019-03-09", "Origin": "ORD", "Reporting_Airline": "AA", "abs_difference_minutes": 60.0, "direct_actual_clock": "0600", "direct_date_resolved": "2019-03-10T06:00:00-05:00", "reporting_delay_minutes": 580.0, "signed_delay": 580.0, "signed_target": "2019-03-10T07:00:00-05:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 63072}, {"CRS_time": "2232", "Dest": "AVL", "FlightDate": "2019-03-09", "Origin": "ATL", "Reporting_Airline": "DL", "abs_difference_minutes": 60.0, "direct_actual_clock": "0615", "direct_date_resolved": "2019-03-10T06:15:00-04:00", "reporting_delay_minutes": 463.0, "signed_delay": 463.0, "signed_target": "2019-03-10T07:15:00-04:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 173535}, {"CRS_time": "2025", "Dest": "ORD", "FlightDate": "2019-03-09", "Origin": "DTW", "Reporting_Airline": "OO", "abs_difference_minutes": 60.0, "direct_actual_clock": "1307", "direct_date_resolved": "2019-03-10T13:07:00-04:00", "reporting_delay_minutes": 1002.0, "signed_delay": 1002.0, "signed_target": "2019-03-10T14:07:00-04:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 223750}, {"CRS_time": "2040", "Dest": "FSD", "FlightDate": "2019-03-09", "Origin": "ORD", "Reporting_Airline": "OO", "abs_difference_minutes": 60.0, "direct_actual_clock": "1254", "direct_date_resolved": "2019-03-10T12:54:00-05:00", "reporting_delay_minutes": 974.0, "signed_delay": 974.0, "signed_target": "2019-03-10T13:54:00-05:00", "source_path": "data2\\raw\\bts\\ontime\\2019\\month=03\\On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2019_3.csv", "source_row_number": 223920}], "exact_agreement_rate": 0.99999173807769, "max_abs_difference_minutes": 265.0, "within_1min_rate": 0.99999173807769}}`.
- Row-level actual departure, signed DepDelay, TaxiOut, T_IB_A00, and decision time are not retained in the frozen B2 cache.
- Row-level source-consistency status: `TARGET_SUPPORT_C0_DATA_ANOMALY`; see `M1_V2_TARGET_SUPPORT_C0_OVERFLOW.csv`.

## Conditioning And Representation

- D_OB Train tail bands: `{'180--210': 24, '210--240': 0, '240--300': 0, '300--360': 10, '>360': 0}`.
- D_OB finite-vs-overflow D_TX diagnostic: `{"D_OB_finite": {"positive_mean": 8.24671052631579, "positive_median": 6.0, "positive_p90": 14.0, "row_count": 1759, "zero_fraction": 0.6543490619670267}, "D_OB_overflow": {"positive_mean": 1.9090909090909092, "positive_median": 1.0, "positive_p90": 3.0, "row_count": 34, "zero_fraction": 0.35294117647058826}}`.
- D_TX parent-conditioning role: `NONE`.
- Scenario representative diagnostics: `{"D_OB": {"absolute_error_max_minutes": 158.0, "absolute_error_mean_minutes": 52.8235294117647, "overflow_count": 34, "overflow_values": [189.0, 199.0, 343.0], "representative_minutes": 185, "split": "train"}, "D_TX": {"absolute_error_max_minutes": 33.0, "absolute_error_mean_minutes": 19.571428571428573, "overflow_count": 28, "overflow_values": [60.0, 78.0, 98.0], "representative_minutes": 65, "split": "development"}, "T_IB_REMAINING_HAZARD": {"absolute_error_max_minutes": 5.0, "absolute_error_mean_minutes": 2.5, "overflow_count": 2, "overflow_values": [360.0, 365.0], "representative_minutes": 365, "split": "train"}}`.
- TRAIN_VALUE_LOSS_TRUNCATION: `False`.

## Finite Support vs Quantile Tail

- `FINITE_SUPPORT_REVIEW` is the only C0 decision surface.
- `POSITIVE_QUANTILE_TAIL_STATUS = UNRESOLVED_AND_OUT_OF_SCOPE`.
- Positive quantile levels remain `[0.1, 0.3, 0.5, 0.7, 0.9]`; no tail policy was changed.

## Human Decisions

### C0-D01

- Options: `KEEP_360 / EXPAND_TO_390 / EXPAND_TO_420 / EXPAND_TO_450 / EXPAND_TO_480 / OTHER`
- Recommendation: `KEEP_360`
- Evidence: Train overflow is 2/342 (0.58%), exact values are 360 and 365, and the 365-minute survival representative has mean absolute error 2.5 minutes (max 5).

### C0-D02

- Options: `KEEP_180 / EXPAND_TO_210 / EXPAND_TO_240 / EXPAND_TO_300 / EXPAND_TO_360 / OTHER`
- Recommendation: `EXPAND_TO_210`
- Evidence: Train overflow is 34/1793 (1.90%); 24 rows are 189/199 and 10 rows are 343. Expanding to 210 resolves the 24 moderate-tail rows while retaining the rare 343-minute tail and avoids unnecessary class doubling.

### C0-D03

- Options: `KEEP_60 / EXPAND_TO_75 / EXPAND_TO_90 / EXPAND_TO_120 / OTHER`
- Recommendation: `KEEP_60`
- Evidence: Train overflow is 0/1880; Development has 28/1765 (1.59%) across only 3 episodes, and D_TX is a chain endpoint with no downstream parent-conditioning role.

## Safety

```text
M1_TRAINING_RUNS = 0
TUNING_RUNS = 0
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = false
GATE_B2_FEATURE_FREEZE = true
M1_TARGET_SUPPORT_FROZEN = false
HYPERPARAMETER_TUNING_AUTHORIZED = false
```

No support/config update, training, tuning, C1, Final Test, FULL, or paper_full was run.
