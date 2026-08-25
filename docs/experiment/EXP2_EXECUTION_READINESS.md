# Exp2 Execution Readiness Closure V1

## Closure status

`EXP2_EXECUTION_READINESS_STATUS = CONTRACT_AUDITED_EXECUTION_BLOCKED`

Audit basis: repository HEAD `f66ef8b8670ebd990f32f1e04deff8a11e00d93c` with a clean worktree before this document was created.

This closure audits the code path that would precede an Exp2 execution. It does not authorize or report a Development, Final Test, `paper_full`, scientific, or paper-result run. Engineering availability, metric availability, scientific support, and claim authority are reported separately.

## A. Scientific question

How much information structure is required for downstream recovery decision evaluation?

Exp2 compares controlled representations of one frozen M1/M2 evidence chain. It does not compare separately trained models. The comparison factor is representation only; model identity, model parameters, source cohort, downstream action/response rules, monetary mapping, risk policy, and evaluator definitions must remain fixed.

## B. Implemented variants

| Family | Variant | Implemented transformation | Family reference | Engineering status |
| --- | --- | --- | --- | --- |
| Exp2A | `EXP2A_COLLAPSED` | One weighted expected `D_OB`/`D_TX`/`D_TO` state with weight 1 and unioned source lineage | `EXP2A_JOINT` | `CODE_READY` |
| Exp2A | `EXP2A_MARGINAL` | Independent field permutation within equal-weight strata; weighted marginals and field-source IDs retained | `EXP2A_JOINT` | `CODE_READY_WITH_EQUAL_WEIGHT_STRATUM_REQUIREMENT` |
| Exp2A | `EXP2A_JOINT` | Identity-preserving normalized joint scenario view | `EXP2A_JOINT` | `CODE_READY` |
| Exp2B | `EXP2B_SCALAR` | Sum of already emitted CU values across all seven required components; null if support is incomplete | `EXP2B_COMPONENT` | `CODE_READY_AS_REPRESENTATION_ONLY` |
| Exp2B | `EXP2B_CHANNEL` | Sum of already emitted CU values within `Flight`, `Passenger`, and `Resource`; null if channel support is incomplete | `EXP2B_COMPONENT` | `CODE_READY_AS_REPRESENTATION_ONLY` |
| Exp2B | `EXP2B_COMPONENT` | Preserve the exact seven M2-emitted components | `EXP2B_COMPONENT` | `CODE_READY` |

The scalar and channel outputs are experiment representations, not new M2 formal estimands, monetary quantities, or scientific evidence by themselves.

## C. Required frozen inputs

No execution is admissible until one identity-complete set of the following inputs is supplied.

| Input | Required identity/support | Current closure |
| --- | --- | --- |
| Dataset and cohort | dataset ID, cohort membership/hash, split, decision-node set | `REQUIRED_NOT_SUPPLIED_FOR_THIS_CLOSURE` |
| M1 source | typed `M1V2Scenario` bundle or schema-validated serialization; model version; calibration version; artifact version; scenario hash; seed; causal-cutoff provenance | interface exists; concrete frozen execution artifact not supplied |
| M2 source | one frozen `ScenarioConsequenceDistribution`; exact seven-component ontology; CU normalization and reference lineage; artifact version/hash | interface exists; concrete frozen execution artifact not supplied |
| M3 action response | fixed candidate action IDs and one frozen response-rule hash per action; current typed `ActionEvaluationEnvelope` output | abstract Exp2 boundary exists; supported multi-action frozen executor not supplied |
| M4 evaluation | frozen production monetary mapping and registry hash; frozen residual-risk policy/hash; alpha; ranking authority | typed interface exists; production mapping/policy inputs not supplied |
| Evaluation contract | fixed metric IDs, formulas, units, support rules, and observation source where required | decision/risk metrics implemented; state contract incomplete |
| Reproducibility | Git HEAD, configuration hash, seed, model versions, artifact versions, source hashes | schema surfaces exist; values must be bound at run time |

Test-only mappings, scenario assumptions, legacy five-component outputs, arbitrary serialized rows without trusted source provenance, and precomputed scalar variant scores do not satisfy the frozen-input contract.

## Input contract check

### M1 fields

`ScenarioRepresentationAdapter` consumes and validates:

- `scenario_id`;
- `scenario_weight`;
- `D_OB`;
- `D_TX`;
- `D_TO`;
- non-empty lineage.

It also checks unique scenario IDs, positive normalized weights, nonnegative delays, source `D_TO = D_OB + D_TX`, a SHA-256 source identity, and post-transform source immutability. Typed `M1V2Scenario` uses `d_ob_minutes`, `d_tx_minutes`, derived `d_to_minutes`, and `scenario_seed_key`; the adapter maps these to the Exp2 surface.

