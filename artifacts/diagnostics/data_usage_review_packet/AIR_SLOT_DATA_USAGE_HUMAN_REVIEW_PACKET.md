# AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET_V1

Status: **DATA_USAGE_REVIEW_PACKET_READY**

This packet is diagnostic only. It does not freeze a registry, modify the M1 feature contract, authorize training, tuning, Gate B, or Final Test.

## PRE Bypass

1. `model/M2/freeze.py:119-124`, `load_timezones(root)` reads `iata` and `timezone` from `data2/refs/us_airport_timezones.csv`. `build_m2_data2_formal_registry()` calls it at line 280, then passes the table into PRE-owned `collect_train_rows()` (`model/PRE/reference/data2_m2_train_fit.py:67-91`).
   - Scientific variable: `airport_timezone`
   - Why M2 needs it: local BTS HHMM to UTC conversion during train-row preparation
   - Current transformation: raw timezone CSV -> dict[IATA, IANA] -> `canonicalize_ontime_row`
   - Current output: canonical train rows, frozen M2 references, train scales, and M2 formal registry
   - Downstream usage: M2 formal artifact construction; no direct M2 timezone feature
   - Classification: **C — local-time conversion only**
   - Recommendation: PRE-owned canonical train artifact or typed timezone-backed preparation artifact; M2 consumes only that artifact.

## Runtime Rule Registration

`D2-BTS-FACTUAL-REPLAY` is a candidate separate projection rule. `D2-BTS-ACTUAL` remains `POSTHOC_ONLY` / `EVAL_OUTCOME`.

```yaml
rule_id: D2-BTS-FACTUAL-REPLAY
dataset_id: data2_2019
source_rule: D2-BTS-ACTUAL
raw_source_role: POSTHOC_COMPLETED_OPERATIONAL_EVENT
projection_role: DECLARED_RETROSPECTIVE_FACTUAL_REPLAY
principal_declared_lag_minutes: 0
availability_semantics: event_time + declared_lag
observed_message_arrival: false
production_availability_claim: false
decision_time_role: INFERENCE_EVIDENCE_UNDER_DECLARED_REPLAY
downstream: [PRE, M1, Exp3]
source_outcome_role_preserved: true
final_test_access_count: 0
```

## Raw Columns Requiring Human Decision

- **RAW-01** `D1-FLIGHTLIST / opensky_flightlist` — `callsign, day`; `MODEL_OR_PRE_USED_NO_RULE`. Decide whether D1-OPENSKY-FLIGHT must declare both columns explicitly.
- **RAW-02** `D1-STATE / opensky_state_vectors` — `heading, lastposupdate, lastcontact`; `MODEL_OR_PRE_USED_NO_RULE`. Decide whether D1-OPENSKY-STATE must declare the projected fields used by the canonicalizer.
- **RAW-03** `D1-METAR / iem_metar` — `station, drct, dwpf, vsby, skyc1..3, skyl1..3, wxcodes, gust`; `MODEL_OR_PRE_USED_NO_RULE`. Decide whether to expand D1-METAR mapping or split canonical weather rules; gust must remain non-principal unless separately supported.
- **RAW-04** `D1-OURAIRPORTS / ourairports` — `elevation_ft, type`; `REFERENCE_BUILD_ONLY`. Decide whether these projected reference-build fields should be declared in D1-OURAIRPORTS.
- **RAW-05** `D2-ONTIME / bts_ontime` — `Reporting_Airline, Flight_Number_Reporting_Airline, Cancelled, Diverted`; `MODEL_OR_PRE_USED_NO_RULE`. Decide whether schedule/actual rules should declare these fields explicitly; no ordinal feature is implied.
- **RAW-06** `D2-T100 / bts_t100` — `ORIGIN, DEST, YEAR, MONTH`; `REFERENCE_BUILD_ONLY`. Decide whether these join/period fields should be declared in the T-100 adapter contract.
- **RAW-07** `D2-TIMEZONE / timezone_reference` — `lat, lon`; `AMBIGUOUS`. Decide whether lat/lon belong in the timezone adapter or should be removed from its canonical output.
- **RAW-08** `D1-EUROSTAT / eurostat JSON-stat` — `id, size`; `AMBIGUOUS`. Decide whether these are source-schema metadata that must be declared or a separate payload contract.

