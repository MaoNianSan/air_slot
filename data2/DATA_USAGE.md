# DATA2 — Dataset Usage and Contract

**Document status**: current and code-grounded (audited 2026-08-16).
**Dataset instance**: `data2_2019`
**Authoritative evidence**: `registries/source_adapter_registry.yaml`, `registries/data_usage_rules.yaml`,
`registries/scientific_variables.yaml`, `registries/dataset_capabilities.yaml`,
`model/PRE/adapters/data2.py`, `model/PRE/canonical/normalization.py`, `model/PRE/episode/builder.py`,
`model/PRE/episode/node_builder.py`, `model/PRE/evidence/admissibility.py`, `model/PRE/reference/*_data2.py`,
`configs/scientific/foundation.yaml`, `model/M1/target_builder.py`, contract/unit tests under `tests/`.
Historical experiment outputs, manifests, and run artifacts are **not** evidence for this document.

---

## 1. Dataset role

Data2 (`data2_2019`) is the **primary experimental dataset** of the current Air Slot implementation.

- It is the only dataset instance with registered M1 training-label rules
  (`D2-LABEL-R-IB`, `D2-LABEL-R-OB`, `D2-LABEL-T-TX`, `D2-M1-TRAINING-COVERAGE`,
  `D2-TEMPORAL-SPLIT` in `registries/data_usage_rules.yaml`) and the only instance with an M1
  training-coverage/target-label code path (`model/M1/coverage.py`,
  `model/M1/target_builder.py:build_data2_target_labels`).
- The experiment/validation layout runs Data2 M1 fast/smoke workflows
  (`validation/data2_m1_*.py`), which confirms Data2 as the experimental benchmark instance.
- Its dataset profile is `EVENT_RICH_POSTHOC_INSTANCE`
  (`registries/dataset_capabilities.yaml`): complete post-hoc flight events, aggregate passenger
  references, and NOAA ISD weather; no ADS-B trajectory.

Data1 (`data1_2019`) is a separate trajectory-rich instance used to demonstrate framework/model
applicability across a different observation structure; it is documented in `data1/DATA_USAGE.md`.

## 2. Raw data sources

Only sources registered in `registries/source_adapter_registry.yaml` for `data2_2019` are consumed:

| adapter | source family | registered layout (relative to raw root) | format | canonical object(s) |
|---|---|---|---|---|
| `D2-ONTIME` | `bts_ontime` | `raw/bts/ontime/{year}/month=*/*.csv` | csv | FlightRecord + OperationalEventRecord |
| `D2-DB1B` | `bts_db1b` | `raw/bts/db1b/{year}/**/*.csv` | csv | AggregateReference |
| `D2-T100` | `bts_t100` | `raw/bts/t100/{year}/*.csv` | csv | AggregateReference |
| `D2-ISD` | `noaa_isd` | `raw/weather/noaa/{year}/*.csv` | csv | WeatherObservation |
| `D2-TIMEZONE` | `timezone_reference` | `refs/us_airport_timezones.csv` | csv | AirportReference |
| `D2-AIRPORT-REFERENCE` | `airport_reference` | `refs/airport_registry.csv` | csv | AirportReference |

Additional files read directly by the adapter:
- `refs/weather_station_map.csv` — NOAA ISD station id -> IATA airport mapping
  (`model/PRE/adapters/data2.py`), built by `data2/scripts/build_weather_station_map.py`.
- `refs/top_airports_2019.csv` — script-support provenance table consumed by
  `data2/scripts/build_weather_station_map.py` and the Data2 probe scripts; not read by the
  production runtime.

## 3. Local directory structure

Repository-relative, configurable raw root (`configs/engineering/local.example.yaml`
`raw_roots.data2`; default `data2` via `model/common/paths.py:data_root("data2_2019")`):

```text
data2/
├── DATA_USAGE.md            # this document (versioned)
├── docs/                    # adapter spec + dataset README (versioned, historical)
├── refs/                    # small versioned lookup tables (see section 2)
├── scripts/                 # audit/build/probe utilities (versioned, not runtime)
├── raw/                     # local raw data (NOT versioned)
│   ├── bts/ontime/2019/month=*/*.csv
│   ├── bts/db1b/2019/...
│   ├── bts/t100/2019/*.csv
│   └── weather/noaa/2019/*.csv
├── _download/               # local download staging (NOT versioned)
├── logs/                    # local logs (NOT versioned)
├── manifests/               # local sha256 manifests (NOT versioned)
└── reports/                 # local generated audit reports (NOT versioned)
```