`INPUT_FIELD_CONTRACT = PASS`

### Future-information boundary

The producing M1 path is causal: M1 sequence validation rejects `information_cutoff > decision_time`, and factual replay accepts only cutoff-legal observations. Exp2 itself neither queries raw observations nor adds fields after the decision time.

However, the Exp2 adapter also accepts schema-compatible dictionaries containing only values and a lineage string. Those rows do not independently prove the producing cutoff, dataset manifest, or model/calibration identity. Therefore a future run must accept only a trusted typed M1 bundle or a serialized artifact accompanied by its frozen manifest and causal-cutoff provenance.

`NO_FUTURE_INFORMATION_LEAKAGE = CONDITIONAL_PASS_REQUIRES_TRUSTED_M1_ARTIFACT`

### Consequence construction boundary

Exp2 reads the exact M2-emitted component vector and `constructed_value_cu`. It does not import M2 drivers, modify native quantities, run CU normalization, or reconstruct consequences from delay fields.

`NO_MANUAL_CONSEQUENCE_RECONSTRUCTION = PASS`

## Representation contract check

The Exp2A transformations reside in `exp/exp2/representation.py` and do not import or invoke model training, optimization, calibration, or parameter mutation code.

| Check | Evidence | Status |
| --- | --- | --- |
| Representation-only factor | variant registry declares one changed factor and fixed model/artifact/action/risk factors | `PASS` |
| No retraining | transformations operate on normalized frozen samples only; result provenance records `model_retrained=false` | `PASS` |
| No model parameter change | no `model/` write path exists in the adapter/protocol; model versions are result provenance | `PASS` |
| No source mutation | source content hash is recomputed after each transform | `PASS` |
| No lineage loss | JOINT retains row lineage; MARGINAL records source ID for every field and unions used lineage; COLLAPSED carries all source lineage | `PASS` |
| Weighted marginal preservation | MARGINAL checks the weighted marginal of all three fields exactly | `PASS_WITH_EQUAL_WEIGHT_STRATUM_REQUIREMENT` |

`REPRESENTATION_CONTRACT = PASS_WITH_DECLARED_MARGINAL_APPLICABILITY_CONDITION`

## M2 aggregation contract check

`ConsequenceRepresentationAdapter` requires the canonical seven components and their M2-emitted channel, value, support, and reference lineage.

| Prohibited change | Check | Status |
| --- | --- | --- |
| Native quantity modification | `native_quantity` is not consumed or written | `PASS` |
| CU recalculation | adapter reads `constructed_value_cu`; it does not call normalization rules or derive CU from native quantities | `PASS` |
| Missing-value zero fill | incomplete support yields null `ABSTAINED` aggregates | `PASS` |
| New model assumption | component grouping uses M2 aspect labels; sums are the frozen representation operation requested by Exp2 | `PASS_AS_REPRESENTATION_ONLY` |

The sum operation must not be relabelled as a formal M2 estimand, real money, or an authoritative risk value.

`M2_CONTRACT = PASS_AS_AGGREGATION_ONLY`

## D. Downstream interfaces

Every variant is routed through the same `Exp2DownstreamInterface` instance:

1. `run_m3` returns current typed `ActionEvaluationEnvelope` objects.
2. `run_m4` receives those M3 outputs and returns current typed `RiskEvaluationEnvelope` objects.

The protocol verifies that M4 action IDs equal the M3 action IDs, every M4 envelope cites the exact M3 envelope hash, and reference/variant M3 outputs have identical action-to-response-rule hashes. The evaluator rejects different M4 monetary mapping hashes, risk-policy hashes, alpha values, or action sets. M4 owns ranking; Exp2 does not implement an alternative ranking rule.

| Invariant | Status |
| --- | --- |
| Same M3 action-response interface | `PASS_AT_ABSTRACT_TYPED_BOUNDARY` |
| Same M4 residual-risk interface | `PASS_AT_ABSTRACT_TYPED_BOUNDARY` |
| No action modification | `PASS_ENFORCED` |
| No response-registry modification | `PASS_ENFORCED_BY_ACTION_TO_RULE_HASH_MAP` |
| No monetary-mapping modification | `PASS_ENFORCED_BY_REGISTRY_HASH` |
| No risk/ranking-policy modification | `PASS_ENFORCED_BY_POLICY_HASH_AND_ALPHA` |
| No M4 bypass | `PASS_ENFORCED_BY_M3_ENVELOPE_HASH` |

The abstract interface is not a concrete executable scientific chain. Current M3 code provides the frozen A00 identity path but no supplied supported multi-action Exp2 executor. No production M4 monetary mapping or frozen execution risk policy was supplied. These remain hard execution blockers.

`M3_M4_CONTRACT = INTERFACE_CLOSED_EXECUTION_INPUTS_BLOCKED`

