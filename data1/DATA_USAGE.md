# DATA1 — Dataset Usage and Contract

**Document status**: current and code-grounded (audited 2026-08-16).
**Dataset instance**: `data1_2019`
**Authoritative evidence**: `registries/source_adapter_registry.yaml`, `registries/data_usage_rules.yaml`,
`registries/scientific_variables.yaml`, `registries/dataset_capabilities.yaml`,
`model/PRE/adapters/data1.py`, `model/PRE/canonical/normalization.py`, `model/PRE/episode/builder.py`,
`model/PRE/episode/node_builder.py`, `model/PRE/evidence/admissibility.py`,
`model/PRE/reference/taxi.py`, `model/PRE/reference/turnaround.py`, `model/PRE/reference/exposure.py`,
`configs/scientific/foundation.yaml`, contract/unit tests under `tests/`.
Historical experiment outputs, manifests, and run artifacts are **not** evidence for this document.

---

## 1. Dataset role

Data1 (`data1_2019`) is the **trajectory-rich applicability dataset** of the current Air Slot
implementation: it demonstrates how the PRE adapter boundary and the dataset-independent
M1–M4 chain behave under a different observation structure (ADS-B trajectory + archive flight
intervals + METAR weather + monthly aggregates), **not** the primary experimental dataset.

- Primary experimental dataset is Data2 (`data2_2019`) — the only instance with M1
  training-label rules and an M1 training-coverage code path (see `data2/DATA_USAGE.md`).
- Data1 has no registered M1 training-label rules in `registries/data_usage_rules.yaml`; its
  realized outcomes are proxy events (`DERIVED`, evaluation-only).
- Dataset profile: `TRAJECTORY_RICH_ROLLING_INSTANCE`
  (`registries/dataset_capabilities.yaml`): trajectory = DIRECT, schedule = UNSUPPORTED
  (`NO_TRUE_SCHEDULE`), action-response history = UNSUPPORTED (`NO_ACTION_LOG`).

## 2. Raw data sources

Only sources registered in `registries/source_adapter_registry.yaml` for `data1_2019` are consumed:

| adapter | source family | registered layout (relative to raw root) | format | canonical object(s) |
|---|---|---|---|---|
| `D1-FLIGHTLIST` | `opensky_flightlist` | `raw/opensky/flightlist/{year}/*.csv.gz` | csv_gzip | FlightRecord + OperationalEventRecord |
| `D1-STATE` | `opensky_state_vectors` | `raw/opensky/state_vectors/{year}/date=*/hour=*/*` | csv_tar | TrajectoryObservation |
| `D1-METAR` | `iem_metar` | `raw/metar/{year}/station=*/*.csv` | csv | WeatherObservation |
| `D1-EUROSTAT` | `eurostat` | `raw/eurostat/{year}/**/*.json` | json_stat | AggregateReference |
| `D1-OURAIRPORTS` | `ourairports` | `raw/ourairports/snapshot=*/airports.csv` | csv | AirportReference |

Notes:
- The family name is `iem_metar` but the registered glob is `raw/metar/{year}/station=*/*.csv`;
  the local tree may additionally contain an unregistered `raw/iem_metar/` download area that
  production readers do not consume.
- OpenSky aircraft metadata is **not** registered (adapter capability
  `aircraft_metadata_2019: UNSUPPORTED`), even though an `aircraft_metadata/` directory may
  exist locally.
- The `{year}` template is parameterized (`RawReadRequest.year`, CLI default 2019), so local
  trees may hold multiple years; only requested years are read.

## 3. Local directory structure

Repository-relative, configurable raw root (`configs/engineering/local.example.yaml`
`raw_roots.data1`; default `data1` via `model/common/paths.py:data_root("data1_2019")`):

```text
data1/
├── DATA_USAGE.md            # this document (versioned)
├── README.md                # historical data-folder governance README (versioned, superseded in part)
├── source_docs/             # attribution / license / retrieval metadata (versioned)
├── raw/                     # local raw data (NOT versioned)
│   ├── opensky/flightlist/{year}/*.csv.gz
│   ├── opensky/state_vectors/{year}/date=*/hour=*/*.csv.tar
│   ├── metar/{year}/station=*/*.csv
│   ├── eurostat/{year}/**/*.json
│   └── ourairports/snapshot=*/airports.csv
└── _download/               # local download staging and logs (NOT versioned)
```

