# Air Slot Model Scientific Specification

Status: model-contract closure, 2026-09-02. This is a model specification,
not an experiment or paper-result specification. `data1/` and `data2/` are
read-only.

## Scope and dependency

The active scientific chain is:

```text
PRE -> M1 -> M2 -> M3 -> M4
```

PRE publishes cutoff-legal typed evidence. M1 represents the unresolved
flight-chain state. M2 maps each state scenario to seven operational
consequences and a common constructed unit (CU). M3 instantiates recovery
action contracts and applies a declared action-response model to the same
scenario. M4 maps CU to a declared measurement system and computes residual
risk on a common basis. M4 does not expose an operational selector.

The model never treats a proxy as an observed fact, an assumption as an
observed response, or a numerical comparison as operational authority.

## PRE

The downstream PRE boundary is `PREState`. It carries:

- `predecessor_state`, `current_state`, and `successor_state` typed objects;
- aggregate/static `reference_state` objects;
- target support and evidence ledgers;
- variable lineage and decision-time information cutoff.

Publication is availability-gated. Post-hoc records are not inference
evidence unless their declared availability is no later than the information
cutoff. `successor_state.schedule_reference` is explicitly adapted to the M3
fact `successor_schedule`; the alias means only that a schedule reference
object is present.

## M1 state

M1 consumes cutoff-legal PRE evidence and admissible history. The current
primitive state targets are:

```text
T_IB_A00   predecessor-to-successor inbound-block event time
D_OB       successor additional off-block delay
D_TX       successor excess taxi delay
```

Derived identities are:

```text
R_IB = max(0, T_IB_A00 - decision_time)
D_TO = D_OB + D_TX
```

The M1 scenario distribution preserves scenario IDs, weights, and lineage:
`(scenario_id, scenario_weight, T_IB_A00, D_OB, D_TX, D_TO)`. State contraction
uses newly observed cutoff-legal events; it never backfills a future outcome
into an earlier node. The current implementation is the typed M1 V2 service
and its FAST/STATE_AWARE paths share the same output contract. The service
envelope records decision time, information cutoff, roll grid, model
path/version, scenario budget, support, and lineage. Formal forecast horizons
are `tau={0,15,60}`; the separate evaluation lead-time grid
`ell={0,30,60,120,180,240,300,360,420,480}` is a node-slicing contract and
never creates prediction heads. Calibration is head-specific under the frozen
July 2019 contract; fitted temperatures remain checkpoint-specific and are not
transferred across hidden-size settings.

The frozen architecture is a single-layer, causal, unidirectional GRU without
attention. `H=8` is primary; `H=16` is a predefined sensitivity setting, not a
tuning candidate. The finite supports are `360/180/60` minutes for
`T_IB_A00_remaining/D_OB/D_TX`, with overflow beginning at `365/185/65` on the
5-minute grid. The positive-quantile representation grid is
`[0.1,0.3,0.5,0.7,0.9]`, and the active scenario budget is 64 per episode.

## M2 consequence model

For scenario `s`, M2 emits exactly these seven components in fixed order:

| Component | Definition | Native unit | Current evidence boundary |
| --- | --- | --- | --- |
| `F_continuity` | `max(0, R_IB - turnaround_reference)` | minutes | derived from M1 plus train-frozen reference |
| `F_execution` | `D_OB` | minutes | derived from M1 |
| `F_propagation` | `D_TO * expected_downstream_exposure` | exposure-minutes | derived using frozen exposure reference |
| `P_time` | `Nbar_pax * D_TO` | passenger-minutes | T-100 expected passengers per performed flight |
| `P_itinerary` | `Nbar_pax * r_conn * 1[D_TO > 45]` | expected disrupted connecting-passenger exposure | DB1B historical continuation-share reference plus 45-min representative itinerary-disruption reference |
| `P_service` | `Nbar_pax * 1[D_TO >= 180]` | expected long-delay passenger-service exposure | 180-min long-delay passenger-service reference |
| `R_operating` | `D_TX` | excess-taxi minutes | derived from M1 |

