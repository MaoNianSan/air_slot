# PRE Ownership Gate Audit

- audit date: `2026-08-17`
- audited change range: `6df4a31bac6c6cbe4d3de9455021976247871e79..88ad2843c8f2713cd4ae6c704b7d9247442ea51e`
- worktree at audit start: `CLEAN`
- result: `ARCHITECTURAL_DRIFT = PRE_OWNERSHIP_VIOLATION`
- gate status: `FAIL`

The required ownership map is:

| Classification | Required owner |
| --- | --- |
| `PRE_DATA_CONSTRUCTION` | `model/PRE/**` |
| `MODEL_LOGIC` | `model/M1/**` through `model/M4/**` |
| `EXPERIMENT_ORCHESTRATION` | `exp/**` |
| `EVALUATION_ONLY` | `exp/**` |
| `ENGINEERING_ONLY` | validation/test/tooling modules, provided no scientific construction is implemented there |

## Function Classification

| File | Newly added or modified functions/classes | Classification | Location check |
| --- | --- | --- | --- |
| `exp/exp1/history.py` | `HistoryRepresentation`; `adaptive_history`; `current_history`; `fixed_history`; `represent_history` | `MODEL_LOGIC` because these functions define the M1 information representation used for training and inference | **FAIL**: scientific model-input logic is implemented under `exp/**`; it belongs under `model/M1/**` |
| `model/M1/cache.py` | `_update_hash`; `_stable_store_hash`; `M1CanonicalRaggedStore.from_partitions`; `canonical_node_count`; `expanded_prefix_node_count`; `partition`; `M1RaggedDataset.__post_init__`; `__len__`; `_example`; `__getitem__`; `M1DevelopmentBaseCache.from_partitions`; `partition`; `save`; `load`; `cache_key` | `MODEL_LOGIC` plus model-artifact `ENGINEERING_ONLY` | PASS: operates only on model-ready examples and M1 representations under `model/M1/**`; no raw dataset preprocessing |
| `model/M1/data.py` | `validate_history_sequence`; `validate_full_history_prefix`; `encode_pre_sequence` | `MODEL_LOGIC` | PASS: typed PRE-state validation and M1 tensor encoding under `model/M1/**` |
| `model/M1/lifecycle.py` | `M1TrainingExample.from_target_labels`; `M1Lifecycle.__init__`; `_resolve_device`; `_batch`; `_batch_indices`; `batching_diagnostics`; `train`; `batched_logits`; `calibrate`; `load` | `MODEL_LOGIC` plus model-runtime `ENGINEERING_ONLY` | PASS: model training, calibration, batching, and loading under `model/M1/**` |
| `model/PRE/pipeline.py` | `ProductionPREPublisher`; `__init__`; `from_project`; `publish`; `publish_production_pre`; `publish_states` | `PRE_DATA_CONSTRUCTION` | PASS: admissibility, registry mapping, support, evidence, and PRE-state publication remain under `model/PRE/**` |
| `validation/data2_v5_hstar_development.py` | `_heartbeat`; `PreparedData`; `_preparation_state_key`; `_save_preparation_state`; `_repository_sha`; `_hash_file`; `_contract_hashes`; `_expected_cache_key`; `_scientific_config_hash`; `_training_contract_payload`; `_training_contract_hash`; `_validate_cache_for_h`; `_validate_manifest_for_resume`; `_peak_rss_mb`; `_base_cache`; `_run_paths`; nested `progress`; `_parser` | `ENGINEERING_ONLY` | PASS only for the listed telemetry, hashing, cache-validation, resume, and CLI helpers |
| `validation/data2_v5_hstar_development.py` | `_ontime_paths`; `_aircraft_tail`; `_episode_reservoirs`; `_lightweight_flights`; nested `value`; `_load_selected_typed_records`; `_weather_index`; `_latest_weather`; `_publish_states`; `_source_paths`; `_source_manifest_hash` | `PRE_DATA_CONSTRUCTION` | **FAIL**: directly opens BTS/NOAA/reference files, uses raw column names, reconstructs timestamps, pairs episodes, maps stations/weather, and publishes PRE states outside `model/PRE/**` |
| `validation/data2_v5_hstar_development.py` | `_active`; `prepare_data` | mixed `PRE_DATA_CONSTRUCTION` and `MODEL_LOGIC` | **FAIL**: combines PRE-state construction with M1 active-example/target preparation in a validation runner |
| `validation/data2_v5_hstar_development.py` | `_examples` | `MODEL_LOGIC` | **FAIL**: creates M1 training examples outside `model/M1/**` |
| `validation/data2_v5_hstar_development.py` | `_ece`; `evaluate`; `_write_h_decision` | `EVALUATION_ONLY` | **FAIL**: Development scoring and model-selection decision logic belong under `exp/**` |
| `validation/data2_v5_hstar_development.py` | `_run_candidate`; `main` | `EXPERIMENT_ORCHESTRATION` | **FAIL**: H-selection training/calibration/evaluation orchestration belongs under `exp/**` |
| `validation/data2_v5_wstar_development.py` | `_load_exp1_config`; `_validate_h_freeze`; `_load_immutable_cache`; `_model_code_hashes`; `_w_selection_contract_hash`; `_validate_cache_for_w`; `_run_paths`; `_validate_resume`; nested `progress`; `_parser` | `ENGINEERING_ONLY` | PASS only for the listed loading, validation, hashing, resume, telemetry, and CLI helpers |
| `validation/data2_v5_wstar_development.py` | `_fixed_views` | `MODEL_LOGIC` / `EXPERIMENT_ORCHESTRATION` | **FAIL**: the runner owns a scientific history-view transformation instead of calling a model-owned M1 history API from an experiment module |
| `validation/data2_v5_wstar_development.py` | `_view_summary`; `recommend_window`; `_write_w_evidence` | `EVALUATION_ONLY` | **FAIL**: W scoring, equivalence, and recommendation logic belong under `exp/**` |
| `validation/data2_v5_wstar_development.py` | `_run_candidate`; `main` | `EXPERIMENT_ORCHESTRATION` | **FAIL**: W-selection orchestration belongs under `exp/**` |
| `validation/performance_closure_p0.py` | `ProfileResult`; `StageProfiler.__init__`; `_rss_mb`; `capture`; `zero`; `summary`; `_file_hash`; `_contract_hashes`; `_equivalence_payload`; `_serialize_baseline`; `_serialize_cache`; `_compare_equivalence`; `_training_smoke`; `_device_status`; `_write_json`; `main` | `ENGINEERING_ONLY` | PASS only for profiling, equivalence reporting, serialization, runtime smoke, and CLI responsibilities |
| `validation/performance_closure_p0.py` | `_discover_january_file`; `_read_projected_subset`; `_convert_rows`; `_filter_completed`; `_weather_sources`; `_select_episodes`; `_read_weather`; `_build_nodes`; `_match_weather`; `_publish`; `_sequences`; `_label_audit`; `_run_profile` | `PRE_DATA_CONSTRUCTION` or mixed PRE construction/orchestration | **FAIL**: directly reads BTS/NOAA, uses raw columns, maps stations, pairs episodes, builds nodes, aligns weather, and publishes states outside `model/PRE/**` |
| `validation/performance_closure_p0.py` | `_encode_examples` | `MODEL_LOGIC` | **FAIL**: M1 example encoding belongs under `model/M1/**` |
| `validation/support/data2_m1.py` | `publish_states` | `PRE_DATA_CONSTRUCTION` | **FAIL**: rolling-node/weather/PRE-state publication helper remains under `validation/**` rather than `model/PRE/**` |
| `tests/experiments/test_exp1_history.py` | `_prefix`; six `test_*` functions | `ENGINEERING_ONLY` test code | PASS: test-only fixture and assertions under `tests/**` |
| `tests/m1/test_performance_closure.py` | `_example`; `_contracts`; `_cache`; `_flight`; six `test_*` functions | `ENGINEERING_ONLY` test code | PASS: test-only fixtures and assertions under `tests/**` |
| `tests/m1/test_wstar_development.py` | three `test_*` functions | `ENGINEERING_ONLY` test code | PASS: test-only assertions under `tests/**` |
| `tests/contract/test_configuration_layers.py` | `test_layers_load_separately` | `ENGINEERING_ONLY` test code | PASS |
| `tests/integration/test_reconciliation_contracts.py` | `test_formal_m1_uses_development_frozen_hidden_size_selection` | `ENGINEERING_ONLY` test code | PASS |

