# AIR_SLOT_DATA_USAGE_CONTRACT_V1

Status: implementation-linked contract draft, generated from the Data Gate A1
semantic repair. It is a boundary document, not scientific evidence and not a
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
| `DepDelayMinutes`, `ArrDelayMinutes`, `TaxiOut`, `TaxiIn` | derived checks, labels, frozen references | never a current feature merely because the archive contains it |

### Direct/derived precedence

Direct clock values are primary. Delay/taxi reconstructions are retained for
date-offset resolution, consistency diagnostics, and fallback only when the
direct clock is missing. BTS actual outcomes remain:

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

## 6. Derived-Value Rule

Every delta/AR variable declares source columns, formula, availability, unit,
and missing behavior. A delta is valid only when current and previous source
values are observed. An AR value is valid only when the frozen coverage rule is
met. Otherwise the encoded value is neutral and a derived-missing mask is 1;
missing values are never silently replaced by zero before differencing or
averaging.

## 7. M1 Principal Classification

- Dynamic: weather values, typed ceiling masks, schedule countdown, state flags,
  legal deltas/AR, observation-age and evidence/support masks.
- Historical sequence: causal PRE prefixes only (`information_cutoff <= decision_time`).
- Static reference: train-frozen turnaround/taxi minutes with lineage.
- Context only: route, carrier, aircraft, airport and other typed identities.
- Labels/evaluation only: `T_IB_A00`, `D_OB`, `D_TX`, and post-hoc outcomes.
- Removed principal duplicates: wind-gust features, wind-direction delta/AR,
  stage one-hot, and fixed-grid `node.spacing_minutes`.

## 8. Forbidden Practices

1. Raw columns directly into a model.
2. Fuzzy production mapping such as `if "delay" in column`.
3. Unknown or unsupported values silently filled with zero.
4. Future realized events used as current state without replay legality.
5. Tail/carrier/airport identities ordinal-encoded as numeric distance.
6. Data1 weather or post-hoc Data2 outcomes silently overlaid into another role.

## 9. Registry and Freeze Requirements

Each mapping entry must expose:

```text
raw_column, canonical_variable, source, owner, role, unit,
availability_rule, transformation, missing_rule, downstream_module, provenance
```

Before M1 training, freeze and hash `DATA_MAPPING_VERSION`,
`FEATURE_SCHEMA_VERSION`, `NORMALIZATION_VERSION`, `LABEL_VERSION`, and
`REPLAY_POLICY_VERSION`. The generated mapping draft and audit are diagnostic
artifacts; they require human review before promotion into authoritative
registries or any Gate B/training workflow.

## 10. Upstream Debugging Rule

When a downstream experiment fails, trace:

```text
experiment -> model -> feature encoder -> PRE variable -> raw source
```

Fix the first semantic mismatch at its owning layer; do not patch the model to
hide an upstream data-contract error.

## 11. Repeatable Contract Audit

Run the read-only diagnostic audit with:

```text
python validation/data_usage_contract_audit.py
```

It reads the current source-adapter registry, data-usage/scientific registries,
PRE canonicalizers/publication paths, and M1 feature schema. It does not open a
raw-data root or modify an authoritative registry. The generated mapping is a
non-authoritative draft for human review:

```text
artifacts/diagnostics/data_usage_contract_audit/
  AIR_SLOT_DATA_USAGE_CONTRACT_AUDIT.json
  AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.csv
  AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.yaml
  AIR_SLOT_DATA_USAGE_RAW_COLUMN_AUDIT.csv
  AIR_SLOT_DATA_USAGE_PRE_OUTPUT_AUDIT.csv
  AIR_SLOT_DATA_USAGE_M1_FEATURE_AUDIT.csv
```

The audit classifies each boundary as `COVERED`, `MISSING`,
`SEMANTIC_CONFLICT`, or `PRE_BYPASS`. A generated result does not freeze a
mapping, resolve Gate A1 human review, authorize M1 training, or enter Gate B.