Raw files are read-only inputs. The production reader never writes into `raw/`
(`RawReadRequest.separate_roots` rejects output roots inside the raw root; see
`model/PRE/adapters/registry.py`).

## 4. Data acquisition

- No download scripts are versioned (the local `scripts/download/` directory is empty).
  `data2/scripts/*.py` are one-off audit/repair/build utilities retained for provenance
  (`data2/scripts/README.md`); they are not imported by the production runtime.
- Raw files must be obtained from the official distributors: BTS On-Time / DB1B / T-100
  (U.S. Bureau of Transportation Statistics) and NOAA ISD global-hourly weather.
- Raw data is **not** redistributed through the GitHub repository; a fresh clone contains no
  raw data. `refs/` lookup tables are small, manually maintained/derived versioned assets and
  ship with the repository.

## 5. Raw schema actually consumed by code

Columns below are the `required_columns` / `projected_columns` of the registry; readers verify
required columns per file (`RAW_SCHEMA_MISMATCH` on drift) and project only registered columns.

### BTS On-Time (`bts_ontime`)

| column | required | consumer / meaning |
|---|---|---|
| `FlightDate` | yes | service date; episode split (`D2-TEMPORAL-SPLIT`), schedule day |
| `Reporting_Airline` | yes | flight identity (`flight_id` composite), provenance |
| `Tail_Number` | yes | aircraft identity (`aircraft_id`, namespace `REGISTRATION`); episode chains |
| `Flight_Number_Reporting_Airline` | yes | flight identity composite |
| `Origin`, `Dest` | yes | airports; episode continuity; timezone lookup |
| `CRSDepTime`, `CRSArrTime` | yes | scheduled reference (local HHMM), not SOBT; episode turnaround-window anchors |
| `DepTime`, `ArrTime`, `WheelsOff`, `WheelsOn` | projected | realized events (post-hoc); date offset restored from delay minutes |
| `TaxiOut`, `TaxiIn` | projected | taxi durations; wheels reconstruction; `T_TX` label; taxi reference |
| `DepDelayMinutes`, `ArrDelayMinutes` | projected | date-offset restoration of actual times (evaluation-only semantics) |
| `Cancelled`, `Diverted` | projected | completeness flags of realized outcomes |

### BTS DB1B coupon (`bts_db1b`)

`Passengers` (required; passenger proxy, 10% sample scaled x10), `Origin`, `Dest` (required;
route join key), `ItinID`, `MktID`, `MktFare` (projected; not canonicalized).

### BTS T-100 segment (`bts_t100`)

`PASSENGERS`, `SEATS` (required), `AIRCRAFT_TYPE`, `ORIGIN`, `DEST`, `YEAR`, `MONTH` (projected).
`AIRCRAFT_TYPE` is carried but marked `UNVERIFIED` (`D2-T100` is `DEVELOPMENT_FROZEN`,
confidence LOW, `semantic_status: AIRCRAFT_TYPE_UNVERIFIED`).

### NOAA ISD global-hourly (`noaa_isd`)

`STATION`, `DATE`, `WND`, `CIG`, `VIS`, `TMP`, `DEW` (required); `REPORT_TYPE`, `CALL_SIGN`,
`SLP`, `REM` (projected). ISD coded fields are decoded in `canonicalize_isd_row`; the embedded
official METAR text (`REM`) is used for altimeter (QNH) and cloud layers. Station ids are
zero-padded (WBAN) and must exist in `refs/weather_station_map.csv`
(`WEATHER_STATION_UNMAPPED` otherwise).

### Timezone reference (`timezone_reference`) / airport reference (`airport_reference`)

`iata`, `ident`, `timezone` (timezone table) and `ident`, `iata_code`, `latitude_deg`,
`longitude_deg` (airport registry; plus `elevation_ft`, `type`) — used for local-HHMM-to-UTC
conversion and airport identity, respectively.

## 6. Why columns are used (joins / ordering / tie-breaks)

- `Origin`/`Dest` + `iata` -> `refs/us_airport_timezones.csv` for every scheduled/actual
  HHMM-to-UTC conversion (`UNKNOWN_AIRPORT_TIMEZONE` on unknown airport).
- `STATION` -> `refs/weather_station_map.csv` for weather airport assignment.
- `Tail_Number` groups same-aircraft chains; `FlightDate`, `Origin`, `Dest`,
  `Flight_Number_Reporting_Airline`, `Reporting_Airline` form the deterministic `flight_id`.