## Drift Findings

### PRE construction outside PRE

`validation/data2_v5_hstar_development.py`, `validation/performance_closure_p0.py`, and
`validation/support/data2_m1.py` directly implement dataset preprocessing that the architecture
assigns exclusively to PRE. The violations include raw file access, raw-column projection,
timestamp reconstruction, predecessor-successor pairing, rolling-node construction, station
mapping, weather alignment, admissibility lookup, and PRE-state publication.

### Scientific model logic outside model

`exp/exp1/history.py` owns M1 history-representation semantics, while validation runners create
fixed-history views and M1 examples. These are model-input/model-data responsibilities and must
be owned by `model/M1/**`.

### Experiment and evaluation logic outside exp

H/W training orchestration, Development metrics, equivalence rules, and human recommendation
construction are implemented in `validation/data2_v5_*_development.py`. These responsibilities
belong under `exp/**`; validation should only invoke and verify them.

### Existing static-test gap

`validation/dependency_rules.py::scan_dependency_boundaries` checks import direction and a small
set of dataset-specific tokens inside model modules. It does not classify function responsibility,
does not reject raw preprocessing under `validation/**`, and does not reject model logic under
`exp/**`. Therefore a passing `tests/static/test_dependency_boundaries.py` result is not evidence
that this ownership gate passes.

