# Exp2 Scientific Execution Protocol V1

## Protocol status

Protocol identifier: `AIR_SLOT_EXP2_SCIENTIFIC_EXECUTION_PROTOCOL_V1`

Repository basis: `9ba4835590718265110d6b5d99be720a0fd712ad`

This document freezes the minimum non-numerical scientific protocol for a future Exp2 execution. It does not authorize execution and does not freeze any M3 response parameter, monetary conversion parameter, CVaR level, or risk-objective coefficient.

```text
PROTOCOL_FREEZE_STATUS = FROZEN
PERMITTED_SCIENTIFIC_LANE = SCENARIO_CONDITIONED_CONDITIONAL
AUTHORITATIVE_ACTION_CLAIM = OUT_OF_SCOPE
EXP2_EXECUTION_STATUS = BLOCKED
```

The protocol is grounded in the current six-variant Exp2 implementation, the M3/M4 registries, `M3_M4_EXP_EXECUTION_GATE_AUDIT.md`, and the manuscript boundary that scenario action responses are numerical assumptions rather than empirical causal effects.

## 1. Scientific question

The frozen scientific question is:

> Holding the dataset, cohort, M1/M2 artifacts, action set, action-response assumptions, monetary interpretation, and risk policy fixed, how sensitive are downstream recovery-action comparisons to the amount and structure of uncertainty and consequence information retained by the Exp2 representation?

Exp2 has two paired representation families:

| Family | Reference | Comparisons | Changed factor only |
| --- | --- | --- | --- |
| Exp2A | `EXP2A_JOINT` | `EXP2A_MARGINAL`, `EXP2A_COLLAPSED` | M1 scenario information structure |
| Exp2B | `EXP2B_COMPONENT` | `EXP2B_CHANNEL`, `EXP2B_SCALAR` | M2 consequence resolution |

The scientific object is representation sensitivity under a fixed downstream decision system. Exp2 does not compare trained models, retrain M1, reconstruct M2 consequences, or optimize M3/M4 parameters.

## 2. Claim scope

### 2.1 Permitted claim

If all execution gates below close, Exp2 may claim only that, within the frozen dataset/cohort and under the declared M3 scenario assumptions and fixed M4 interpretation, changing representation alone does or does not change the numerical recovery comparison.

The permitted wording class is:

> `SCENARIO_CONDITIONED_REPRESENTATION_SENSITIVITY`

Any result must be described as conditional on:

- the frozen M1 and M2 artifacts;
- the exact action-set manifest;
- the M3 scenario-response registry and per-action rules;
- the M4 monetary mapping and residual-risk policy;
- the dataset, split, cohort, and seed.

### 2.2 Blocked claims

This protocol does not support claims that:

- an M3 response is an observed or identified causal action effect;
- an action is operationally optimal, recommended, or superior;
- a representation or model is universally sufficient, best, or superior;
- a conditional numerical ordering is an authoritative recovery ranking;
- a residual-risk difference is realized benefit, regret, savings, or avoided cost;
- an M4 quantity is RMB or another real currency without a separately justified real-currency mapping;
- the findings generalize beyond the frozen cohort, split, artifacts, and scenario assumptions;
- Development evidence is Final Test or final paper evidence.

This matches the manuscript claim boundary: its Exp2 action comparison is explicitly scenario-conditioned and non-authoritative, and it excludes authoritative rankings, optimal actions, causal action effects, and regret. The present protocol preserves that boundary rather than upgrading `PURE_SCENARIO` inputs to empirical support.

## 3. Action comparison protocol

### 3.1 Minimum action count

At every decision node admitted to the primary metrics, the reference and comparison representation must contain the same **at least two** numerically ranked actions.

```text
MINIMUM_COMMON_ACTION_COUNT = 2
```

One action cannot support `DECISION_RANKING_CHANGE`. A node with fewer than two common ranked actions is not backfilled, assigned zero, or supplied with a different action set; it is excluded from the primary comparison with an explicit support reason and counted in execution coverage.

