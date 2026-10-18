# PRE -> M3 -> M4 Action Contract

This document defines the active model contract. It does not define an
experiment, a recommendation rule, or an operational selector.

## PRE to M3 factual boundary

`model.M3.factual_adapter` is the only PRE-to-M3 fact adapter. Native booleans
map to `TRUE` or `FALSE`. Missing, unsupported, numeric, string, identifier,
datetime, mapping, and aggregate reference values remain `UNKNOWN` unless a
named semantic conversion exists. The only current alias is:

```text
successor_state.schedule_reference -> successor_schedule
```

The alias means that a supported schedule object is present. It is not a
retiming-feasibility or authority fact.

## Action registry contract

The registry contains 23 templates. Each template declares the following
fields: `template_id`, `family`, `required_facts`, `required_parameters`,
`authority_capabilities`, `preparation_time_minutes`, `deadline_semantics`,
consequence footprint, response model/parameters, response support, and
provenance.

`A00` is the no-additional-action identity baseline. It is never emitted as an
operational recommendation. Non-A00 response parameters are explicit model
inputs and retain their source/support class.

### Structural footprint and induced burden

Every action/component cell is explicitly classified as `MITIGATION`,
`INDUCED`, or `UNTOUCHED`, with level `PRIMARY`, `SECONDARY`,
`CONDITIONAL_SECONDARY`, or `NONE`. These levels describe structural role and
do not imply a numerical magnitude. Coefficients are independent fields: an
active structural cell without a frozen coefficient remains
`NUMERICAL_PARAMETER_NOT_MATERIALIZED`.

The response equation uses `d_a,k` in ordinal `INDUCED_SCORE` units and the
registry-frozen `gamma = 0.10 CU / INDUCED_SCORE`. The additive term is
`ACTION_ATTEMPT_BURDEN`: it remains present when `rho = 0` because mitigation
failure does not erase the burden of attempting the action. It is not an
empirical action effect, causal estimate, observed cost, or monetary
coefficient.

### Numerical response completeness

Structural action formation and response-parameter completeness are separate.
Missing `m_a,k` or `d_a,k` values never change a constructable action from
`chi_inst=FORMED` to `NOT_FORMED`. For an active footprint cell, the numerical
parameter state is one of:

```text
STRUCTURAL_ZERO
NUMERICALLY_MATERIALIZED
NUMERICAL_PARAMETER_NOT_MATERIALIZED
```

Only `UNTOUCHED` cells may be structural zero. An active cell without its
declared coefficient yields `chi_num=UNDEFINED` with reason
`RESPONSE_PARAMETER_NOT_MATERIALIZED`; no coefficient is defaulted to zero.
The deterministic action-level audit is materialized as
`M3_ACTION_NUMERICAL_READINESS`.

## Required facts and support class

| Required fact | Actions | Classification | Contract interpretation |
| --- | --- | --- | --- |
| `successor_schedule` | A21 | derived object presence; action contract underspecified | schedule reference is present, but retiming predicates remain UNKNOWN |
| `passenger_connection` | A11, A32 | proxy-only | aggregate passenger/segment references do not identify a live connection |
| `passenger_itinerary` | A31 | proxy-only | no individual itinerary is published |
| `passenger_exposure` | A33 | proxy-only | aggregate exposure is not a contemporaneous service fact |
| `flight_execution_range` | A13 | unobserved | no decision-time execution/fuel/safety envelope |
| `slot_opportunity`, `priority_window` | A22, A23 | unobserved | no live ATFM opportunity publication |
| `gate_resource`, `ground_resource`, `stand_resource` | A32, A41-A43 | unobserved | no current airport resource state |
| replacement/standby/reposition aircraft, compatibility, rotation | A51-A55 | unobserved | no contemporaneous alternative inventory/feasibility |
| replacement/reserve/reposition crew, duty | A61-A64 | unobserved | no roster, qualification, duty/rest or transport feasibility |
| cancellation/network authority | A71-A72 | underspecified and unobserved | capability labels are not current actor authority |

