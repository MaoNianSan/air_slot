# DATA2 — BTS 2019 Dataset & Adapter

> DATA2 is the BTS (Bureau of Transportation Statistics) 2019 dataset used as an
> **operational benchmark and portability validation** for the AIR SLOT framework.

## Dataset purpose

**Data2 is not replacing Data1.**

| aspect | Data1 (OpenSky) | Data2 (BTS) |
| --- | --- | --- |
| role | primary scenario | operational benchmark / portability validation |
| source | OpenSky state vectors + METAR + Eurostat | BTS On-Time, DB1B, T-100 |
| trajectory | direct (state vectors) | **unsupported** (none exists) |
| observation | partial / real-time | complete post-hoc event records |
| scenario | European (19 target airports) | **US domestic** (flight-level tables) |
| aircraft id | `icao24` | `Tail_Number` |

## What is in DATA2

| table | year | rows | key content | status |
| --- | ---: | ---: | --- | --- |
| BTS On-Time | 2019 (12 months) | 7,422,037 | gate departure/arrival, wheels off/on, taxi, schedule ref | **DIRECT** events |
| BTS DB1B Coupon | 2019 (4 quarters) | 43,259,853 | itinerary segments, passengers (10% sample) | proxy |
| BTS DB1B Market | 2019 (4 quarters) | 28,535,894 | itinerary markets, fares (10% sample) | proxy |
| BTS T-100 Segment | 2019 (full year) | 487,923 | passenger/seat/freight per segment (all carriers) | proxy |

## Adapter

- Spec: [`BTS_ADAPTER_SPEC.md`](BTS_ADAPTER_SPEC.md)
- Implementation: `src/airslot/adapters/bts_adapter.py`
- Pipeline: `BTS raw → DATA2 Adapter → AIR_CHAIN_CORE_V2 (canonical PRE) → PRE/M1`

The adapter is the **only** place BTS raw-field semantics are interpreted; after the
adapter, PRE/M1/M2/M3/M4 consume the identical canonical contract as Data1.

## Limitations (explicit)

Unsupported in DATA2:

- **trajectory** — no ADS-B state-vector trajectory; `UNSUPPORTED` (never fabricated, no zero-fill)
- **real-time ADS-B state** — On-Time fields are post-operation records (`decision_time_available=false`)
- **crew** — no crew/roster data
- **gate resources** — no gate/stand/equipment data
- **weather** — future adapter (BTS files carry no weather; METAR linkage from Data1 planned)

Additional caveats:

- On-Time / DB1B are **100% US domestic**; the 19 European target airports of Data1
  are **not covered** by the flight-level tables (only T-100 touches them, at aggregate
  segment level).
- DB1B is a **10% ticket sample** — passenger-volume proxies must be scaled by ~10×.
- DB1B placeholder carrier codes (`--`, `99`) must be cleaned before market joins.
- Complete US airport timezone reference ships in `refs/us_airport_timezones.csv`
  (generated from OurAirports coordinates); used by the adapter when the built-in
  state-based reference cannot resolve an airport.

## Reports (in `reports/`)

- `data2_directory_inventory.md` — Phase 1 inventory
- `data2_phase2_field_profiling.md` — Phase 2 field profiling & framework feasibility
- `data2_structure_fix_report.md` — Phase 3 structure fix (T-100 relocation)
- `bts_pre_contract_test.md` — PRE contract compatibility test
- `bts_m1_interface_test.md` — M1 interface smoke test