## Semantic Conflicts Requiring Human Decision

- **SC-01** `D1-EUROSTAT` / `id` — `MISSING_RULE_MISMATCH`; affected `PRE/reference`. Resolution: Add id to the adapter/payload contract or split the JSON-stat metadata rule.
- **SC-02** `D1-EUROSTAT` / `size` — `MISSING_RULE_MISMATCH`; affected `PRE/reference`. Resolution: Add size to the adapter/payload contract or split the JSON-stat metadata rule.
- **SC-03** `D1-STATE` / `baroaltitude` — `MISSING_RULE_MISMATCH`; affected `PRE/M1`. Resolution: Declare the field under D1-OPENSKY-STATE; do not infer it from evaluation-only events.
- **SC-04** `D1-STATE` / `geoaltitude` — `MISSING_RULE_MISMATCH`; affected `PRE/M1`. Resolution: Declare the field under D1-OPENSKY-STATE.
- **SC-05** `D1-STATE` / `vertrate` — `MISSING_RULE_MISMATCH`; affected `PRE/M1`. Resolution: Declare the field under D1-OPENSKY-STATE.
- **SC-06** `D2-ONTIME` / `Tail_Number` — `ROLE_MISMATCH`; affected `PRE/episode`. Resolution: Confirm one explicit PRE identity/continuity mapping with no numeric M1 encoding.
- **SC-07** `D2-M1-TRAINING-COVERAGE` / `decision_time` — `ROLE_MISMATCH`; affected `validation/M1`. Resolution: Move the fields to a derived coverage-artifact schema; do not add them to the BTS adapter.
- **SC-08** `D2-M1-TRAINING-COVERAGE` / `node_index` — `ROLE_MISMATCH`; affected `PRE/validation`. Resolution: Represent node_index as derived PRE lineage, not raw BTS coverage.
- **SC-09** `D2-M1-TRAINING-COVERAGE` / `operational_stage` — `ROLE_MISMATCH`; affected `PRE/M1`. Resolution: Represent stage as derived PRE state and retain the training-coverage rule separately.
- **SC-10** `D2-T100` / `CLASS` — `MISSING_RULE_MISMATCH`; affected `PRE/reference`. Resolution: Decide whether CLASS is projected optional metadata or a required T-100 contract field.

## Registry Conflicts Requiring Human Decision

- **REG-01** `D1-EUROSTAT` — registry stale or incomplete. Declare id/size in the source/payload contract, or split the payload rule.
- **REG-02** `D2-TURNAROUND-REFERENCE` — registry legacy V1 semantics. Change the registry pre_family to successor_state after human approval; do not patch M1.
- **REG-03** `D2-TAXI-REFERENCE` — registry legacy V1 semantics. Change the registry pre_family to successor_state after human approval; preserve train-frozen lineage.
- **REG-04** `D2-DOWNSTREAM-EXPOSURE` — registry coverage gap. Decide whether to add a PRE/reference scientific variable or narrow the rule to the M2 frozen artifact boundary.
- **REG-05** `D2-M1-TRAINING-COVERAGE` — registry role error. Move this to a derived training-coverage artifact contract; do not register synthetic fields as BTS raw columns.
- **REG-06** `D2-T100-CLASS` — registry adapter gap. Decide whether CLASS is optional projected metadata or required input, then align adapter and rule.

## PRE Output Conflicts Requiring Human Decision

- **PRE-01** `passenger_reference` — current `reference_state via RegistryPREMapper when a legal aggregate record exists`; expected `reference_state / aggregate domain proxy; not flight-level truth`. First divergence: registry consumer/support alignment between D2 passenger rules and scientific_variables.yaml
- **PRE-02** `turnaround_reference` — current `successor_state static MODEL_FEATURE with reference lineage`; expected `successor_state static train-frozen reference`. First divergence: D2-TURNAROUND-REFERENCE registry pre_family says reference_state
- **PRE-03** `taxi_reference` — current `successor_state static MODEL_FEATURE with reference lineage`; expected `successor_state static train-frozen reference`. First divergence: D2-TAXI-REFERENCE registry pre_family says reference_state
- **PRE-04** `segment_reference` — current `reference_state aggregate reference when mapped`; expected `reference_state DEVELOPMENT_FROZEN aggregate proxy`. First divergence: D2-T100-CLASS adapter/rule schema mismatch before PRE publication