No required action fact is currently a direct contemporaneous observed boolean.
`A21`, `A71`, and `A72` are always `CONTRACT_UNDERSPECIFIED` and retain factual
`UNKNOWN`, even when a capability label or partial object is present.

## M3 output

For every action template at every node, M3 emits an `ActionInstantiationRecord`
with `template_id`, `InstantiationState`, reason, missing required parameters,
source/lineage, and an optional candidate. Only `FORMED` records carry a
`CandidateAction`; `NOT_FORMED` records remain in the audit trail and are not
passed to M4. `instantiate_candidates()` is the formed-candidate projection.

`CandidateAction` records structural action identity, parameters,
`InstantiationState`, factual state/reason, response model and support, lead
time, footprint, and provenance. A candidate is formed only when the declared
mathematical parameters exist. Factual state does not control formation:

```text
required parameters missing -> chi_inst = NOT_FORMED (record retained; candidate omitted)
required parameters present -> chi_inst = FORMED
```

For a formed candidate, factual evaluation is:

```text
all required facts TRUE -> chi_fact = TRUE
any fact FALSE          -> chi_fact = FALSE
otherwise               -> chi_fact = UNKNOWN
```

The M3 action-conditioned envelope preserves all scenario IDs, weights, seven
CU components, response rule identity, response support, and lineage. It does
not perform monetary mapping or selection.

## M4 input and numerical output

`M4ActionEnvelopeInput` consumes only the serialized M3 CU envelope. It keeps
`instantiation_state`, `eligibility_state`, `opportunity_state`, response
support/provenance, scenario identity, and component support metadata.

`evaluate_residual_risk` checks only numerical completeness for `chi_num`:

- a frozen `ConsequenceComparisonScope` is present;
- every participating action uses the same exact `K_cmp` and measurement registry;
- mappings exist and are executable for every component in `K_cmp`;
- all action-conditioned CU values are present, supported, and finite;
- each mapping output and aggregate is finite;
- the declared risk policy is executable and tail support is resolved.

It then computes weighted expected loss, variance, VaR, CVaR, and the declared
residual-risk objective. Factual `UNKNOWN` or `FALSE`, response support class,
and opportunity state do not by themselves make `chi_num` undefined. They are
retained as independent metadata and can label the numerical comparison as
`CONDITIONAL_INPUTS`.

`rank_risk_evaluations` validates the common basis (episode/node, scenario IDs
and weights, frozen comparison scope identity/component IDs/measurement
registry, monetary mapping, and risk policy), then returns:

- `supported_input_ranking`;
- `conditional_input_ranking`;
- `not_comparable_action_ids`.

These are numerical comparison outputs only. They are not authority, policy,
or recommendation outputs.

## Independent state contract

| State | Canonical code |
| --- | --- |
| `chi_inst` | `InstantiationState` (`FORMED` / `NOT_FORMED`) |
| `chi_fact` | `FactualState` / `EligibilityState` (`TRUE`, `FALSE`, `UNKNOWN`) |
| `chi_num` | `NumericalEvaluationState` (`DEFINED`, `UNDEFINED`) |
| `chi_resp` | `ResponseSupportClass` plus response provenance |
| `chi_opp` | `OpportunitySupportState` (`AVAILABLE`, `UNAVAILABLE`, `UNKNOWN`, `NOT_INSTANTIATED`, `NOT_REQUIRED`) |
| `chi_sel` | `SelectionState.UNIMPLEMENTED`; selector calls raise `M4_SELECTION_NOT_AUTHORIZED` |

No single boolean is used as a substitute for these states.
`RiskEvaluationSupport` is separate overall input-qualification metadata on an
M4 evaluation; it is not a replacement for `chi_resp`, `chi_fact`, or `chi_opp`.

The M1-to-downstream boundary also keeps formal forecast horizons (`tau`) apart
from evaluation lead-time slicing (`ell`). The former is `[0,15,60]`; the latter
is `[0,30,60,120,180,240,300,360,420,480]` and is never an additional model
head.