- `CRSDepTime`/`CRSArrTime` anchor the CRS turnaround window `[pred.CRSArr, succ.CRSDep]` used
  for episode eligibility; `DepTime`/`ArrTime` anchor the direct gate gap
  (`D2-CHAIN-GATE-GAP`, `D2-TURNAROUND-REFERENCE`).
- `FlightDate` of the successor drives the temporal split (`D2-TEMPORAL-SPLIT`).
- BTS delay minutes are used only to restore the calendar-date offset of typed actual
  timestamps (`ACTUAL_*_DATE_OFFSET_FROM_DELAY_MINUTES` quality flags); they are evaluation-only.

## 7. Derived variables and lineage

| published variable | parent/raw columns | transformation | time rule | missing / fallback | support / evidence | consumers |
|---|---|---|---|---|---|---|
| `schedule_reference` (FlightRecord) | `CRSDepTime`, `CRSArrTime` + timezone | `local_hhmm_to_utc`, rollover inference | `SCHEDULE_REFERENCE_ASSUMPTION`; semantics = CRS departure, **not** SOBT | explicit missing; no fallback | EMPIRICAL_REFERENCE / ceiling EMPIRICAL_REFERENCE; `D2-BTS-SCHEDULE` | PRE, M1, M2 |
| `realized_operational_event` (OperationalEventRecord) | `DepTime/ArrTime/WheelsOff/WheelsOn/TaxiOut/TaxiIn/DepDelayMinutes/ArrDelayMinutes/Cancelled/Diverted` | local actual -> UTC with delay-minute date offset; wheels from taxi | `POSTHOC_ONLY`; never inference evidence | explicit cancelled; no fallback | DIRECT / DIRECT; `D2-BTS-ACTUAL` | EVALUATION_ONLY |
| `R_IB` label | `ArrTime` (pred), decision time | `max(0, pred.actual_arrival - decision_time)`, cap 360 | post-hoc | explicit | DIRECT; `D2-LABEL-R-IB` | M1 |
| `R_OB` label | `DepTime`, `CRSDepTime` (succ) | `max(0, succ.actual_departure - succ.CRS_departure)`, cap 180 | post-hoc | explicit | DIRECT; `D2-LABEL-R-OB` | M1 |
| `T_TX` label | `TaxiOut` (succ) | preserved minutes, cap 60 | post-hoc | explicit | DIRECT; `D2-LABEL-T-TX` | M1 |
| `M1 training coverage` | all rolling-grid decision nodes | stage-gated, node-equal weight | post-hoc | explicit | DERIVED, ceiling DIRECT; `D2-M1-TRAINING-COVERAGE` | M1 |
| `dataset_partition` | `FlightDate` (successor service date) | temporal split: train <= 2019-06-30, calibration <= 2019-07-31, development <= 2019-09-30, else test (`model/M1/target_builder.py:split_for_date`) | post-hoc | explicit | DERIVED; `D2-TEMPORAL-SPLIT` | M1, M2, M3 |
| `passenger_reference` (AggregateReference) | DB1B `Passengers`, `Origin`, `Dest` | quarter coupon sum x10, route-frozen (H1 variant too) | `REFERENCE_PERIOD` | explicit; no fallback | DOMAIN_PROXY; `D2-PASSENGER-REFERENCE`, `D2-PASSENGER-REFERENCE-H1` | PRE, M1, M2 |
| `segment_reference` (AggregateReference) | T-100 `PASSENGERS`, `SEATS`, `AIRCRAFT_TYPE` | preserve month grain; service-class variant `D2-T100-CLASS` | `REFERENCE_PERIOD` | explicit | DOMAIN_PROXY; DEVELOPMENT_FROZEN; aircraft type UNVERIFIED; `D2-T100`, `D2-T100-CLASS` | M2, M3, EVALUATION_ONLY |
| `taxi_reference` | `TaxiOut` (train partition) | official taxi-out median, train-frozen | post-hoc fit, FROZEN_REFERENCE at use | cell -> global, min cell 50; zero coverage ABSTAIN | DIRECT / DIRECT; `DATA2_TAXI_REFERENCE@1.0.0` (D2-4) | PRE, M1, M2 |
| `turnaround_reference` | `DepTime`, `ArrTime` (train partition) | direct gate turnaround median, train-frozen | post-hoc fit | cell -> global, min cell 50 | DIRECT; `DATA2_TURNAROUND_REFERENCE@1.0.0` | PRE, M1, M2 |
| `expected_downstream_exposure` | `CRSDepTime`, `CRSArrTime`, `Tail_Number`, `Origin`, `Dest` | scheduled legs within 360-min horizon, train-frozen | schedule-reference assumption | cell -> global, min cell 50; zero coverage ABSTAIN | DERIVED; `DATA2_DOWNSTREAM_EXPOSURE@1.0.0` | PRE, M1, M2 |
| `current_weather` (WeatherObservation) | NOAA ISD `TMP/DEW/WND/VIS/CIG` + `REM` METAR text | ISD coded fields -> canonical units; QNH from altimeter in REM; clouds from METAR text | `REPLAY_EVENT_TIME`, replay lag 5 min (`data2_weather_replay_lag_minutes`, DEVELOPMENT_FROZEN, D2-6), max age 60 min | explicit; no fallback | DIRECT / DIRECT; `D2-NOAA-ISD` | PRE, M1 |