## E. Allowed metrics

The allowed metric contract distinguishes names/interfaces from executable formulas.

| Requested level | Metric | Current implementation/support | Closure decision |
| --- | --- | --- | --- |
| Decision | action disagreement | `DECISION_ACTION_DISAGREEMENT`; implemented from common supported M4 rankings | `FROZEN_WHEN_M4_SUPPORTED` |
| Decision | ranking change | `DECISION_RANKING_CHANGE`; implemented as pairwise ranking reversal rate | `FROZEN_WHEN_M4_SUPPORTED` |
| Decision/risk | risk difference | `DECISION_RISK_DIFFERENCE`; paired mean M4 residual-risk difference, variant minus reference | `FROZEN_WHEN_M4_SUPPORTED` |
| Risk, conditional | CVaR difference | `DECISION_CVAR_DIFFERENCE`; prior allowed extension, executable only when M4 CVaR is supported | `CONDITIONAL_ALLOWED` |
| State | calibration | common interface `STATE_CALIBRATION` exists, but Exp2 has no attached evaluator, formula, unit, or observation contract | `NOT_FROZEN_NOT_RUN` |
| State | uncertainty preservation | current Exp2 exposes `STATE_CRPS=NOT_RUN`; no separate frozen uncertainty-preservation formula or observation contract exists | `NOT_FROZEN_NOT_RUN` |
| System | runtime | common interface `SYSTEM_RUNTIME` exists; Exp2 does not currently attach or report it | `NOT_APPLICABLE_UNLESS_EXECUTION_PROTOCOL_FREEZES_IT` |

`STATE_CRPS` must not be silently treated as both calibration and uncertainty preservation. No proxy, substitute formula, or synthetic value may be introduced during execution. State metrics remain `NOT_RUN` until their definitions and observation sources are separately frozen.

`METRIC_CONTRACT = PARTIAL_DECISION_RISK_FROZEN_STATE_BLOCKED_SYSTEM_OPTIONAL`

## Result contract check

The returned type is `exp.common.result_schema.ExperimentResult`. It contains:

| Required concept | Schema location | Status |
| --- | --- | --- |
| `experiment_id` | top-level `experiment_id`, fixed to `EXP2` by reporter | `PASS` |
| `variant_id` | top-level `variant_id` | `PASS` |
| `artifact_version` | canonical top-level map `artifact_versions["EXP2_SOURCE_ARTIFACT"]`; singular value is also copied to provenance | `PASS_WITH_COMMON_SCHEMA_PLURAL_MAP` |
| `scenario_hash` | top-level SHA-256 `scenario_hash` | `PASS` |
| `metrics` | top-level metric observation map | `PASS` |
| `support_status` | top-level `SupportStatus` | `PASS` |

The common schema deliberately uses `artifact_versions` because the result binds both M1 and M2 identities. Adding an unversioned parallel top-level field is not authorized by this closure.

`RESULT_CONTRACT = PASS_WITH_DOCUMENTED_ARTIFACT_VERSION_MAPPING`

## F. Blocked claims

Until all frozen inputs and metric gates above are satisfied, Exp2 must not claim:

- how much information is scientifically sufficient;
- that one representation or model is superior or best;
- causal, policy, or operational benefit;
- supported multi-action disagreement or ranking change;
- authoritative residual-risk or CVaR differences;
- real-money/RMB cost without an authoritative monetary mapping;
- state calibration or uncertainty preservation;
- runtime improvement without a frozen runtime measurement protocol;
- paper eligibility, Final Test evidence, or a paper result.

Engineering tests prove contract behavior only. They do not close scientific support.

## Execution gate

Before any Exp2 execution, all of the following must be supplied and approved:

1. a trusted frozen M1 scenario artifact and causal-cutoff manifest;
2. its aligned frozen seven-component M2 artifact;
3. a supported frozen multi-action M3 action set and response registry;
4. an authoritative frozen M4 monetary mapping and executable frozen risk policy;
5. frozen definitions and observation sources for calibration and uncertainty preservation, or an explicit approved decision removing them from the required run;
6. dataset/cohort/split/config identities and a run seed;
7. separate human authorization for the requested execution tier.

`FINAL_EXECUTION_GATE = CLOSED_DOCUMENTATION_COMPLETE_EXECUTION_NOT_READY`

## Validation record

| Check | Result |
| --- | --- |
| `python -m pytest tests/experiments/test_exp2 -q` | `PASS: 7 passed in 0.19s` |
| `python -m compileall -q exp/exp2 tests/experiments/test_exp2` | `PASS` |
| `git diff --check` | `PASS` |
| `git status --short -- model PRE` | `PASS: no model/PRE worktree changes` |

No paper experiment, full result generation, model training, calibration, variant selection, commit, or push was performed.
