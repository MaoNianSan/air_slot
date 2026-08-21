# AIR_SLOT_DATA_USAGE_CONTRACT_V1

Status: `DATA_USAGE_DECISIONS_APPLIED_AUDIT_PASS` on August 21, 2026. This is
an implementation-linked boundary document, not scientific evidence and not a
replacement for the versioned registries.

## 1. Processing Boundary

AirSlot does not consume raw Data1/Data2 columns directly:

```text
raw source -> source adapter/parser -> PRE canonicalization
           -> operational/scientific variables -> M1/M2/M3/M4
```

Every raw column must declare source meaning, availability, transformation,
owner, unit, missing rule, provenance, and downstream role. A raw column is not
automatically a model feature.

## 2. Dataset Roles

- **Data1 (`data1_2019`)**: trajectory-rich applicability and validation data.
  It must not redefine BTS schedule truth, Data2 labels, or passenger outcomes.
- **Data2 (`data2_2019`)**: primary M1/M2 experimental source for BTS operational
  events plus NOAA weather.
- Data1/Data2 records are never mixed or silently overlaid. Current registries,
  adapters, canonical contracts, PRE publication, config, and tests are truth;
  legacy READMEs are historical context only.

## 3. Ownership

| Layer | Owns |
|---|---|
| PRE | raw column interpretation, HHMM/timezone/date handling, source units, airport mapping, weather decoding, event availability, provenance |
| M1 | train-only normalization, causal history construction, masks, principal feature encoding |
| M2 | structured operational consequences |
| M3 | action representation |
| M4 | monetary/risk interpretation |

## 4. Data2 BTS Contract

| Raw column(s) | PRE canonical / role | Principal use |
|---|---|---|
| `Tail_Number` | aircraft identity / continuity context | PRE only; no ordinal M1 feature |
| `Reporting_Airline` | carrier context/reference key | typed context; no ordinal feature without a frozen embedding contract |
| `Origin`, `Dest` | airport identity and joins | weather/reference lookup; typed context |
| `FlightDate`, `CRSDepTime`, `CRSArrTime` | UTC schedule reference | `schedule.signed_minutes_to_crs_departure` is dynamic M1 input |
| `DepTime`, `ArrTime`, `WheelsOff`, `WheelsOn` | direct operational clocks | `EVAL_OUTCOME`/labels; inference only through declared replay |
| `DepDelay`, `ArrDelay` | signed schedule-to-actual offsets | direct-clock date disambiguation and missing-direct fallback; never a current feature |
| `DepDelayMinutes`, `ArrDelayMinutes` | nonnegative delay reporting only | diagnostics/classification; never timestamp reconstruction |
| `TaxiOut`, `TaxiIn` | operational durations | wheels fallback, labels, and frozen references; never a current feature merely because the archive contains it |
| `Cancelled`, `Diverted` | completed operational outcome status | `D2-BTS-ACTUAL`; never schedule evidence |

Flight identity and aircraft continuity are registered separately as
`D2-BTS-FLIGHT-IDENTITY`. `FlightDate`, carrier, flight number, route, and
`Tail_Number` are retained identity/provenance fields; they are not ordinal or
continuous M1 features.

### Direct/derived precedence

Direct clock values are primary. Signed `DepDelay`/`ArrDelay` resolve their
calendar date and supply a fallback only when the direct clock is missing.
`DepDelayMinutes`/`ArrDelayMinutes` are clipped reporting fields and never
reconstruct timestamps. Taxi durations remain wheel-clock diagnostics/fallbacks.
BTS actual outcomes remain:

```text
decision_time_role = EVAL_OUTCOME
availability_basis = POSTHOC_ONLY
```

The PRE-owned replay projection is separate:

```text
rule_id = D2-BTS-FACTUAL-REPLAY
policy = DECLARED_EVENT_TIME_REPLAY
declared_lag_minutes = 0
availability_time = operational_event_time
downstream = PRE, M1, EXP3
observed_message_arrival_claim = false
production_availability_claim = false
```

This is a retrospective event-time assumption. It does not claim observed
message-arrival time or production availability time. A factual event may enter
stage construction only when its declared availability is at or before the
information cutoff. Training labels and evaluation outcomes remain post-hoc.

## 5. Data2 NOAA Contract

| Raw field | Canonical field | Rule |
|---|---|---|
| `TMP` | `weather.temperature_c` | NOAA coded temperature to Celsius; explicit missing |
| `DEW` | `weather.dewpoint_c` | NOAA coded dew point to Celsius; explicit missing |
| `VIS` | `weather.visibility_m` | meter scale; `999999` is missing |
| `WND` speed | `weather.wind_speed_mps` | coded speed to m/s |
| `WND` direction | `weather.wind_direction_deg` | principal uses sin/cos only |
| `CIG` | `weather.ceiling_base_m` plus typed status | finite meters; `22000` unlimited; `99999` missing |
| `REM` | QNH/present-weather support | no unsupported MSLP invention |

Ceiling status is explicit: `FINITE`, `UNLIMITED`, or `MISSING`. M1 uses a
finite normalized value plus an unlimited mask and a missing mask; neutral
numeric values are never interpreted as a real 0 m ceiling.

Wind direction linear degree delta and arithmetic AR are removed from the
principal schema. Wind gust may remain in the PRE canonical schema, but absent
an authoritative Data2 mapping it is removed from principal M1, including its
derived features and dedicated masks.

## 6. Data1 Source Mapping

- `D1-OPENSKY-FLIGHT` declares `callsign` and `day` for episode/flight identity.
- `D1-OPENSKY-STATE` declares altitude, heading, vertical-rate, position-update,
  and contact fields consumed by canonicalization; source `callsign` is
  explicitly unused.
