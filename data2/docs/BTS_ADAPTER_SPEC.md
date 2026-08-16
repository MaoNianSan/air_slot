# BTS Adapter Specification (Data2 → AIR SLOT canonical PRE)

> Defines the mapping from BTS raw fields to AIR SLOT canonical objects for the
> `data2/` dataset (BTS 2019). This is the *only* place BTS raw-field semantics are
> interpreted. Downstream (PRE → M1 → M2 → M3 → M4) consumes canonical objects only;
> **BTS field names are never exposed downstream**.
>
> Reference: `src/airslot/adapters/bts_adapter.py` (implementation), canonical contracts in
> `src/airslot/contracts/`.

## Legend

| status | meaning |
| --- | --- |
| `DIRECT` | field maps 1:1 to the canonical value with full fidelity |
| `DIRECT_EVENT` | field maps 1:1 to an operational event timestamp, but the record is **post-operation** (not real-time available) |
| `REFERENCE` | field provides a scheduled/reference value, not an observed event |
| `UNSUPPORTED` | canonical object cannot be produced from BTS files |

Every published object carries evidence metadata:

```json
{
  "source": "BTS_ONTIME",
  "status": "DIRECT",
  "decision_time_available": false
}
```

- `source`: dataset table that produced the object (`BTS_ONTIME`).
- `status`: evidence class of the object.
- `decision_time_available`: whether the value could be known at a real-time decision node.
  All On-Time event fields are post-hoc records → `false`. Scheduled references are also
  flagged `false` for real-time availability (they are `REFERENCE`, not observed).

---

## 1. Aircraft identity

| canonical | BTS | status |
| --- | --- | --- |
| `aircraft_id` | `Tail_Number` | `DIRECT` |

The aircraft registration (tail number) is the canonical aircraft key. Missing tail
numbers (0.24% of all rows; 0.00% of completed flights in 2019) are published as
`missing=true`; the flight is excluded from aircraft-level episode chains.

## 2. Flight identity

| canonical | BTS | status |
| --- | --- | --- |
| `flight_id` | `Flight_Number_Reporting_Airline` + `FlightDate` + `Reporting_Airline` | `DIRECT` |

`flight_id` is derived as a stable composite: `{carrier}|{flight_number}|{flight_date}|{origin}|{dest}`.
`carrier` ← `Reporting_Airline` (IATA code), `flight_number` ←
`Flight_Number_Reporting_Airline`, `flight_date` ← `FlightDate` (yyyymmdd), plus
`origin`/`dest` (IATA airport codes).

## 3. Schedule reference

| canonical | BTS | status |
| --- | --- | --- |
| `scheduled_departure_reference` | `CRSDepTime` | `REFERENCE` |
| `scheduled_arrival_reference` | `CRSArrTime` | `REFERENCE` |

> **Important:** These are **scheduled reference timestamps** (CRS = Computer
> Reservation System planned times), **not** SOBT/SIBT. They are published as
> `REFERENCE` objects and must never be called SOBT/SIBT downstream.

## 4. Operational events

| canonical | BTS | status |
| --- | --- | --- |
| `observed_departure_time` | `DepTime` | `DIRECT_EVENT` |
| `observed_arrival_time` | `ArrTime` | `DIRECT_EVENT` |
| `takeoff_time` | `WheelsOff` | `DIRECT_EVENT` |
| `landing_time` | `WheelsOn` | `DIRECT_EVENT` |

> **Note:** These are **post-operation records**. They represent recorded actuals, not
> real-time available information — every event is published with
> `decision_time_available=false`.

## 5. Taxi

| canonical | BTS | status |
| --- | --- | --- |
| `taxi_out_duration` | `TaxiOut` (minutes) | `DIRECT` |
| `taxi_in_duration` | `TaxiIn` (minutes) | `DIRECT` |

Durations are published as canonical duration values with `duration_minutes`.

## 6. Trajectory

| canonical | BTS | status |
| --- | --- | --- |
| trajectory / observation sequence | — | `UNSUPPORTED` |

No ADS-B trajectory exists in BTS files. Trajectory-related variables remain
`UNSUPPORTED`; no trajectory is fabricated and no zero-fill is applied.

## 7. Evidence metadata (per published object)

Every canonical object includes:

```json
{
  "source": "BTS_ONTIME",
  "availability_status": "POST_OPERATION",
  "evidence_type": "DIRECT | DIRECT_EVENT | REFERENCE | UNSUPPORTED",
  "decision_time_available": false
}
```

| object | evidence_type | decision_time_available |
| --- | --- | --- |
| `aircraft_id`, `flight_id` | `DIRECT` | false |
| `scheduled_departure_reference`, `scheduled_arrival_reference` | `REFERENCE` | false |
| `observed_departure_time`, `observed_arrival_time`, `takeoff_time`, `landing_time` | `DIRECT_EVENT` | false |
| `taxi_out_duration`, `taxi_in_duration` | `DIRECT` | false |
| trajectory | `UNSUPPORTED` | — |

## 8. Canonical PRE record shape

```json
{
  "contract_id": "AIR_CHAIN_CORE_V2",
  "dataset": "BTS",
  "source": "BTS_ONTIME",
  "flight_identity": { "flight_id": "...", "aircraft_id": "...", "carrier": "...", "flight_number": "...", "flight_date": "...", "origin": "...", "dest": "..." },
  "schedule_references": { "scheduled_departure_reference": {...}, "scheduled_arrival_reference": {...} },
  "operational_events": { "observed_departure_time": {...}, "observed_arrival_time": {...}, "takeoff_time": {...}, "landing_time": {...}, "taxi_out_duration": {...}, "taxi_in_duration": {...} },
  "evidence": { "<object>": {"source": "BTS_ONTIME", "availability_status": "POST_OPERATION", "evidence_type": "...", "decision_time_available": false} },
  "trajectory": "UNSUPPORTED",
  "timezone_status": "CONFIRMED | UNKNOWN"
}
```

## 9. Compatibility contract

- Same canonical objects as Data1 (OpenSky) for: `aircraft_id`, schedule references,
  operational events, taxi durations.
- Data1 trajectory = `DIRECT` (state vectors); Data2 trajectory = `UNSUPPORTED` (masked).
- After this adapter, PRE and M1–M4 consume the identical canonical contract; no module
  knows the dataset identity.