### 3.2 A00 requirement

`A00` is mandatory. The minimum comparison is therefore:

```text
A00 + at least one eligible non-A00 action
```

`A00` is the current decision-time no-additional-action identity baseline. Requiring it gives every admitted comparison a common baseline and prevents a two-action subset from being defined solely by whichever interventions happen to be numerically convenient.

This requirement does not claim that no historical intervention occurred, and it does not turn the non-A00 scenario response into a supported real-world effect.

### 3.3 Action-set manifest

No action set may be selected dynamically from variant outputs. Before execution, one content-addressed action-set manifest must be frozen for the dataset/cohort/split and supplied identically to every Exp2 variant.

The manifest must contain:

- manifest ID, schema version, freeze ID, and SHA-256 content hash;
- dataset ID, split, cohort identity/hash, and decision-node scope;
- ordered unique action IDs, with `A00` present;
- the structural action-registry ID, version, hash, and source identity;
- the M3 response-registry ID and hash;
- one response-rule ID and hash for every included action;
- per-action response support class, source type, source references, parameter version, freeze ID, and provenance;
- eligibility and instantiability rules, including the handling of `FALSE` and `UNKNOWN` prerequisites;
- a deterministic order used consistently for exact numerical ties;
- the rule that the same eligible common action set is passed to M3/M4 for the paired reference and comparison representation.

The manifest may freeze a supported subset; the full 23-template structural catalog is not required. It must include at least one non-A00 action and may include more only when each added action satisfies the same response, provenance, support, consequence-coverage, and M4-evaluation gates.

Per-node eligibility may reduce the manifest set. That reduction must depend only on the frozen eligibility contract and decision-time facts, never on Exp2 variant identity, M3/M4 scores, or future information. Nodes failing the two-common-action rule remain explicitly unevaluable.

## 4. M3 support interpretation

### 4.1 Frozen interpretation

The scientific interpretation selected for the principal Exp2 multi-action comparison is:

```text
M3_SUPPORT_INTERPRETATION = SCENARIO_ASSUMPTION
```

Every included non-A00 response must be represented as a typed `ActionResponseRule` whose support and source are consistent with `SCENARIO_ASSUMPTION`. The current `M3_RESPONSE_SCENARIO_V1` registry is reproducible and human-approved as a scenario specification, but it declares `PURE_SCENARIO` provenance and `formal_support_upgrade=false`; it is therefore not `SUPPORTED` evidence of real action effectiveness.

`A00` retains its deterministic identity semantics. Its stronger structural status does not upgrade a multi-action comparison containing scenario-assumption alternatives: the metric-level comparison inherits the weakest included support and remains conditional.

### 4.2 Treatment of the four support classes

| M3 support class | Protocol treatment |
| --- | --- |
| `SUPPORTED` | Not selected for this protocol. It would require evidence not supplied by the current scenario registry and would widen the manuscript claim improperly. |
| `REFERENCE_BASED` | Not selected. No common reference-backed response artifact has been frozen for the required non-A00 comparison set. |
| `SCENARIO_ASSUMPTION` | Selected. Permits reproducible numerical sensitivity analysis with explicit conditional/non-causal wording. |
| `ABSTAIN` | Cannot enter action disagreement, ranking change, or residual-risk difference. It remains an explicit unavailable state and contributes only to coverage accounting. |

The selected interpretation matches the manuscript because the manuscript already describes numerical M3 responses as scenario-conditioned, not empirical causal effects, and labels the resulting action comparisons non-authoritative. No manuscript claim requires a `SUPPORTED` treatment-effect interpretation for the limited representation-sensitivity question.

## 5. M4 evaluation protocol

### 5.1 Monetary interpretation scope