## Automatically Resolvable / No Action

- **NAME_ONLY_MISMATCH**: none
- **STALE_LEGACY_SEMANTICS**: D2-TURNAROUND-REFERENCE pre_family=reference_state, D2-TAXI-REFERENCE pre_family=reference_state
- **UNUSED_RAW_COLUMN**: D1-FLIGHTLIST: number, registration, typecode, D1-STATE: callsign, D2-DB1B: MktFare, D2-ISD: CALL_SIGN, SLP
- **DIAGNOSTIC_ONLY**: D2-ISD: REPORT_TYPE quality flag, D2-M1-TRAINING-COVERAGE: decision_time, node_index, operational_stage are derived metadata
- **REFERENCE_BUILD_ONLY**: D1-OURAIRPORTS: elevation_ft, type, D2-T100: ORIGIN, DEST, YEAR, MONTH
- **automatic_action**: none

## Answerable Decisions

### DUC-01
Question: M2 timezone handling should be owned by which boundary?
Recommendation: **A**
Reason: The current read exists only to support PRE HHMM-to-UTC conversion in collect_train_rows; M2 has no independent timezone semantics.
Options: A=PRE produces canonical train rows or a typed timezone-backed artifact; M2 consumes only that artifact.; B=M2 may read the shared timezone table through a formally approved adapter.; C=Retain the current M2 raw read.

### DUC-02
Question: How should the declared factual replay projection be represented?
Recommendation: **A**
Reason: The projection is already role-separated in code and must not mutate source outcome semantics.
Options: A=Register D2-BTS-FACTUAL-REPLAY as a separate projection rule while preserving D2-BTS-ACTUAL as POSTHOC_ONLY/EVAL_OUTCOME.; B=Keep the runtime rule unregistered until after training.; C=Rewrite D2-BTS-ACTUAL to be inference evidence.

### DUC-03
Question: How should D1-METAR fields used by the canonicalizer but absent from the rule be handled?
Recommendation: **A**
Reason: The fields are consumed for canonical weather semantics, but raw mapping coverage does not imply principal feature promotion.
Options: A=Expand or split the PRE-owned D1-METAR mapping, retaining gust as non-principal unless supported.; B=Remove the canonical weather parsing for those fields.; C=Register every projected field as an M1 feature.

### DUC-04
Question: What is the T-100 CLASS contract?
Recommendation: **A**
Reason: The current canonicalizer treats service class as optional; the schema should say so explicitly.
Options: A=Optional projected metadata with an explicit rule and adapter declaration.; B=Remove D2-T100-CLASS.; C=Make CLASS a required field for every T-100 row.

### DUC-05
Question: Which PRE family owns train-frozen turnaround and taxi references?
Recommendation: **A**
Reason: Current PRE publishes both numeric references into successor_state and M1 consumes that typed publication.
Options: A=successor_state, matching current static publication.; B=reference_state, preserving the current registry labels.; C=Both, with duplicate publication.

### DUC-06
Question: How should expected_downstream_exposure be represented in the scientific registry?
Recommendation: **B**
Reason: Current formal M2 consumption is through a typed frozen reference bundle; no M1 principal feature currently consumes it.
Options: A=Add a PRE/reference scientific variable with typed M2 lineage.; B=Keep it only as an M2 frozen artifact and narrow registry consumers.; C=Remove the frozen exposure reference.

### DUC-07
Question: How should synthetic M1 training-coverage fields be represented?
Recommendation: **A**
Reason: decision_time, node_index, and operational_stage are generated PRE/node metadata.
Options: A=Derived coverage-artifact schema, separate from raw BTS adapter columns.; B=Add the synthetic fields to the BTS source adapter.; C=Delete the coverage rule.

## Safety Boundary

- `M1_TRAINING_RUNS = 0`
- `TUNING_RUNS = 0`
- `FINAL_TEST_ACCESS_COUNT = 0`
- `PAPER_FULL_RUN = false`
- `GATE_B_ENTERED = false`

Stop at human review. No automatic batch repair was performed.
