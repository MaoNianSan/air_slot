# Round 2 M4 V2 Monetary Mapping and Residual-Risk Design

## Role and authority

M4 owns monetary interpretation, scenario-weighted residual-risk aggregation, and explicitly labelled action ranking. It does not generate consequences, model action response, decide feasibility, or optimize a policy.

The authority chain is strict:

`C^{0,CU}` (M2) -> `C^{a,CU}` (M3) -> `L^{a,m}` and risk metrics (M4).

M4 cannot change native quantities, CU normalization, scenario identity/weight, action eligibility, or action response. The public M4 V2 API therefore exposes `M4ActionEnvelopeInput`, `evaluate_residual_risk`, and `rank_risk_evaluations`; the PRE/M1/M2/CandidateAction evaluator remains legacy-only.

## Why CU is separated from money

CU is a monetary-system-independent consequence representation. A monetary system `m` supplies only the component mapping `f_k^m`, so the same `C_k^{a,CU}(s)` can be interpreted under multiple systems without rerunning M1–M3 or changing consequence identity. This separation prevents prices, accounting conventions, and currency assumptions from leaking into operational consequence construction.

For each supported component and scenario:

`L_k^{a,m}(s) = f_k^m(C_k^{a,CU}(s))`.

The currently implemented mapping function is `LINEAR_SCALE`, with the explicitly named parameter `money_per_cu`. The interface permits new named/versioned functions later; no anonymous weight, gamma, or omega is accepted.

## Monetary mapping registry

Every component rule requires `monetary_system_id`, `component_id`, `mapping_function`, `parameter_version`, `source_type`, `reference`, `freeze_id`, named parameters with units/provenance, `rule_id`, and `rule_hash`. The registry binds one monetary system, registry version/hash, freeze state, component coverage, reference period, and provenance.

`NOT_FROZEN` has no executable mappings. `TEST_ONLY` is executable solely for contract tests and can produce only conditional results. Only `FROZEN` with non-test sources can support authoritative ranking. No production/RMB mapping is frozen in this tranche.

## Residual risk

Residual risk is the loss remaining after the M3 action response. M4 therefore maps `C^{a,CU}`, not the initial `C^{0,CU}`. The sole equality case is A00 because M3 guarantees `C^{A00,CU}=C^{0,CU}`; its mapped loss is the monetary baseline.

For scenario losses `L^{a,m}(s)` and normalized input weights `w_s`, M4 V2 calculates:

- expected loss: `sum_s w_s L^{a,m}(s)`;
- variance: `sum_s w_s (L^{a,m}(s)-E[L])^2`;
- upper-loss `VaR_alpha`: first loss whose cumulative probability reaches `alpha`;
- upper-loss `CVaR_alpha`: the largest-loss probability mass totaling exactly `1-alpha`, using fractional mass at the quantile boundary;
- residual-risk objective: `beta_E E[L] + beta_C CVaR_alpha`, where the named coefficients sum to one and belong to the versioned risk policy.

All input weights must be finite, positive, aligned to the scenario sequence, and sum to one. M4 never substitutes unweighted samples or a mean-only input.

## Tail gate

`ResidualRiskPolicy` requires `alpha`, named objective coefficients, metric version, policy status/freeze, tail-support state/reference, provenance, and a policy hash. If upstream positive-tail support remains unresolved, evaluation raises `M1_POSITIVE_TAIL_DECISION_REQUIRED`; M4 does not extrapolate the tail.

## Support, coverage, and ranking

`RiskEvaluationEnvelope` retains action and M3 envelope identity, monetary registry lineage, metric policy lineage, M3 response support/provenance, every scenario and weight, all seven component CU/loss records, M2 reference-lineage hashes, component coverage, metrics, ranking authority, reason codes, and a reproducible hash.

- `SUPPORTED`: complete supported consequence, M3 supported response, scientifically frozen mapping, and frozen risk policy; eligible for authoritative ranking.
- `ASSUMPTION_BASED`: executable but at least one response/mapping/policy basis is scenario/test/non-authoritative; ranked only in a separately labelled conditional list.
- `ABSTAINED`: unsupported response, incomplete mapping, unavailable CU, or unfrozen mapping; metrics remain null and the action is not ranked.

Ranking is deterministic sorting of already evaluated residual risk, with separate authoritative and conditional lists. It is not action search or policy optimization.

## Implementation and stop status

The M4 V2 engineering contracts, weighted aggregation, provenance propagation, abstention, and labelled ranking are implemented. Production monetary values, the positive-tail policy, and real risk-objective coefficients remain human gates. No experiment, Exp1–4 change, M3 change, TeX edit, production ranking, or scientific-result claim is part of this closure.

## Required answers

1. CU is separated from money so operational consequence identity remains stable across currencies, valuation sources, and accounting conventions; only `f_k^m` changes.
2. M4 cannot modify M2 consequence because M2 is the scientific authority for baseline quantity/CU construction and M3 is the authority for action response; changing either in M4 would duplicate authority and corrupt lineage.
3. Initial disruption impact is `C^{0,CU}` before an additional framework action, whereas residual risk is the monetary loss distribution derived from post-response `C^{a,CU}`; they coincide only for A00.
4. Uncertainty is preserved by mapping every component within every scenario before aggregation, retaining the original scenario IDs and weights, and calculating weighted expectation, variance, VaR, and fractional-mass CVaR without pre-collapse.