- `D1-METAR` declares the station, temperature/dewpoint, wind, visibility,
  cloud-layer, present-weather, and METAR-text fields actually consumed. Source
  `mslp` is explicitly unused; QNH comes from the METAR text contract.
- OurAirports `elevation_ft` and `type` are reference-build-only metadata.
- Eurostat `id` and `size` are JSON-stat source-schema metadata, not passenger
  scientific variables.

## 7. Reference and Artifact Boundaries

- T-100 `ORIGIN`, `DEST`, `YEAR`, and `MONTH` are reference-build-only join and
  period fields. `CLASS` is optional projected metadata and remains `None` when
  absent.
- The timezone adapter publishes only airport identity to IANA timezone;
  latitude/longitude belong to the airport reference contract.
- `turnaround_reference` and `taxi_reference` are static, train-frozen,
  lineage-complete `successor_state` publications.
- `expected_downstream_exposure` is only an M2 frozen reference derived from
  canonical PRE schedule rows. It is not a PRE/M1 principal state variable.
- M1 coverage metadata uses
  `DERIVED_M1_TRAINING_COVERAGE_ARTIFACT_V1`; `decision_time`, `node_index`,
  and `operational_stage` are PRE decision-node fields, not BTS columns.
- `passenger_reference` and `segment_reference` remain aggregate domain proxies,
  never flight-level direct truth.

## 8. M2 PRE Ownership

M2 calls `build_data2_m2_train_preparation(...)` and consumes
`DATA2_M2_TRAIN_PREPARATION_V1`. Timezone lookup, BTS CSV reading, HHMM-to-UTC
conversion, and canonical row construction remain inside PRE. M2 does not open
the timezone CSV or interpret its raw schema.

## 9. Derived-Value Rule

Every delta/AR variable declares source columns, formula, availability, unit,
and missing behavior. A delta is valid only when current and previous source
values are observed. An AR value is valid only when the frozen coverage rule is
met. Otherwise the encoded value is neutral and a derived-missing mask is 1;
missing values are never silently replaced by zero before differencing or
averaging.

## 10. M1 Principal Classification

- Dynamic: weather values, typed ceiling masks, schedule countdown, state flags,
  legal deltas/AR, observation-age and evidence/support masks.
- Historical sequence: causal PRE prefixes only (`information_cutoff <= decision_time`).
- Static reference: train-frozen turnaround/taxi minutes with lineage.
- Context only: route, carrier, aircraft, airport and other typed identities.
- Labels/evaluation only: `T_IB_A00`, `D_OB`, `D_TX`, and post-hoc outcomes.
- Removed principal duplicates: wind-gust features, wind-direction delta/AR,
  stage one-hot, and fixed-grid `node.spacing_minutes`.

## 11. Forbidden Practices

1. Raw columns directly into a model.
2. Fuzzy production mapping such as `if "delay" in column`.
3. Unknown or unsupported values silently filled with zero.
4. Future realized events used as current state without replay legality.
5. Tail/carrier/airport identities ordinal-encoded as numeric distance.
6. Data1 weather or post-hoc Data2 outcomes silently overlaid into another role.

## 12. Registry and Freeze Requirements

Each mapping entry must expose:

```text
raw_column, canonical_variable, source, owner, role, unit,
availability_rule, transformation, missing_rule, downstream_module, provenance
```

Before M1 training, freeze and hash `DATA_MAPPING_VERSION`,
`FEATURE_SCHEMA_VERSION`, `NORMALIZATION_VERSION`, `LABEL_VERSION`, and
`REPLAY_POLICY_VERSION`. The seven DUC decisions are applied to the current
registries. This closure does not authorize Gate B, M1 training, tuning, Final
Test, FULL, or paper runs.

## 13. Upstream Debugging Rule

When a downstream experiment fails, trace:

```text
experiment -> model -> feature encoder -> PRE variable -> raw source
```

Fix the first semantic mismatch at its owning layer; do not patch the model to
hide an upstream data-contract error.

## 14. Repeatable Contract Audit

Run the read-only diagnostic audit with:

```text
python -m validation.data_usage_contract_audit
```

It reads the current source-adapter registry, data-usage/scientific registries,
PRE canonicalizers/publication paths, and M1 feature schema. It does not open a
raw-data root. The generated mapping remains a trace artifact:

```text
artifacts/diagnostics/data_usage_contract_audit/
  AIR_SLOT_DATA_USAGE_CONTRACT_AUDIT.json
  AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.csv
  AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.yaml
  AIR_SLOT_DATA_USAGE_RAW_COLUMN_AUDIT.csv
  AIR_SLOT_DATA_USAGE_PRE_OUTPUT_AUDIT.csv
  AIR_SLOT_DATA_USAGE_M1_FEATURE_AUDIT.csv
```

PASS classifications are `COVERED_ACTIVE`, `EXPLICITLY_UNUSED`,
`DIAGNOSTIC_ONLY`, `REFERENCE_BUILD_ONLY`, and `SOURCE_SCHEMA_METADATA`.
Failures are `PRE_BYPASS`, `RUNTIME_USED_NO_CONTRACT`,
`AMBIGUOUS_ACTIVE_COLUMN`, `ACTIVE_SEMANTIC_CONFLICT`,
`ACTIVE_REGISTRY_CONFLICT`, and `ACTIVE_PRE_OUTPUT_CONFLICT`.

The current closure requires every failure count to be zero. A PASS still does
not authorize M1 training or entry into Gate B.