Each row retains native quantity, CU quantity, support state, source/reference
lineage, and reason code. Unsupported values remain null with `ABSTAIN`; no
zero-fill, component dropping, or denominator renormalization is allowed.
CU normalization is separate from monetary mapping. M2 output is the baseline
`C^(0,CU)`; M3 owns action-conditioned `C^(a,CU)`.

Each component has two distinct meanings: `consequence_semantics` describes
the channel represented by the model, while `baseline_empirical_realization`
describes the public-data proxy used to construct the baseline. In particular,
`R_operating` represents operating/recovery-resource burden while its baseline
proxy is `D_TX`; `P_service` represents passenger service/care burden while its
baseline proxy is `Nbar_pax * I[D_TO >= 180]`. An action-side induced burden in
one of these channels is a declared scenario burden on that channel, not a
claim that the baseline proxy is the action outcome.

The active CU scales for all seven components are frozen positive Train medians
`Median_Train(q_k | q_k > 0)`. Passenger scales are materialized from the new
T-100/DB1B references; no passenger component uses an assumption scale.
Historical V1/V2/V3 registries remain immutable and are provenance-only. The
active registry is `M2_DATA2_FORMAL_CU_V4`, whose seven scales are independently
normalized by `Median_Train(q_k | q_k > 0)`. `Nbar_pax` is a T-100 H1
Train-frozen expected-passengers-per-performed-flight reference, not an actual
passenger count. `r_conn` is a DB1B Q1/Q2 Train-frozen historical continuation
share, not live connecting-passenger information. `P_itinerary` and `P_service`
are domain proxies, not observed missed connections, service delivery, or
airline expenditure. All seven CU components enter `M4_RMB_BASE_MAPPING_V2`.

## M3 action contract

The active action registry contains 23 templates: `A00`, `A11`, `A13`, `A21`,
`A22`, `A23`, `A31`, `A32`, `A33`, `A41`, `A42`, `A43`, `A51`, `A52`, `A53`,
`A54`, `A55`, `A61`, `A62`, `A63`, `A64`, `A71`, and `A72`.

Every template declares: identity, family, required facts, required
mathematical parameters, authority capability labels, preparation time,
consequence footprint, response model and parameters, response support and
provenance, and opportunity/deadline semantics.

The consequence footprint is explicit for all seven components. Each cell has
`role in {MITIGATION, INDUCED, UNTOUCHED}` and
`level in {PRIMARY, SECONDARY, CONDITIONAL_SECONDARY, NONE}`. A structural
level is not a numerical effect magnitude; a missing coefficient is reported
as `NUMERICAL_PARAMETER_NOT_MATERIALIZED` rather than filled by convention.

For non-A00 actions, `d_a,k` is a nonnegative ordinal structural burden score
with unit `INDUCED_SCORE`. The frozen conversion is
`gamma = 0.10 CU / INDUCED_SCORE`, so `gamma*d_a,k` is an action-attempt
burden. It is present even when `rho = 0`; it is not multiplied by `rho` and
does not represent an empirical cost, causal effect, or RMB coefficient.

`A00` is the no-additional-action identity baseline. It copies each baseline
CU component exactly and is a comparator only. The other templates currently
use declared, reproducible response models; scenario parameters are not
observed intervention effects.

Required facts are evaluated centrally by `model/M3/factual_adapter.py`:

```text
all required facts TRUE  -> TRUE
any required fact FALSE   -> FALSE
otherwise                 -> UNKNOWN
```

`A21` is always `CONTRACT_UNDERSPECIFIED` with factual `UNKNOWN`. A schedule
reference can form the mathematical action target but does not establish a
retiming window, departure status, feasibility, or authority. For `A71` and
`A72`, framework capability labels are not contemporaneous cancellation or
network authority; factual authority therefore remains `UNKNOWN` and the
contract is `CONTRACT_UNDERSPECIFIED`.