Raw files are read-only inputs; the production reader never writes into `raw/`
(`RawReadRequest.separate_roots` rejects output roots inside the raw root).

## 4. Data acquisition

- No download scripts are versioned in the repository; `source_docs/` records attribution,
  licenses, source notes, and retrieval metadata for each family (OpenSky, METAR/IEM, Eurostat,
  OurAirports).
- Raw files must be obtained from the official distributors (OpenSky Network, IEM ASOS/AWOS
  METAR, Eurostat JSON-stat, OurAirports snapshots) and are **not** redistributed through the
  GitHub repository; a fresh clone contains no raw data.

## 5. Raw schema actually consumed by code

Columns below are the `required_columns` / `projected_columns` of the registry; readers verify
required columns per file (`RAW_SCHEMA_MISMATCH` on drift) and project only registered columns.

### OpenSky flightlist (`opensky_flightlist`)

| column | required | consumer / meaning |
|---|---|---|
| `callsign` | yes | flight identity composite (`flight_id`), source flight id |
| `icao24` | yes | aircraft identity (`aircraft_id`, namespace `ICAO24`); episode chains |
| `origin`, `destination` | yes | airports; episode continuity |
| `firstseen`, `lastseen` | yes | archive observation interval [UTC]; episode identity and proxy event bounds |
| `number`, `registration`, `typecode`, `day` | projected | carried by projection; **no canonical consumer** (aircraft metadata unsupported) |

### OpenSky state vectors (`opensky_state_vectors`)

| column | required | consumer / meaning |
|---|---|---|
| `time` | yes | observation event time (unix epoch -> UTC) |
| `icao24` | yes | aircraft identity |
| `lat`, `lon` | yes | position (degrees) |
| `velocity` | yes | ground speed (m/s) |
| `onground` | yes | on-ground flag |
| `heading`, `vertrate`, `baroaltitude`, `geoaltitude`, `lastposupdate`, `lastcontact`, `callsign` | projected | canonicalized where non-missing (`heading_deg`, `vertical_rate_mps`, `baro_altitude_m`, `geo_altitude_m`, `position_time`, `contact_time`) |

### METAR (IEM, `iem_metar`)

`station`, `valid`, `tmpf`, `sknt`, `metar` (required); `dwpf`, `drct`, `gust`, `mslp`, `vsby`,
`skyc1..3`, `skyl1..3`, `wxcodes` (projected). Consumers: `WeatherObservation`
(`temperature_c`, `dewpoint_c`, `wind_direction_deg`, `wind_speed_mps`, `wind_gust_mps`,
`visibility_m`, cloud layers, ceiling, present weather). `mslp` is projected but **not**
canonicalized: `mslp_hpa` is always `None` and QNH is parsed from the METAR text
(capability `qnh_mslp: QNH_NOT_MSLP`).

### Eurostat (`eurostat`, JSON-stat)

`class`, `value`, `dimension` (required; `id`, `size` also used). Consumer:
`AggregateReference` `passenger_reference` (`D1-EUROSTAT`): `avia_paoa` passengers cube,
freq M, unit PAS, `PAS_BRD`, schedule TOT, traffic coverage TOTAL — grain airport x month.
Sparse absent cells are **not** materialized (never zero-fabricated); explicit zeros are
preserved.

### OurAirports (`ourairports`)

`ident`, `iata_code`, `latitude_deg`, `longitude_deg` (required); `elevation_ft`, `type`
(projected). Consumer: `AirportReference` (airport identity namespace mapping; feet -> meters).

## 6. Why columns are used (joins / ordering / tie-breaks)

- `icao24` groups same-aircraft chains; `firstseen`/`lastseen` provide the archive interval
  that anchors episode ordering and gap computation (`D1-OPENSKY-FLIGHT`).
- `origin`/`destination` enforce airport continuity between predecessor and successor.
- `station` (METAR) links weather to airports; `valid` is the event time; the raw METAR text is
  the only QNH source.
- Eurostat `rep_airp`/`time` dimensions select the airport-month slice; OurAirports `ident` is
  the airport namespace.
