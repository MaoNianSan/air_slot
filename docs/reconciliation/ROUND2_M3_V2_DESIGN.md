# Round 2 M3 V2 Action-Response Design

## Frozen role and ownership

M3 represents feasible recovery actions and their explicitly supported operational response. It does not choose an action, rank actions, optimize a policy, predict money, or replace M2 consequence construction.

- M2 owns the immutable baseline vector `C^{0,CU}(s)` for each scenario `s`.
- M3 owns eligibility `I(a)` and the response mechanism `P(a)`, then emits `C^{a,CU}(s)`.
- M4 may later consume the full action-conditioned distribution for monetary mapping and ranking.

M3 cannot rewrite `T_IB_A00`, `D_OB`, `D_TX`, `D_TO`, native units, or M2 component definitions.

## Input contract

`M3BaselineConsequenceInput` accepts a hashed, serialized M2 envelope. It carries the exact seven ordered components, scenario identity and weight, native and CU artifact lineage, CU value/support, and the explicit flags `consequence_state=BASELINE`, `action_id=null`, and `action_adjustments_applied=false`. M3 does not import M2 implementation code.

## Action space

The structural action space remains the ordered 23-template registry in `registries/action_templates.yaml`. Its registry hash for this design is `sha256:2057a4fc274eb9eb7b820365f5b85ff1d0d3f9ea96549e8618842c740f987716`. Action existence means only that a recovery operation can be represented; it does not establish eligibility in a particular state or causal effectiveness.

## Eligibility and response separation

`ActionEligibility` is `I(a)`. It contains the action and family, decision node, eligibility state, state/fact conditions, fact references, provenance, and a content-derived eligibility ID. It contains no response parameters.

`ActionResponseRule` is `P(a)`. It contains the action and family, affected components, one or more mechanism types, the response rule, parameter source, support state, source references, parameter version, freeze ID, named parameters, provenance, and a content-derived rule hash. It contains no eligibility conditions.

The supported mechanism types are not collapsed into one formula: `DIRECT_REDUCTION`, `RESOURCE_SUBSTITUTION`, `SEQUENCE_MODIFICATION`, `PASSENGER_SERVICE_PROTECTION`, `IDENTITY`, and `ABSTAIN`.

## Support and provenance

Every V2 response is classified as `SUPPORTED`, `REFERENCE_BASED`, `SCENARIO_ASSUMPTION`, or `ABSTAIN`. Every source is classified as `LITERATURE`, `OPERATIONAL_RULE`, `SCENARIO_ASSUMPTION`, `EXPERT_JUDGEMENT`, or `HYBRID`. Source reference, parameter version, freeze ID, and provenance are mandatory.

A scenario assumption or expert judgement cannot be labeled `SUPPORTED`. An `ABSTAIN` rule cannot carry effect parameters or produce a supported component. A component whose M2 CU baseline is `ABSTAIN` remains `ABSTAIN` under the current V2 contract; lifting that restriction requires a separately approved source and contract change.

The legacy registry `M3_RESPONSE_SCENARIO_V1` has hash `sha256:ff8adb3034603ec225930ed9187bc296b46d58637a974c9de64b341248755ce0`. Its 22 non-A00 entries are reproducible `PURE_SCENARIO` specifications and explicitly have `formal_support_upgrade=false`. “FROZEN” therefore means version-frozen scenario parameters, not empirical validation.

## A00 identity

A00 means no additional recovery from the decision time onward. `build_a00_identity_envelope` is the only executable V2 response in this tranche and enforces, component by component and scenario by scenario:

`C^{A00,CU}_k(s) = C^{0,CU}_k(s)`.

Values, support states, scenario IDs, scenario weights, episode, decision node, and baseline lineage are retained. The identity does not claim that no intervention happened before the decision time.

## Scenario preservation and M4 boundary

`ActionEvaluationEnvelope` requires the output scenario sequence to equal the input sequence exactly and requires weights to sum to one. It retains all seven components for every scenario; no top-1 scenario, mean-only vector, or point estimate is emitted.

`m4_payload()` exposes action ID/family, eligibility lineage, response support and provenance, all scenario IDs/weights, and per-scenario `C_a_CU` component values/support. `M4ActionEnvelopeInput` validates this boundary without invoking the legacy M4 decision path. The preserved distribution is sufficient for a later M4 implementation to calculate expectation, variance, and tail functionals. The payload contains no RMB, currency, monetary cost, ranking, objective, or chosen action.

## Implementation state and stop boundary

- A00 identity: implemented and tested.
- Non-A00 mechanism classification: designed and frozen in `registries/m3_v2_action_response_design.json`.
- Non-A00 component-wise response calculation: not implemented and explicitly disabled.
- M4 consumption shape: implemented as serialization plus a no-money validation contract; the legacy ranking path is not migrated or run.
- Optimization, ranking, experiments, manuscript source edits, and scientific response promotion: not performed.

Final engineering status is `INTERFACE_CLOSED_NON_A00_RESPONSE_GATED`, not scientific validation.
