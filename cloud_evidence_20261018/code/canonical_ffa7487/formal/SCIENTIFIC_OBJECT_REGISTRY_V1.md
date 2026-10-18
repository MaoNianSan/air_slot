# Air Slot Scientific Object Registry V1

Status: `SCIENTIFIC_MAINTENANCE_DOCUMENTATION_ONLY`

This registry records the scientific-object boundaries confirmed in Phase B2.
It is explanatory only. It does not replace a typed contract, modify a formula,
authorize an experiment, or change any frozen result.

## Scope And Authority

- The current code authority is the typed implementation and its active
  registries at the audited repository head.
- Final Test numerical authority remains the executed artifact set recorded in
  `formal/FINAL_TEST_PROVENANCE_RECONCILIATION_V1.json`.
- Historical V1 artifacts and compatibility readers remain provenance evidence;
  they are not a second principal M1 implementation.
- Fixture-only PRE construction is not a production flight-chain builder.

## Flight-Chain State

The production information-state authority is `model/PRE/contracts/pre_state.py`
(`PREState`) published by `model/PRE/pipeline.py`
(`ProductionPREPublisher`). The operating stage is assigned only by
`model/PRE/episode/node_builder.py:stage_at`:

| Internal code | Paper-facing label | Meaning at decision time |
| --- | --- | --- |
| `PRE_IB` | Pre-in-block | Predecessor in-block, successor off-block, and successor take-off are unresolved. |
| `POST_IB_PRE_OB` | Post-in-block / pre-off-block | Predecessor in-block is realized; successor off-block and take-off remain unresolved. |
| `POST_OB_PRE_TO` | Post-off-block / pre-take-off | Successor off-block is realized; taxi and take-off remain unresolved. |
| `COMPLETED` | Completed | Successor take-off is realized. |

At an observed milestone time, that event is factual rather than unresolved.
The paper labels are a documented translation, not interchangeable enum values
and not a second stage-assignment implementation.

Exp1's `ScenarioState`, `JointRepresentation`, `PointRepresentation`, and
`MarginalRepresentation` are evaluation representations. They do not compete
with the production PRE publisher as flight-chain authority.

## M1 Target And Alias Registry

The principal target semantics are defined by
`model/M1/semantics.py:M1_V2_TARGET_SEMANTICS`. The following names must not be
substituted for one another merely because each concerns predecessor in-block
or successor timing.

| Name | Role | Representation and unit | Translation rule |
| --- | --- | --- | --- |
| `T_IB_REMAINING_HAZARD` | Internal V2 hazard coordinate | Remaining predecessor in-block time in minutes from decision time | For an unresolved draw, `T_IB_A00 = decision_time + coordinate`. |
| `T_IB_A00` | V2 scientific primitive | Absolute predecessor in-block event time, ISO UTC | Stored in typed scenarios as `t_ib_a00_utc`. |
| `R_IB` | V2 formal derived quantity and paper-facing empirical hazard quantity | Nonnegative remaining minutes | `max(0, T_IB_A00 - decision_time)`. It is never a separately trained head. |
| `D_OB` | V2 scientific primitive | Nonnegative successor off-block delay in minutes | V2 hurdle plus positive conditional quantile output. |
| `D_TX` | V2 scientific primitive | Nonnegative excess taxi delay in minutes | Derived relative to the train-frozen taxi reference during label construction; modeled as the V2 successor taxi head. |
| `D_TO` | V2 formal derived quantity | Nonnegative successor take-off delay in minutes | `D_OB + D_TX` for each aligned scenario. |
| `DELTA_OB` | Legacy V1 / label-construction auxiliary | Signed successor off-block offset | Not a V2 formal stochastic parent. |
| `T_TX` | Legacy V1 / label-construction auxiliary | Raw taxi-out duration in minutes | Not `D_TX`; `D_TX` is excess relative to reference. |
| `T_OB` | Legacy derived event time | Successor off-block event time | Not `D_OB`; it is scheduled departure plus signed `DELTA_OB`. |

`model/M1/pipeline.py:V1_TO_V2_SUPPORT` is a support-name compatibility map,
not a numerical identity or unit conversion. The V2 principal sampling path
rejects a V1 principal model. Final Test scenario tables intentionally expose
`R_IB`, `D_OB`, `D_TX`, and `D_TO`; Exp1 maps `R_IB` to the internal hazard
coordinate only for target evaluation.

## Consequence Components And Normalization

`model/M2/consequences/engine.py:native_quantities` is the scenario-level
authority for the seven native components. `model/common/native_formulas.py`
provides shared passenger arithmetic. Active CU conversion is
`model/common/cu_normalization.py:to_cu`, using the V4 registry loaded by
`model/M2/scientific_registry.py:load_active_m2_cu_registry`.

| Native component | Definition source quantity |
| --- | --- |
| `F_continuity` | `max(0, R_IB - turnaround reference)` |
| `F_execution` | `D_OB` |
| `F_propagation` | `D_TO * expected downstream exposure` |
| `P_time` | expected passengers times `D_TO` |
| `P_itinerary` | expected passengers times connection share when `D_TO > 45` minutes |
| `P_service` | expected passengers when `D_TO >= 180` minutes |
| `R_operating` | `D_TX` |

`model/PRE/reference/data2_m2_train_fit.py:compute_train_scales` reconstructs
realized TRAIN-population quantities to freeze normalization scales. It is not
a replacement scenario evaluator. Its separate passenger helper has a stricter
row-availability condition than the main scale builder, so neither population
may be silently substituted for the other.

`AvailableComponentSumDiagnostic` is a diagnostic sum of available valued
components. It is not the paper's equal-domain consequence priority `S_C`.

## Priority And View Registry

The arithmetic authority for component-to-domain construction is
`exp/shared/recovery_priority.py`:

| Object | Definition |
| --- | --- |
| `score_F` | Mean of normalized `F_continuity`, `F_execution`, and `F_propagation`. |
| `score_P` | Mean of normalized `P_time`, `P_itinerary`, and `P_service`. |
| `score_R` | Normalized `R_operating`. |
| `S_C` / equal-domain consequence priority | Mean of `score_F`, `score_P`, and `score_R`. |
| `EQUAL_COMPONENT` | Mean of all seven normalized components. |
| `NO_F_EXECUTION` | Equal-domain aggregate after removing `F_execution` from the flight domain. |

Exp2's `conditional_node_summary` is the paper authority for common-support
conditional node summaries. It renormalizes over common-supported scenario
mass. The strict shared `SupportedScore` materializers reject unsupported
scenario inputs instead; they are deliberately different support semantics,
not interchangeable implementations.

The aggregation-robustness producer defines six views: `BASE_EQUAL_DOMAIN`,
`EQUAL_COMPONENT`, `NO_F_EXEC`, and the three domain-emphasis views. Exp4's
screening consensus uses eight views, including the three single-domain views.
The overlap of formulas does not make the two view sets interchangeable.

## Maintenance Rules

1. Preserve this registry's distinctions in reviewer responses, supplements,
   and future experiment design.
2. Any future target, stage, component, or view change requires an explicit
   scientific contract and a compatibility decision; no name-only replacement
   is permitted.
3. This document does not authorize code consolidation during paper freeze.