Every registered template produces one `ActionInstantiationRecord` per node.
`FORMED` records carry the `CandidateAction`; `NOT_FORMED` records carry an
explicit reason and missing required parameters and never enter M4.

## M4 comparison

M2 ontology is always the fixed seven-item set `K = {F_continuity,
F_execution, F_propagation, P_time, P_itinerary, P_service, R_operating}`.
M4 does not assume all seven or the historical five items. Each comparison
must carry a frozen `ConsequenceComparisonScope` defining `K_cmp subset K`,
support requirements, measurement registry ID, version, and provenance. If
absent or not frozen, `chi_num=UNDEFINED` with
`COMPARISON_SCOPE_NOT_FROZEN`.

M4 requires one common basis: same episode/node, scenario IDs and weights,
identical frozen `K_cmp`, measurement registry, and risk policy.
For each action with a complete finite mapping, it computes:

```text
E_w[L]       weighted expected monetary loss
Var_w[L]     weighted variance
VaR_alpha    upper-loss quantile
CVaR_alpha   upper-tail mean
J            expected-loss/CVaR weighted residual-risk objective
```

The scientific foundation config and `M4_RISK_POLICY_BASE_V1` freeze
`lambda=0.25`, `alpha=0.90`, expected-loss weight `0.75`, and CVaR weight
`0.25`. `M4_RMB_BASE_MAPPING_V2` freezes RMB as the active constructed
measurement system for all seven components with `beta_k=1.0`; V1 is superseded
provenance.
This is a reporting/measurement convention, not currency conversion,
accounting cost, or empirical airline loss. M4 returns `SUPPORTED_INPUTS`,
`CONDITIONAL_INPUTS`, or
`NOT_COMPARABLE` as numerical comparison metadata. These labels are not
authority labels. Factual, response-support, and opportunity states remain
attached to each evaluation.

No `argmin` result is exposed as `recommended_action_id`. `chi_sel` is
`UNIMPLEMENTED` and `NOT_AUTHORIZED`.

## Independent action states

| State | Definition | Code representation |
| --- | --- | --- |
| `chi_inst` | mathematical action instance can be formed | `InstantiationState` in per-template `ActionInstantiationRecord`; formed records also carry `CandidateAction`; `instantiable` is only a compatibility projection |
| `chi_fact` | required contemporaneous factual conditions are known | `FactualState` in adapter and `EligibilityState` in M3/M4 |
| `chi_num` | consequence/risk model is complete, common-basis compatible, and finite | `NumericalEvaluationState` |
| `chi_resp` | evidential/support status of the action-response mapping | `ResponseSupportClass` and response provenance |
| `chi_opp` | current execution opportunity is known | `OpportunitySupportState` |
| `chi_sel` | operational selection authority | `SelectionState.UNIMPLEMENTED`; selector API raises `M4_SELECTION_NOT_AUTHORIZED` |

These states are independent. In particular:

```text
chi_fact = UNKNOWN does not imply chi_num = UNDEFINED
chi_fact = UNKNOWN does not imply chi_num = DEFINED
chi_num depends only on numerical-model completeness and finiteness
```

An UNKNOWN or FALSE factual state is retained as metadata. It can make a
comparison conditional, but it does not erase a complete numerical result.
M4 `RiskEvaluationSupport` is an overall input-qualification label for the
comparison result; it does not replace any of the six `chi` states.

## Unresolved scientific semantics

The following remain explicit scientific gates rather than code defaults:

- complete contemporaneous factual contracts for A21, A52, and other resource,
  passenger, crew, slot, and network actions;
- contemporaneous authority publication for A71/A72;
- action-specific opportunity/deadline evidence beyond the current typed state;
- empirical support for non-A00 response mappings;
- empirical itinerary and service outcomes beyond the frozen
  assumption/reference-grounded component definitions;
- an operational comparison scope is absent unless a caller explicitly freezes
  `ConsequenceComparisonScope`;
- any future operational selection rule. No such rule is implemented here.