## Gate Decision

```text
ARCHITECTURAL_DRIFT = PRE_OWNERSHIP_VIOLATION
PRE_OWNERSHIP_GATE = FAIL
WARNING_THRESHOLD_WORK = BLOCKED
FINAL_TEST_ACCESS_COUNT = 0
```

No warning-cohort build, sampling, threshold search, H/W rerun, or Final Test access is permitted
until ownership is repaired or an explicit architecture exception is approved. Existing H/W
artifacts remain historical evidence and must not be silently regenerated under a moved pipeline.

## Post-Repair Closure

The sections above are the immutable pre-repair finding. The authorized migration
subsequently removed those violations. Current machine-readable evidence is
`artifacts/diagnostics/v5_development_freeze/PRE_OWNERSHIP_GATE_V2.json`.

```text
PRE_OWNERSHIP_GATE = PASS
STATIC_VOLUME_GATE = PASS
PRE_DATA_CONSTRUCTION_OUTSIDE_PRE = 0
MODEL_LOGIC_OUTSIDE_MODEL = 0
EXP_LOGIC_OUTSIDE_EXP = 0
FINAL_TEST_ACCESS_COUNT = 0
```

### Post-repair function classification

| Current owner | Functions/classes added or changed by the repair | Classification | Location check |
| --- | --- | --- | --- |
| `model/M1/history.py` | `HistoryRepresentation`; `adaptive_history`; `current_history`; `fixed_history`; `represent_history` | `MODEL_LOGIC` | PASS |
| `model/M1/preparation.py` | `active_rows`; `build_training_examples`; `normalization_rows` | `MODEL_LOGIC` | PASS |
| `model/PRE/cohort.py` | `split_for_date` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/pipeline.py` | `ProductionPREPublisher.target_support`; modified `publish` delegation | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/development.py` | `PREPreparedEpisode`; `PREDevelopmentCohorts`; `_publish_partition`; `build_sampled_pre_cohorts` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/development_support.py` | `stream_january_flights`; `stream_coupon_routes`; `reference_summary`; `turnaround_cells`; `taxi_cells`; `exposure_cells`; `passenger_cells`; `chain_stats`; `sample_three_way_cohort`; `load_typed_records`; `publish_states` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/profiling.py` | `PREProfileBundle`; `_discover_source`; `_read_projected_subset`; `_convert_rows`; `_filter_completed`; `_weather_sources`; `_select_episodes`; `_read_weather`; `_build_nodes`; `_match_weather`; `_publish`; `build_profile_pre_bundle` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/reference/candidate_audit.py` | `_missing`; `_number`; `_utc`; `_zip`; `_iter_rows`; `_quantile`; `_summary`; `_hist_summary` and nested `quantile`; `_sql_values`; `_sql_summary`; `_group_refs` and nested `flush`; `_coverage`; `main` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/streaming/data2.py` | `load_timezones`; `config_hash`; `registry_hash`; `ontime_paths`; `development_source_paths`; `development_source_manifest_hash`; `aircraft_tail`; `iter_lightweight_flights` and nested `value`; `lightweight_flights`; `preparation_state_key`; `save_preparation_state`; `episode_reservoirs`; `load_selected_typed_records`; `weather_index`; `latest_weather`; `publish_episode_states`; `stream_completed_flights`; `weather_index_and_stats` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/streaming/development.py` | `_file_hash`; `pre_contract_hash`; `source_hashes`; `StreamCounts.as_dict`; `StreamCounts.from_dict`; `_node_count`; `summarize_episode_publication`; `_merge_episode`; `run_development_pre_stream` | `PRE_DATA_CONSTRUCTION` | PASS |
| `model/PRE/streaming/development.py` | `_heartbeat`; `_write_manifest` | `ENGINEERING_ONLY` supporting PRE execution | PASS |
| `exp/exp1/development/hstar.py` | `PreparedData`; `_heartbeat`; `prepare_data`; `_repository_sha`; `_hash_file`; `_contract_hashes`; `_scientific_config_hash`; `_training_contract_payload`; `_training_contract_hash`; `_expected_cache_key`; `_validate_cache_for_h`; `_validate_manifest_for_resume`; `_peak_rss_mb`; `_base_cache`; `_run_paths`; `_run_candidate`; `_parser`; `main` | `EXPERIMENT_ORCHESTRATION` or experiment-local `ENGINEERING_ONLY` | PASS |
| `exp/exp1/development/hstar.py` | `_ece`; `evaluate`; `_write_h_decision` | `EVALUATION_ONLY` | PASS |
| `exp/exp1/development/wstar.py` | `_load_exp1_config`; `_validate_h_freeze`; `_load_immutable_cache`; `_model_code_hashes`; `_w_selection_contract_hash`; `_validate_cache_for_w`; `_fixed_views`; `_run_paths`; `_validate_resume`; `_run_candidate` and nested `progress`; `_parser`; `main` | `EXPERIMENT_ORCHESTRATION` or experiment-local `ENGINEERING_ONLY` | PASS |
| `exp/exp1/development/wstar.py` | `_view_summary`; `recommend_window`; `_write_w_evidence` | `EVALUATION_ONLY` | PASS |
| `validation/performance_closure_p0.py` | `ProfileResult`; `StageProfiler` methods; `_file_hash`; `_contract_hashes`; `_sequences`; `_label_audit`; `_encode_examples`; `_equivalence_payload`; `_serialize_baseline`; `_serialize_cache`; `_run_profile`; `_compare_equivalence`; `_training_smoke`; `_device_status`; `_write_json`; `main` | `ENGINEERING_ONLY` validation/profiling; all scientific transforms are invoked from PRE/M1 APIs | PASS |
| validation compatibility files | `main` in the retired mixed-ownership runners; `deprecated_main`; `source_stats`; `weather_state_stats`; `validation.pre_development_stream.main`; ownership-gate scan/build helpers | `ENGINEERING_ONLY` | PASS |
| `tests/pre/test_ownership_migration_equivalence.py`; changed M1/static tests | all fixture helpers and `test_*` functions, including the fixed real-subset test | `ENGINEERING_ONLY` test code | PASS |

`exp/exp1/history.py` and `model/M1/splits.py` now contain compatibility
re-exports only. `model/PRE/raw_schema.py` contains PRE-owned constants only.
`exp/exp4/portability.py` and `model/M1/target_builder.py` changed imports only;
their existing function bodies did not acquire preprocessing or model logic.

The ownership gate scans nested functions as well as module-level functions and
explicitly rejects M1 history/example/normalization implementations under
`exp/**` or `validation/**`. This closes the residual `_active_rows` / `_examples`
placement found during final diff review.