## 8. Decision-time admissibility

- Canonical records carry `availability_basis` and `availability_time`; formal inputs require
  `availability_time <= information_cutoff` (cutoff = decision time).
- `POSTHOC_ONLY` records (actuals, labels, evaluation outcomes) are rejected as inference
  evidence by contract (`model/common/value_objects.py:TimeContext`); they are realization /
  evaluation material only.
- `SCHEDULE_REFERENCE_ASSUMPTION` is a reference assumption, not an observed availability
  (CRS times are published as reference, never as real-time facts).
- Weather uses replay availability (event time + 5 min for Data2) and the frozen max age of
  60 minutes (`weather_max_age_minutes`); stale weather abstains — no fallback.
- Selection is `latest_legal`: legal by `availability_time <= cutoff`, then latest time, then
  lowest priority, then deterministic `record_id`; equal-priority conflicts raise
  `EQUAL_PRIORITY_CONFLICT` instead of silently choosing
  (`model/PRE/evidence/admissibility.py`).
- `missing`, `unsupported`, `zero`, and `false` are distinct semantics; missing/unsupported
  publish `ABSTAIN` with a `reason_code`, never a fabricated value.

## 9. Time rules

- All canonical timestamps are timezone-aware UTC (contract validator rejects naive times).
- Local HHMM fields are converted with the airport timezone reference
  (`model/PRE/canonical/timezone.py`): `2400` -> next day `00:00`, rollover added when the
  candidate is more than 12 hours before its reference (`infer_rollover`), DST handled by IANA
  zones (`ZoneInfo`).
- BTS `*Time` fields are local airport time (origin timezone for departure-side fields, dest
  timezone for arrival-side fields); the calendar-date offset of `DepTime`/`ArrTime` is restored
  from `DepDelayMinutes`/`ArrDelayMinutes`.
- Decision nodes are a fixed 5-minute rolling grid (`roll_minutes = 5`, FROZEN): decision times
  `t_n = t_0 + 5n` from episode start through episode end; `information_cutoff = decision_time`
  (`model/PRE/episode/node_builder.py`).
- Operational stages: `PRE_IB`, `POST_IB_PRE_OB`, `POST_OB_PRE_TO`, `COMPLETED`, computed from
  predecessor in-block (actual arrival), successor off-block (actual departure), and successor
  takeoff (wheels-off) (`stage_at`).

## 10. Episode / predecessor-successor construction

Rule `DATA2_SAME_AIRCRAFT_AIRPORT_GAP@1.0.0` (`model/PRE/episode/builder.py`):

- Group: `(dataset_instance_id, aircraft_id_namespace=REGISTRATION, aircraft_id=Tail_Number)`.
- Order: `actual_departure_utc`, `actual_arrival_utc`, `flight_id`; window = adjacent rows.
- Continuity: same aircraft AND `predecessor.destination_airport_id == successor.origin_airport_id`.
- Gap: `successor.actual_departure_utc - predecessor.actual_arrival_utc` in minutes, must be
  positive and `<= max_gap_minutes = 360` (`D2-CHAIN-GATE-GAP`).
- Episode anchors: CRS turnaround window `[pred.CRSArr, succ.CRSDep]` (UTC); pairs with an
  inverted (<= 0) schedule turnaround window are excluded (D2-2 option B); labels keep DIRECT
  actuals.
- Rejections: aircraft mismatch, dataset mismatch, airport discontinuity, non-positive time
  order, gap > 360, duplicate ordering keys -> pair excluded with an explicit error path.
- Decision nodes are built on the 5-minute grid over each episode; stage gating follows
  section 9.

## 11. Evidence / support / quality states

- `EvidenceClass` rank (weakest accepted): `DIRECT < DERIVED < DOMAIN_PROXY ==
  EMPIRICAL_REFERENCE == EXTERNAL_STANDARD < SCENARIO_PARAMETER < UNSUPPORTED`
  (`model/common/enums.py`); transformations cannot upgrade evidence (`SUPPORT_UPGRADE_FORBIDDEN`).
