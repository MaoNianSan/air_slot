# Round 2 M3 V2 Before Audit

Audit HEAD: `6b5a8faa591de6dbf366af758cc87d9cb3dc52a6`  
Starting worktree: clean  
Focused baseline: `31 passed`

## Classification

| Area | Finding | Classification | Required closure |
|---|---|---|---|
| M2 input | Hashed, action-free seven-component baseline envelope exists | `ALIGNED` | Add typed baseline component CU values/support so A00 identity can be verified without M3 importing M2 |
| action set | Structural registry loads the existing ordered 23 templates and preserves families, required facts, authority and provenance fields | `ALIGNED` | Do not redesign the set; freeze a V2 view that names operational meaning and eligibility separately from response |
| eligibility | `instantiate_candidates` distinguishes factual precondition and missing required parameters, but comments historically overload `I(a)`/`P(a)` terminology | `CODE_STALE` | Define immutable `ActionEligibility`; reserve `I(a)` for eligibility and `P(a)` for response mechanism |
| response provenance | `ActionResponseSupport` can distinguish evidence bases, but templates normally leave it null and the scenario registry exposes legacy string provenance | `CODE_STALE` | Require source type, source reference, parameter version, freeze ID and provenance in every V2 response rule/output |
| response engine | `response.py` maps a scalar `U_pre` with Bernoulli–Beta intensity and induced-score conversion | `CODE_STALE` | Keep as historical V1 scenario engine; V2 interface operates component-wise on `C_k^{0,CU}(s)` and does not activate this scalar path |
| response registry | 22 non-A00 actions are parameterized as `PURE_SCENARIO`; registry explicitly has `formal_support_upgrade=false` | `SCIENTIFIC_DECISION_REQUIRED` | Classify as frozen scenario assumptions, not empirical effectiveness; no anonymous gamma/weight |
| A00 | Registry defines deterministic zero response and `NOT_REQUIRED` parameters | `ALIGNED` | Add executable identity contract `C^{A00,CU}=C^{0,CU}` over every component/scenario |
| passenger responses | Several actions target `P_itinerary` or `P_service`, while the M2 baseline components currently abstain | `UNSUPPORTED` | Preserve component abstention; an action response cannot manufacture a supported baseline quantity |
| crew/gate/internal cost | Structural actions exist, but M2 provides no direct crew, gate or internal financial cost | `UNSUPPORTED` | Keep response effects scenario-only/abstaining as applicable; do not introduce monetary fields |
| scenario distribution | M2 preserves all scenarios and weights | `ALIGNED` | Require exact input/output scenario identity and weights in an `ActionEvaluationEnvelope` |
| M4 handoff | Existing M3 contracts do not expose one immutable, provenance-complete, no-money envelope | `CODE_STALE` | Define M3 output payload for M4 without importing or changing M4 ranking logic |

## Authority boundaries

M2 owns baseline native consequence and CU lineage. M3 may express an action-conditioned CU response but cannot rewrite `T_IB_A00`, `D_OB`, `D_TX`, `D_TO`, or any M2 native definition. M4 remains the sole owner of monetary mapping and residual-risk ranking.

No response parameter receives a scientific-support upgrade in this tranche. Existing numerical tiers remain reproducible scenario specifications only.
