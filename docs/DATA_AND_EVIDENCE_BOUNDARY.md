# Data and Evidence Boundary

## Read-only environments

`data1/` and `data2/` are read-only model inputs. No cache, index, temporary
file, generated artifact, or preprocessing output may be written there.
Diagnostics belong under `artifacts/diagnostics/`, `validation/`, or test
temporary directories.

## PRE publication

`PREState` is the only downstream publication boundary. It contains typed
predecessor, current, successor, and reference objects, target support,
evidence ledger, variable lineage, decision time, and information cutoff.
Every published object carries source, support state, evidence class, and
lineage. Availability is checked before an object can be inference evidence.

| Published object | Evidence class | Meaning at a decision node |
| --- | --- | --- |
| successor schedule reference | empirical reference | schedule context only; not live retiming authority |
| turnaround reference | empirical/train-frozen reference | reference value; not current resource availability |
| taxi reference | train-frozen reference | numeric reference; not execution opportunity |
| passenger and segment references | domain proxy | aggregate exposure/context; not individual passenger facts |
| airport reference | external/static reference | static context; not current gate/stand/crew state |
| factual replay record | direct only after cutoff gate | retrospective evidence when legally available; otherwise not published |

The M3 adapter explicitly maps
`successor_state.schedule_reference` to `successor_schedule` and records the
conversion rule. It does not map aggregate references to passenger,
resource, or authority facts.

## Required-fact classifications

The current action registry has no direct contemporaneous observed boolean for
any non-baseline required action fact.

- `successor_schedule` is `DERIVED` object presence only; A21 remains
  `CONTRACT_UNDERSPECIFIED` and factual `UNKNOWN`.
- Passenger connection, itinerary, and exposure are `PROXY_ONLY`.
- Flight execution range, slot/priority opportunity, airport resources,
  aircraft inventory/compatibility, crew feasibility, and network authority
  are `UNOBSERVED`.
- A21 retiming predicates and A71/A72 contemporaneous authority are
  `UNDERSPECIFIED`; the latter are also unobserved in the current PRE data.

`OBSERVED`, `DERIVED`, `PROXY_ONLY`, `UNOBSERVED`, and `UNDERSPECIFIED` are
evidence classifications, not substitutes for action state. The adapter
preserves `TRUE`, `FALSE`, and `UNKNOWN` factual state separately.

## Evidence ceilings

Support metadata cannot be upgraded by flattening, truthiness, numerical
calculation, or model output. Unsupported values remain null with an explicit
reason. Scenario assumptions remain scenario assumptions; they can support a
conditional numerical calculation but do not become observed action effects.

## State separation

The model preserves independent `chi_inst`, `chi_fact`, `chi_num`, `chi_resp`,
`chi_opp`, and `chi_sel` states. In particular, factual UNKNOWN neither proves
nor disproves numerical definition. `chi_sel` is not authorized in the active
model.

M1 calibration uses only the frozen July 1-31, 2019 calibration split and
separate primitive-head procedures (hazard event-time NLL and hurdle zero-mass
temperature). The existing August 26 H32/CURRENT_ONLY calibration artifact is
historical superseded provenance; it is not an H8 runtime authority and is not
re-fit during model freeze.

Passenger consequences use typed Train-frozen reference objects. T-100
provides expected passengers per performed flight at a carrier-route-month
grain with explicit fallback. DB1B Coupon provides a historical continuation
share; blank `TripBreak` is only a historical continuation indicator, never a
live passenger connection fact. T-100 fitting is row-gated to 2019 months 1-6,
and DB1B fitting is restricted to Q1/Q2. `P_itinerary` uses `D_TO > 45` under a
representative itinerary-disruption reference; `P_service` uses `D_TO >= 180`
under a long-delay passenger-service reference. Neither threshold is a
universal operational or legal fact. No empirical itinerary events, service
records, airline expenditure, or actual passenger counts are claimed.

The seven active CU numeric scales are positive Train medians from the new
`passenger_reference_freeze_v4` and existing flight/resource Train references. No
data directory is scanned during model loading. Historical five-component
registries and V3 remain immutable superseded provenance. All seven components
enter `M4_RMB_BASE_MAPPING_V2`.