- These are pipeline-critical even though they are not model features
  (join/order/temporal-continuity/provenance roles).

## 7. Derived variables and lineage

| published variable | parent/raw columns | transformation | time rule | missing / fallback | support / evidence | consumers |
|---|---|---|---|---|---|---|
| episode identity (FlightRecord) | `callsign`, `day`, `origin`, `destination`, `icao24`, `firstseen`, `lastseen` | deterministic `flight_id`; archive interval `[first_seen, last_seen]` | `ARCHIVE_PUBLICATION_RULE` (archive interval, **not** real-time) | explicit | DERIVED / DERIVED; `D1-OPENSKY-FLIGHT` | PRE (episode construction) |
| `predecessor_motion` (TrajectoryObservation) | `time`, `icao24`, `lat`, `lon`, `velocity`, `onground` (+ heading/vertrate/altitudes) | epoch -> UTC; units preserved (m/s, degrees) | `REPLAY_EVENT_TIME`; availability = event time + replay lag | explicit (missing -> None) | DIRECT / DIRECT; `D1-OPENSKY-STATE` | PRE, M1 |
| trajectory events (OperationalEventRecord) | state-vector sequence | motion-state transitions `S_OFF/S_STATIC/S_TAXI/S_AIR` (`TRAJECTORY_OPERATIONAL_EVENT_TRANSITION@1.0.0`; detector config: eps_position_deg=0.001, v_static_mps=1.0, eps_altitude_m=15, v_taxi_min_mps=5, v_air_mps=60, gap_off_minutes=10, r_airport_km=20, w_seconds=60) | `POSTHOC_ONLY` | explicit quality flags | DERIVED; `D1-TRAJECTORY-EVENT` | EVALUATION_ONLY (feeds taxi reference) |
| proxy realized event (OperationalEventRecord) | `firstseen`, `lastseen` | `ARCHIVE_FLIGHT_INTERVAL_PROXY` interval event | `POSTHOC_ONLY` | explicit | DERIVED; `D1-OPENSKY-FLIGHT-EVENT` | EVALUATION_ONLY |
| `current_weather` (WeatherObservation) | METAR `valid`, `tmpf`, `dwpf`, `drct`, `sknt`, `gust`, `vsby`, `skyc*`, `skyl*`, `metar` | F->C, knots->m/s, SM->m, hundreds ft->m; ceiling = min base of BKN/OVC/VV (`CEILING_DERIVED_MIN_BKN_OVC` / `CEILING_UNLIMITED` / masked flags); QNH from METAR text `Q(\d{4})`; `mslp_hpa` always None | `REPLAY_EVENT_TIME`; replay lag 0 min (frozen), max age 60 min | explicit; stale -> ABSTAIN; no fallback | DERIVED, ceiling DIRECT; `D1-METAR` | PRE, M1 |
| `passenger_reference` (AggregateReference) | Eurostat `value`/`dimension` | `PAS_BRD` airport-month slice; sparse cells absent, zeros preserved | `REFERENCE_PERIOD` | explicit | EMPIRICAL_REFERENCE; `D1-EUROSTAT` | PRE, M2, EVALUATION_ONLY |
| `airport_reference` (AirportReference) | OurAirports `ident`, `iata_code`, `latitude_deg`, `longitude_deg`, `elevation_ft`, `type` | namespace mapping; ft -> m | static snapshot | preserve namespace | EXTERNAL_STANDARD; `D1-OURAIRPORTS` | PRE, M1, M2, M3 |
| `taxi_reference` | trajectory events within flight interval | `TRAJECTORY_TAKEOFF - TRAJECTORY_OUT_BLOCK_PROXY` (minutes); train-frozen MEDIAN per origin airport; min cell 50; fallback cell -> global; zero coverage ABSTAIN (`NO_TAXI_TRAJECTORY_EVIDENCE`) | train partition fit, FROZEN_REFERENCE at use | explicit | EMPIRICAL_REFERENCE (DEGRADED, trajectory-pair source); `TAXI_REFERENCE@1.0.0` (D1-9) | PRE, M1, M2 |
| `turnaround_reference` | flightlist intervals (same-aircraft airport gap) | gate-gap median, train-frozen; min cell 50; fallback cell -> global | train partition fit | explicit | EMPIRICAL_REFERENCE (DEGRADED, `FLIGHTLIST_PROXY_GAP_REFERENCE`); `TURNAROUND_REFERENCE@1.0.0` (D1-8) | PRE, M1, M2 |
| `expected_downstream_exposure` | flightlist chain | downstream same-aircraft legs within 360-min horizon, train-frozen MEDIAN per connection airport; min cell 50; fallback cell -> global; zero coverage ABSTAIN | train partition fit | explicit | EMPIRICAL_REFERENCE (DEGRADED, archive chains); `EXPECTED_DOWNSTREAM_EXPOSURE@1.0.0` (D1-10) | PRE, M1, M2 |

