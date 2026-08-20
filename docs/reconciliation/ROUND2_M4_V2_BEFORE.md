# Round 2 M4 V2 Before Audit

Audit HEAD: `e28e4ddf7d71a7a0b30e58561ab758c4ac910ddd`  
Starting worktree: clean

## Classification

| Area | Finding | Classification | Required closure |
|---|---|---|---|
| M3 input boundary | `M4ActionEnvelopeInput` accepts the full M3 V2 CU distribution, support and response lineage and rejects extra raw fields | `ALIGNED` | Make it the only operational-data input to the V2 evaluator |
| legacy M4 request | `M4DecisionRequest` consumes PRE, M1, M2 and `CandidateAction` directly | `CODE_STALE` | Retain for compatibility only; do not use it in M4 V2 |
| legacy response path | `post_action.py` generates response draws and reconstructs post-action CU inside M4 | `CODE_STALE` | V2 must consume `C^{a,CU}` and never regenerate `P(a)` |
| consequence authority | Legacy evaluation reads raw M2 component vectors and action mitigation/induced fields | `CODE_STALE` | V2 must not consume raw delays, PRE/weather features, or alter native/CU/action-response definitions |
| monetary separation | `MonetaryMappingRegistry` is separate from CU normalization and blocks unfrozen mappings | `ALIGNED` | Preserve separation and immutable input CU |
| mapping rule schema | Rules use generic `weight`, `version`, and optional provenance; source type/reference/freeze are not required per component | `CODE_STALE` | Replace anonymous weight with named parameters and mandatory mapping/source/version/freeze/provenance fields |
| production monetary mapping | No repository registry provides scientifically frozen real monetary-system parameters | `SCIENTIFIC_DECISION_REQUIRED` | Keep production mapping unavailable; use explicitly test-only mappings for engineering tests |
| weighted expectation | `weighted_mean` uses scenario weights | `ALIGNED` | Add explicit validation and lineage in the V2 result |
| weighted CVaR | Existing code selects an upper tail with fractional boundary mass | `ALIGNED` | Specify normalization, validate weights/alpha, and attach the upstream tail-support gate |
| positive-tail support | The repository retains `M1_POSITIVE_TAIL_DECISION_REQUIRED`, but legacy M4 does not consult it | `UPSTREAM_INTERFACE_REQUIRED` | Require a frozen tail policy; reject CVaR when support remains unresolved |
| ranking | Legacy ranking excludes non-formal lanes but can treat frozen scenario-response parameters as formally rankable | `CODE_STALE` | Distinguish supported, assumption-based conditional, and abstained evaluations; never rank abstentions |
| A00 | M3 V2 supplies exact component-wise A00 identity | `ALIGNED` | Map that envelope as the monetary baseline; do not reconstruct it from M2 |
| residual-risk result | Legacy `ActionEvaluation` lacks M2 reference lineage, M3 response provenance, explicit coverage, metric version and result hash | `CODE_STALE` | Add reproducible `RiskEvaluationEnvelope` |

## Authority and stop boundary

M2 owns `C^{0,CU}` and M3 owns `C^{a,CU}`. M4 may only map the latter into `L^{a,m}`, aggregate the preserved scenario distribution, and label comparison authority. No M3 file, experiment, TeX source, action-response rule, CU definition, native quantity, or production monetary parameter is changed in this tranche.
