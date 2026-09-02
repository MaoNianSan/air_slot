# Current Model Architecture

## Active dependency direction

```text
PRE -> M1
PRE -> M2
PRE -> M3
M1  -> M2
M1  -> M3
M2  -> M3
M3  -> M4
model/common -> all layers
registries/configs -> consumed contracts
```

`data1/` and `data2/` are read-only. Model modules do not import retired
experiment or paper-result code.

Active model-owned authorities are `configs/scientific/foundation.yaml`,
`registries/m2_data2_formal_cu_v2.json`, `registries/action_templates.yaml`,
`registries/m4_rmb_base_mapping.json`,
`registries/m4_risk_policy_base_v1.json`, and
`registries/MODEL_PARAMETER_REGISTRY.json`. Historical EUR registries and
compatibility M4 facades are not active loader inputs.

| Layer | Responsibility | Does not do |
| --- | --- | --- |
| `model/PRE` | cutoff-legal evidence publication, support and lineage | prediction, action facts, response effects |
| `model/M1` | history-conditioned unresolved state scenarios | action feasibility or recommendation |
| `model/M2` | fixed seven-component baseline consequence and CU | action response, factual fabrication, monetary authority |
| `model/M3` | action templates, instantiation, factual adapter, response contract, action-conditioned CU | monetary mapping, risk comparison, selection |
| `model/M4` | common-basis numerical risk calculation and comparison metadata | operational selection or authority inference |
| `model/common` | shared typed primitives | layer-specific policy |

## M3/M4 boundary

M3 transfers only typed `C^(a,CU)` distributions plus scenario identity,
support, factual state, instantiation state, opportunity state, response rule,
and provenance through `M4ActionEnvelopeInput`. M4 does not reconstruct PRE,
M1, M2, or M3 objects.

M2 owns the fixed seven-component consequence ontology `K`. M4 comparison
requires an explicit frozen `ConsequenceComparisonScope` with `K_cmp subset K`,
support requirements, measurement registry ID, version, and provenance. The
same exact scope identity and component IDs are required for all compared
actions; no seven- or five-component default exists.
`RiskRankingEnvelope` has three numerical output collections:

```text
supported_input_ranking
conditional_input_ranking
not_comparable_action_ids
```

They are not recommendation lanes and carry no selection authority.

## Independent states

The architecture has six non-interchangeable model states:

```text
chi_inst  InstantiationState
chi_fact  FactualState / EligibilityState
chi_num   NumericalEvaluationState
chi_resp  ResponseSupportClass plus provenance
chi_opp   OpportunitySupportState
chi_sel   SelectionState.UNIMPLEMENTED
```

`CandidateAction.instantiable` is a compatibility projection of
`InstantiationState`, not a gate that represents factual, numerical, response,
opportunity, or selection status. `project_authority()` always rejects with
`M4_SELECTION_NOT_AUTHORIZED`.

M3 retains one `ActionInstantiationRecord` per template per node, including
`NOT_FORMED` records; only formed records are projected as candidates.

M1 service metadata is authoritative at the envelope boundary: `decision_time`,
`information_cutoff`, `roll_minutes`, `model_path`, `model_version`,
`scenario_count`, support, and lineage are retained. Scheduled updates advance
the service timeline; direct queries do not reset it. Formal `tau` horizons and
evaluation `ell` lead times are separate contracts.

## Current scientific boundaries

- A21 is `CONTRACT_UNDERSPECIFIED`; schedule object presence does not establish
  retiming feasibility.
- A71/A72 capability labels do not establish contemporaneous authority.
- Non-A00 response mappings currently preserve their declared support; scenario
  assumptions do not become empirical intervention evidence.
- Opportunity does not default open when a model has not instantiated it.
- The active RMB BASE registry covers all seven ontology components.
  Passenger references remain aggregate/domain-proxy references and do not
  establish individual passenger, live connection, or service facts.