## 8. Decision-time admissibility

- Canonical records carry `availability_basis` and `availability_time`; formal inputs require
  `availability_time <= information_cutoff` (cutoff = decision time).
- Data1 replay lag is frozen at **0 minutes** (`configs/scientific/foundation.yaml`
  `replay_lag_minutes: {FROZEN, 0}`); missing frozen values block with
  `REPLAY_LAG_NOT_FROZEN` (no silent default).
- `ARCHIVE_PUBLICATION_RULE` records (flightlist intervals) are offline archive facts, never
  real-time availability; they are used for episode construction and proxy outcomes only.
- `POSTHOC_ONLY` records (proxy events, trajectory events) are rejected as inference evidence
  by contract (`TimeContext` validator); they are evaluation/realization material only.
- Weather: latest-legal within 60 minutes (`weather_max_age_minutes`, FROZEN); stale weather
  abstains — no fallback.
- Selection is `latest_legal`: legal by `availability_time <= cutoff`, then latest time, then
  lowest priority, then deterministic `record_id`; equal-priority conflicts raise
  `EQUAL_PRIORITY_CONFLICT` instead of silently choosing.
- `missing`, `unsupported`, `zero`, and `false` are distinct semantics; missing/unsupported
  publish `ABSTAIN` with a `reason_code`, never a fabricated value.

## 9. Time rules

- All canonical timestamps are timezone-aware UTC (contract validator rejects naive times).
- State-vector `time` and flightlist `firstseen`/`lastseen` are unix epoch seconds -> UTC.
- METAR `valid` is parsed as ISO timestamp -> UTC.
- Decision nodes are a fixed 5-minute rolling grid (`roll_minutes = 5`, FROZEN): decision times
  `t_n = t_0 + 5n` from episode start through episode end; `information_cutoff = decision_time`
  (`model/PRE/episode/node_builder.py`).
- Operational stages: `PRE_IB`, `POST_IB_PRE_OB`, `POST_OB_PRE_TO`, `COMPLETED`
  (`stage_at`). Data1 canonicalized events do not populate the actual
  arrival/off-block/takeoff fields used by stage computation, so the `None` guard defaults
  stage to `PRE_IB` for Data1 nodes.

## 10. Episode / predecessor-successor construction

Rule `SAME_AIRCRAFT_AIRPORT_GAP@1.0.0` (`model/PRE/episode/builder.py`):

- Group: `(dataset_instance_id, aircraft_id_namespace=ICAO24, aircraft_id=icao24)`.
- Order: `event_start_time`, `event_end_time`, `flight_id`; window = adjacent rows;
  tie-break `event_end_time`, `flight_id`.
- Continuity: same aircraft AND `predecessor.destination_airport_id == successor.origin_airport_id`.
- Gap: `successor.event_start_time - predecessor.event_end_time` in minutes, must be positive
  and `<= max_gap_minutes = 360`.
- Anchors are the flightlist archive intervals (`FlightRecord.offline_membership_only = True`;
  `ARCHIVE_PUBLICATION_RULE`), i.e. offline episode identity, never a decision-time fact.
- Rejections: aircraft mismatch, dataset mismatch, airport discontinuity, non-positive time
  order, gap > 360, duplicate ordering keys -> pair excluded with an explicit error path.
- Decision nodes are built on the 5-minute grid over each episode.

## 11. Evidence / support / quality states

- `EvidenceClass` rank (weakest accepted): `DIRECT < DERIVED < DOMAIN_PROXY ==
  EMPIRICAL_REFERENCE == EXTERNAL_STANDARD < SCENARIO_PARAMETER < UNSUPPORTED`
  (`model/common/enums.py`); transformations cannot upgrade evidence (`SUPPORT_UPGRADE_FORBIDDEN`).
