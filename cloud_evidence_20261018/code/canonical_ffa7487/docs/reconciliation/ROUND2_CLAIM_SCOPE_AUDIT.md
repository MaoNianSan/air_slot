# Round 2 Claim Scope Audit

Scope: strong manuscript claims in Sections 1–4, with Section 5 language checked only where it clarifies the intended experiment boundary.

## Classification rule

- `SUPPORTED`: directly supported as a conceptual statement, current typed contract, frozen configuration, or explicit limitation.
- `NEEDS_LIMITATION`: directionally defensible but broader than the current evidence lane or dependent on missing citations/support.
- `REMOVE`: contradicted by current implementation/evidence or liable to assert an unestablished causal, optimal, monetary, or passenger-completeness result.

## Strong-claim matrix

| Claim or wording class | Location | Classification | Reason |
|---|---|---|---|
| Same current delay may imply different recovery needs under different histories/states | Section 1 | `SUPPORTED` | This is the framework motivation, not an empirical effect estimate. |
| Existing studies “substantially improved” recovery decisions | Sections 1–2 | `NEEDS_LIMITATION` | Scope the object of improvement and repair the unresolved citations. |
| Improving isolated modules does not guarantee cross-stage consistency | Sections 1–2 | `SUPPORTED` | Framed as a logical gap; avoid converting “does not guarantee” into proof of universal failure. |
| The framework affects “final recovery decisions” | Section 1 contribution | `NEEDS_LIMITATION` | Current formal multi-action monetary ranking is unavailable; Development evidence is not final evidence. |
| “Causal GRU” | Section 4.2.1 | `REMOVE` | The model is unidirectional/history-respecting; it does not identify a causal treatment effect. Use temporal/admissible-prefix terminology. |
| All seven passenger/operating consequences are empirically instantiated | Sections 4.2.2 and Tables 5–6 | `REMOVE` | `P_itinerary` and `P_service` abstain; `P_time` is a proxy. |
| Passenger itinerary/service mappings are frozen from literature | Sections 4.1–4.2 | `REMOVE` | No approved frozen mappings exist in the current M2 V2 contract. |
| Twenty-two non-A00 actions have frozen response models suitable for formal comparison | Sections 4.3–4.4 | `REMOVE` | Their legacy values are pure-scenario assumptions, V2 execution is disabled, and formal support is not upgraded. |
| Public data do not identify action-specific causal effects | Section 4.3 | `SUPPORTED` | This is the necessary limitation and must remain prominent. |
| `lambda=0.25`, `alpha=0.90` define the principal risk functional | Section 4.4 | `SUPPORTED` | Both values are frozen in the scientific foundation; availability still depends on mapping and tail support. |
| The study uses a frozen RMB valuation system | Sections 4.2.2, 4.4, 4.5 | `REMOVE` | Production mapping is disabled and all component mappings abstain. |
| A registered or scenario-evaluable action is a valid recommendation | Sections 3.4–4.4 implication | `REMOVE` | Registry membership, eligibility, numerical response, and authoritative ranking are distinct gates. |
| A00 means no additional action from the decision time onward | Sections 3.5 and 4.4 | `SUPPORTED` | This is the exact M3 identity; it does not assert an intervention-free past. |
| The framework provides universal optimal airline recovery | Any prospective summary/conclusion | `REMOVE` | No universal optimizer or optimal-policy proof exists. |
| The framework is general across airlines, data systems, or monetary systems | Any prospective claim | `NEEDS_LIMITATION` | Architecture can parameterize different systems, but portability/generalization is not yet formally demonstrated. |
| The framework estimates causal effects of unexecuted recovery actions | Any prospective claim | `REMOVE` | Explicitly outside the data and model identification scope. |

## Mandatory scope boundaries

- Do not claim causal action effects.
- Do not claim universal or globally optimal recovery.
- Do not claim complete passenger consequence coverage.
- Do not call CU “cost” or “RMB”; CU is a normalization interface.
- Do not treat a version-frozen scenario parameter as scientific support.
- Do not describe conditional/scenario-only rankings as authoritative recommendations.
- Do not claim generalization from partial readiness or unrun Exp4/Final Test work.

## Overall claim status

`MAJOR_LIMITATION_AND_REMOVAL_REQUIRED`.

The conceptual framework claims are mostly supportable. The strongest empirical claims in Section 4 require removal or replacement with explicit gated status before the manuscript can be used to plan formal experiments.