M4 must use one complete, content-addressed, scientifically frozen seven-component monetary mapping shared by all variants. The mapping must be applied per component and per scenario before risk aggregation, with the original scenario weights preserved.

For this protocol, its scientific interpretation is limited to:

```text
CONSTRUCTED_INTERNAL_LOSS_UNIT_FOR_PAIRED_SENSITIVITY_ONLY
```

The mapping may provide a common numerical scale for paired comparisons. It must not be called observed cost, accounting cost, realized savings, RMB, or another real currency unless a separate source-backed real-currency protocol is approved. `TEST_ONLY`, incomplete, self-declared, or fallback mappings are not admissible.

This document does not select mapping functions or numerical parameter values. A future frozen mapping artifact must provide those values, sources, versions, provenance, and hashes.

### 5.2 Risk policy

All variants must share one complete, content-addressed `ResidualRiskPolicy`, including its tail convention and CVaR policy. The policy must be frozen and executable before Exp2 starts, but this document does not select alpha, expected-loss/CVaR coefficients, or other numerical values.

No variant-specific policy, parameter tuning, default, test value, or post-result choice is allowed.

### 5.3 Ranking authority

The accepted scientific lane is conditional, not authoritative:

```text
REQUIRED_METRIC_LEVEL_AUTHORITY = CONDITIONAL
```

- every included action must have a numerical M4 residual-risk value and must not be `NOT_RANKED`;
- individual A00 handling does not upgrade the multi-action metric when any included alternative is `SCENARIO_ASSUMPTION`;
- the overall Exp2 metric/result support must be `PARTIAL` or its exact schema-equivalent conditional state, never `SUPPORTED` or `AUTHORITATIVE`;
- an authoritative ranking or recommendation claim requires a different future protocol with supported M3 effects and is outside this freeze.

Conditional output is scientifically admissible here because the estimand is sensitivity of a fixed scenario-conditioned numerical comparison to representation, not the true best operational action. `NOT_RANKED` or missing values block the affected primary comparison; they are not converted to zeros.

## 6. Metric protocol

All metrics are paired reference-versus-variant comparisons over the same action IDs, response rules, mapping, policy, cohort, and decision nodes. Numerical differences use `variant - reference`. Scenario draws are numerical integration units, not independent observations.

### 6.1 Primary metric: action disagreement

`DECISION_ACTION_DISAGREEMENT` is the indicator that the minimum-residual-risk action differs between the family reference and comparison representation. The frozen action-manifest order provides deterministic handling of exact numerical ties and must be identical across variants.

The result is summarized as a rate over admitted decision nodes, with episode-balanced aggregation required for scientific reporting so that episodes, rather than scenario draws or high-node-count episodes, define the empirical weighting.

Interpretation: sensitivity of the scenario-conditioned top action to representation. It is not recommendation error or accuracy.

### 6.2 Primary metric: ranking change

`DECISION_RANKING_CHANGE` is the pairwise ranking-reversal rate over all unordered pairs in the same common action set. A reversal occurs only when the signed reference and comparison gaps have opposite signs; an exact tie is not counted as a reversal, matching the implementation.

At least two common ranked actions are required. Scientific reporting uses episode-balanced aggregation.

Interpretation: sensitivity of relative numerical ordering to representation. It is not authoritative policy instability.

### 6.3 Secondary metric: residual-risk difference

`DECISION_RISK_DIFFERENCE` is the mean, across the frozen common action IDs, of paired M4 residual-risk differences `variant - reference`, followed by episode-balanced aggregation for cohort reporting.

Its unit is the frozen M4 constructed internal loss unit. It is secondary because its magnitude depends on the frozen monetary mapping and risk policy; it cannot be described as realized monetary benefit, regret, or causal effect.

### 6.4 Metrics outside the scientific endpoint set