- `SupportState`: `SUPPORTED` / `DEGRADED` / `ABSTAIN`; `ABSTAIN` requires a null value and a
  `reason_code`; `DEGRADED` requires a `reason_code`.
- Freeze states: `FROZEN`, `DEVELOPMENT_FROZEN`, `UNSUPPORTED`; no silent fallback for frozen
  parameters.
- Data1 capabilities (`registries/dataset_capabilities.yaml`): trajectory DIRECT (formal
  DIRECT); schedule UNSUPPORTED (`NO_TRUE_SCHEDULE`); action-response history UNSUPPORTED
  (`NO_ACTION_LOG`).
- Adapter capability flags (`model/PRE/adapters/data1.py`): `qnh_mslp: QNH_NOT_MSLP`,
  `schedule: UNSUPPORTED`, `aircraft_metadata_2019: UNSUPPORTED`,
  `passenger_reference: EMPIRICAL_REFERENCE`.

## 12. PRE adapter boundary

```text
OpenSky/METAR/Eurostat/OurAirports raw -> Data1Adapter (model/PRE/adapters/data1.py) + D1 registry rules
                                       -> canonical contracts (model/PRE/contracts/canonical.py)
                                       -> RegistryPREMapper -> PREState (model/PRE/mapping.py, pipeline.py)
                                       -> M1-M4 (dataset-independent)
```

- Dataset-specific logic is confined to `model/PRE/adapters/data1.py` and the `D1-*` registry
  entries; the same canonical contracts and scientific variables are published for Data2.
- M1–M4 consume canonical objects and scientific variables only; no Data1-specific raw column
  leaks into PRE publication (`tests/contract/test_dataset_independence.py`,
  `tests/contract/test_data1_adapter_interface.py`).
- Known boundary caveat (shared with Data2): the only dataset-specific dependency found in
  M1–M4 is `model/M1/target_builder.py` (Data2 labels/temporal split); Data1 has no M1 label
  path. Reported as an adapter-boundary issue; no refactor performed in this pass.

## 13. Common PRE publication interface (Data1)

| scientific variable | pre family | status (Data1) | formal / realized |
|---|---|---|---|
| `predecessor_motion` | predecessor_state | SUPPORTED | DIRECT / DERIVED |
| `current_weather` | current_state | SUPPORTED | DERIVED / DERIVED |
| `schedule_reference` | successor_state | UNSUPPORTED (`NO_SCHEDULE`) | — |
| `passenger_reference` | reference_state | SUPPORTED | EMPIRICAL_REFERENCE / UNSUPPORTED (`NOT_FLIGHT_LEVEL`) |
| `segment_reference` | reference_state | UNSUPPORTED (`NO_T100`) | — |
| `airport_reference` | reference_state | SUPPORTED | EXTERNAL_STANDARD / UNSUPPORTED (static) |
| `airport_timezone` | reference_state | UNSUPPORTED (`NOT_REQUIRED_IN_FOUNDATION`) | — |
| `realized_operational_event` | realized_outcome | DERIVED proxy (post-hoc, evaluation-only) | UNSUPPORTED formal / DERIVED realized |
| `R_IB` target | — | SUPPORTED | DERIVED / DERIVED |
| `R_OB` target | — | ABSTAIN (`TARGET_SEMANTICS_UNSUPPORTED`: no schedule) | — |
| `T_TX` target | — | SUPPORTED | DERIVED / DERIVED |

---

## Corrections vs. legacy documents

- `data1/README.md` (inherited from the old `data/` layout) describes a 2022-only raw tree
  (`opensky/flightlist/2022`, `state_vectors/2022`, 562 `.csv.tar` inventory) and a `pre/`
  processing boundary. The current implementation registers `data1_2019` layouts with
  year-parameterized globs (CLI default 2019), reads METAR at `raw/metar/{year}/station=*/`,
  and places processing in `model/PRE/...`. Conflicting statements in that README are
  superseded by this document; the README is retained as a historical governance record.
- Row counts, file counts, and coverage-gap figures from older manifests are not repeated here;
  this document contains no experiment results.