- `SupportState`: `SUPPORTED` / `DEGRADED` / `ABSTAIN`; `ABSTAIN` requires a null value and a
  `reason_code`; `DEGRADED` requires a `reason_code` (`SupportedValue` validator).
- Freeze states: `FROZEN`, `DEVELOPMENT_FROZEN`, `UNSUPPORTED`. Missing frozen parameters
  (e.g. replay lag) block with `REPLAY_LAG_NOT_FROZEN`; there is no silent default.
- Dataset capabilities (`registries/dataset_capabilities.yaml`): `realized_events` =
  POSTHOC_DIRECT; `weather` = NOAA_ISD_DIRECT (formal + realized DIRECT); `trajectory` =
  UNSUPPORTED (`NO_TRAJECTORY`); schedule = EMPIRICAL_REFERENCE (formal) / DIRECT (realized
  outcome support per `scientific_variables.yaml`).
- Data2 adapter capability flags (`model/PRE/adapters/data2.py`): `realized_events:
  POSTHOC_DIRECT`, `passenger_reference: AGGREGATE_PROXY`, `aircraft_type: UNVERIFIED`,
  `realtime_state: UNSUPPORTED`, `weather: NOAA_ISD_DIRECT`.

## 12. PRE adapter boundary

```text
BTS/NOAA raw  ->  Data2Adapter (model/PRE/adapters/data2.py) + D2 registry rules
              ->  canonical contracts (model/PRE/contracts/canonical.py)
              ->  RegistryPREMapper -> PREState (model/PRE/mapping.py, pipeline.py)
              ->  M1-M4 (dataset-independent)
```

- Dataset-specific logic is confined to `model/PRE/adapters/data2.py`, the `D2-*` registry
  entries, and `data2/refs/` tables.
- M1–M4 consume canonical objects and scientific variables only; BTS field names never leak
  into PRE publication (`tests/contract/test_dataset_independence.py`,
  `tests/contract/test_data2_adapter_interface.py`).
- Known boundary caveat: `model/M1/target_builder.py:build_data2_target_labels` and
  `split_for_date` are Data2-specific label/temporal-split logic inside M1. It is the only
  dataset-specific dependency found in M1-M4 and is reported as an adapter-boundary issue
  (no refactor performed in this pass).

## 13. Common PRE publication interface (Data2)

| scientific variable | pre family | status (Data2) | formal / realized |
|---|---|---|---|
| `predecessor_motion` | predecessor_state | UNSUPPORTED (`NO_TRAJECTORY`) | — |
| `current_weather` | current_state | SUPPORTED | DIRECT / DIRECT |
| `schedule_reference` | successor_state | SUPPORTED | EMPIRICAL_REFERENCE / DIRECT |
| `passenger_reference` | reference_state | SUPPORTED | DOMAIN_PROXY / UNSUPPORTED (`NOT_FLIGHT_LEVEL`) |
| `segment_reference` | reference_state | SUPPORTED (DEVELOPMENT_FROZEN) | DOMAIN_PROXY / UNSUPPORTED (aggregate only) |
| `airport_reference` | reference_state | SUPPORTED | EXTERNAL_STANDARD / UNSUPPORTED (static) |
| `airport_timezone` | reference_state | SUPPORTED | EXTERNAL_STANDARD / UNSUPPORTED (static) |
| `realized_operational_event` | realized_outcome | DERIVED-to-DIRECT (post-hoc, evaluation-only) | UNSUPPORTED formal / DIRECT realized |
| `R_IB` target | — | SUPPORTED | DERIVED / DERIVED |
| `R_OB` target | — | SUPPORTED | DIRECT / DIRECT |
| `T_TX` target | — | SUPPORTED | DERIVED / DERIVED |

---

## Corrections vs. legacy documents

- `data2/docs/DATA2_README.md` previously framed Data2 as an "operational benchmark / portability
  validation" secondary to Data1 and stated weather was a "future adapter". Current code defines
  Data2 as the primary experimental dataset and implements NOAA ISD weather (`D2-NOAA-ISD`).
  This document supersedes those statements.
- `data2/docs/BTS_ADAPTER_SPEC.md` references the legacy `src/airslot/...` layout and
  `AIR_CHAIN_CORE_V2` naming; the current implementation lives under `model/PRE/...` and the
  registry-driven contract above. The spec is retained as a design record; this document is the
  implementation-grounded entry point.
- Row counts and other run-derived figures in the legacy docs are not repeated here; this
  document contains no experiment results.
