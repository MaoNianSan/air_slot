# M1-M2 V2 Context Wiring Report

Date: 2026-08-06

```text
CONTEXT_BUILDER_IMPLEMENTED = YES
PRE_TO_M2_CONTEXT_WIRING = PARTIAL
PRE_FORMAL_FAST_BUNDLE_AVAILABLE = NO
VALUATION_READ_FROM_PRE = NO
ACTION_FIELDS_READ_BY_CONTEXT_BUILDER = NO
```

| M2 field | PRE source | Transform | Direction | Evidence level | Formal? |
|---|---|---|---|---|---|
| `successor_sobt` | M1 operational reference sourced from PRE episode | none | NON_DIRECTIONAL | official or unsupported | YES if official reference active |
| `turnaround_reference_minutes` | M1 official floor; otherwise PRE train-only minimum/typical turnaround | official passthrough or empirical proxy | NON_DIRECTIONAL | official / supported proxy | conditional |
| `continuity_exposure` | optional PRE episode field | validate `[0,1]` | LARGER_IS_HIGHER_RISK | field evidence status | NO in current required schema |
| `downstream_leg_count` | optional PRE episode field | nonnegative count | LARGER_IS_HIGHER_RISK | field evidence status | NO in current required schema |
| `execution_window_margin` | optional PRE episode field | validate `[0,1]` | LARGER_IS_LOWER_RISK | field evidence status | NO in current required schema |
| `execution_window_pressure` | execution margin | `1-margin` | LARGER_IS_HIGHER_RISK | inherited | conditional |
| `aircraft_flexibility` | optional PRE episode field | validate `[0,1]` | LARGER_IS_LOWER_RISK | field evidence status | NO in current required schema |
| `aircraft_constraint` | aircraft flexibility | `1-flexibility` | LARGER_IS_HIGHER_RISK | inherited | conditional |
| `passenger_load_proxy` | optional PRE episode field or train-only passenger reference | passthrough | NON_DIRECTIONAL | official/proxy | proxy path available; data-dependent |
| `connection_slack` | optional PRE episode field | validate `[0,1]` | LARGER_IS_LOWER_RISK | field evidence status | NO in current required schema |
| `connection_pressure` | optional field; otherwise connection slack | passthrough or `1-slack` | LARGER_IS_HIGHER_RISK | inherited | conditional |
| `rebooking_scarcity` | optional PRE episode field | validate `[0,1]` | LARGER_IS_HIGHER_RISK | field evidence status | NO in current required schema |
| `airport_flow_pressure` | optional PRE episode field; otherwise PRE flow observation plus train-only airport q90 | `clip(flow/q90,0,1)` | LARGER_IS_HIGHER_RISK | supported proxy | proxy path available; data-dependent |
| `infrastructure_flexibility` | optional PRE episode field | validate `[0,1]` | LARGER_IS_LOWER_RISK | field evidence status | NO in current required schema |
| `infrastructure_constraint` | infrastructure flexibility | `1-flexibility` | LARGER_IS_HIGHER_RISK | inherited | conditional |
| `resource_availability` | optional PRE episode field | validate `[0,1]` | LARGER_IS_LOWER_RISK | field evidence status | NO in current required schema |
| `resource_scarcity` | resource availability | `1-availability` | LARGER_IS_HIGHER_RISK | inherited | conditional |
| `ground_support_pressure` | optional PRE episode field | validate `[0,1]` | LARGER_IS_HIGHER_RISK | field evidence status | NO in current required schema |

## Provenance And Support

Every field has a `context_support` entry and a provenance record. Missing PRE fields remain `None` with `UNSUPPORTED` or `MISSING`; they are not filled with zero. Values outside `[0,1]` are rejected when no frozen normalizer exists.

PRE identity checks require matching bundle hash, contract `AIR_CHAIN_CORE_V2`, episode, query time, and information cutoff. A mismatch raises a contract error before reconstruction.

## Formality Boundary

The implementation path is complete, but current evidence is partial:

- `pre/reports/published/core_v2/PRE_CORE_V2_STATUS.json` reports contract/schema/manifest validation PASS for the implementation.
- The same file reports `formal_fast_bundle_available=false`.
- PRE Core V2 required episode columns do not include most M2 risk fields.
- Passenger and flow proxies can be constructed only when matching train-only references and observations exist.

Therefore the correct current status is `PRE_TO_M2_CONTEXT_WIRING = PARTIAL`. No unsupported field is promoted to formal.