- `DECISION_CVAR_DIFFERENCE` may be retained by the current implementation as a policy/contract diagnostic when the frozen M4 policy makes it available, but it is not a primary or secondary scientific endpoint under this protocol and must not be promoted into an Exp2 claim.
- `STATE_CRPS`, calibration, uncertainty-preservation proxies, and runtime are not part of this freeze and remain `NOT_RUN` unless separately specified.
- No substitute metric, raw-CU ranking, post-hoc threshold, or best-variant metric may be created during execution.

## 7. Execution gate checklist

### READY

The following protocol decisions are frozen:

- scientific question: representation sensitivity under fixed downstream conditions;
- claim class: scenario-conditioned, conditional, non-causal, non-authoritative;
- registered representation families and their references;
- minimum of two common ranked actions per admitted node;
- mandatory `A00` baseline plus at least one eligible non-A00 action;
- requirement for one content-addressed action-set manifest shared across variants;
- M3 interpretation `SCENARIO_ASSUMPTION` for non-A00 responses;
- weakest-support inheritance for the multi-action metric;
- constructed-internal-loss-unit monetary interpretation;
- conditional metric-level authority and prohibition on authoritative recommendation claims;
- primary metrics `DECISION_ACTION_DISAGREEMENT` and `DECISION_RANKING_CHANGE`;
- secondary metric `DECISION_RISK_DIFFERENCE`;
- paired `variant - reference` direction and episode-balanced scientific aggregation;
- no retraining, M2 reconstruction, variant-specific downstream changes, numerical tuning, or silent fallback.

The Exp2 representation adapters, fixed-binding manifest surface, M3-then-M4 interface, identity/hash guards, and metric formulas are engineering-ready for these roles.

### BLOCKED

Exp2 execution remains blocked until all of the following concrete inputs or closures exist:

1. a frozen dataset/split/cohort/decision-node manifest and authorized execution tier;
2. a content-addressed action-set manifest satisfying this protocol, including the exact non-A00 membership;
3. complete typed, executable non-A00 `ActionResponseRule` artifacts consistent with `SCENARIO_ASSUMPTION`, including rule hashes and provenance;
4. complete supported seven-component M2-to-M3 consequence coverage for every included action and scenario;
5. an adapter-facing M3 artifact that binds per-action rules, provenance, and support rather than only registry hashes;
6. a complete, frozen, non-test M4 monetary mapping with seven-component coverage and the narrow interpretation specified above;
7. a complete frozen residual-risk/CVaR policy, including all numerical values, source justification, positive-tail decision, provenance, and content hash;
8. an adapter-facing M4 artifact that validates the complete mapping and policy content rather than only asserted status strings and hashes;
9. verification that every admitted paired node has A00 plus at least one common non-A00 numerical M4 evaluation and no `NOT_RANKED` member;
10. reporting enforcement that labels the multi-action output conditional/partial and limits claims and endpoints to this protocol.

No blocker may be closed with defaults, test-only artifacts, historical result values, manual consequence reconstruction, or post-hoc parameter selection.

## 8. Stopping and invalidation rules

Execution must stop before metric generation if any fixed artifact identity differs across variants, the action set or response-rule map changes, a mapping/policy is missing or unfrozen, a future-information boundary is violated, or a required artifact relies on silent fallback.

A produced result is invalid for this protocol if it:

- omits A00 or has fewer than two common ranked actions at an admitted node;
- mixes variant-specific actions, response rules, monetary mappings, or risk policies;
- labels scenario-assumption comparisons authoritative or supported;
- interprets internal units as real money;
- treats scenarios as independent empirical observations;
- reports metrics outside the frozen endpoint hierarchy as Exp2 scientific claims.

## 9. Authorization boundary

This protocol freeze does not authorize an Exp2 run. After the blocked artifacts are supplied and independently validated, execution still requires an explicit human run authorization. Final Test access, `paper_full`, parameter selection, variant selection by outcome, and result promotion remain outside this document.

No model, registry, execution adapter, experiment output, or scientific result was changed or generated by this protocol freeze.
