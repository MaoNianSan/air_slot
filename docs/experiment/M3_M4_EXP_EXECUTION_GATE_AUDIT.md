# M3/M4 Exp2 Execution Gate Audit V1

## Audit scope and conclusion

Audit basis: repository HEAD `9ba4835590718265110d6b5d99be720a0fd712ad`, with a clean worktree before this document was created.

Inspected read-only:

- `model/M3/`;
- `model/M4/` and `model/common/monetary_system.py`;
- `registries/action_templates.yaml`;
- `registries/m3_response_scenarios.yaml`;
- `registries/m3_v2_action_response_design.json`;
- `registries/m4_v2_monetary_mapping_design.json`;
- `exp/exp2/protocol.py`, `evaluator.py`, and `execution/`.

`OVERALL_STATUS = SCIENTIFIC_GATE_REQUIRED`

The M3/M4 typed interfaces, registry hashing, Exp2 artifact loader, manifest, and identity-locking adapter are engineering-ready. They are not sufficient scientific artifacts. The minimum remaining closure is:

1. freeze an actual common action comparison set and a complete typed response rule for every included action, with per-action provenance and support;
2. freeze a complete authoritative seven-component monetary mapping;
3. freeze the residual-risk/CVaR policy, including the positive-tail decision;
4. require and verify the intended ranking authority before accepting Exp2 metrics.

No parameter values or action subset are selected by this audit.

## Status definitions

| Status | Meaning in this audit |
| --- | --- |
| `READY` | Complete for the stated role and can be consumed without an additional scientific choice |
| `ENGINEERING_ONLY` | Reproducible code/schema/test or scenario artifact, but not authoritative scientific support |
| `SCIENTIFIC_GATE_REQUIRED` | A human scientific freeze, support decision, or missing authoritative artifact is required |

## 1. Exact M3 artifacts required

### 1.1 Frozen action set

The execution artifact must contain an ordered, unique set of action IDs and bind it to:

- `ActionRegistry.registry_id`;
- schema version;
- structural `registry_hash`;
- source SHA-256 or equivalent source-artifact identity;
- dataset/cohort/split and decision-node applicability;
- eligibility/instantiability rules and their provenance;
- one stable action-set hash;
- the explicit action IDs admitted to the comparison.

The current structural registry is:

- registry ID: `ACTION_TEMPLATES_V1`;
- registry hash: `sha256:2057a4fc274eb9eb7b820365f5b85ff1d0d3f9ea96549e8618842c740f987716`;
- 23 structural templates: `A00`, 22 non-A00 actions;
- structural response parameter status: A00 `NOT_REQUIRED`, all 22 non-A00 templates `NOT_FROZEN`.

The 23-template library is not itself the executable action set. `instantiate_candidates` removes known-false or non-instantiable actions at a decision node, so a claim about a supported subset must freeze the actual comparison membership rather than equate it with the structural catalog.

`ACTION_REGISTRY_STRUCTURE = READY`

`EXP2_EXECUTABLE_ACTION_SET = SCIENTIFIC_GATE_REQUIRED`

### 1.2 Frozen response registry and per-action rules

For each action in the frozen comparison set, the required scientific artifact is a typed `ActionResponseRule` with:

- response rule ID and SHA-256 rule hash;
- action ID and action family;
- affected components and response types;
- named response rule;
- parameter source;
- support state;
- source references;
- parameter version and freeze ID;
- named parameters, if applicable;
- complete provenance.

The artifact set must also carry the response registry ID/hash and a deterministic action-to-rule-hash map. The same map must be used for every Exp2 variant. An action registry hash alone does not prove response support.

Current response scenario registry:

- registry ID: `M3_RESPONSE_SCENARIO_V1`;
- registry hash: `sha256:ff8adb3034603ec225930ed9187bc296b46d58637a974c9de64b341248755ce0`;
- declared status: `HUMAN_APPROVED_SCENARIO_SPECIFICATION`;
- A00: deterministic, `NOT_REQUIRED`, `OPERATOR_INDUSTRY`;
- 22 non-A00 actions: parameters marked `FROZEN`, provenance `PURE_SCENARIO`;
- `formal_support_upgrade=false`.

This registry is reproducible for scenario/sensitivity work, but it cannot be relabelled as empirical or otherwise unconditional treatment-effect support. The M3 README also states that only the A00 identity path is executable in the current V2 action-response implementation; non-A00 component response mappings remain gated.

`A00_TYPED_IDENTITY_RULE = READY`

`M3_RESPONSE_SCENARIO_V1 = ENGINEERING_ONLY`

`NON_A00_TYPED_SUPPORTED_RESPONSE_RULES = SCIENTIFIC_GATE_REQUIRED`

### 1.3 Provenance

Minimum per-action provenance must bind:

- evidence/source class;
- source references;
- parameter version and freeze ID;
- response registry ID/hash;
- response rule ID/hash;
- action eligibility provenance;
- baseline M2 CU artifact and reference-lineage hashes;
- response provenance propagated into `ActionEvaluationEnvelope` and then M4.

`SCENARIO_ASSUMPTION` and `EXPERT_JUDGEMENT` cannot be labelled `SUPPORTED` by `ActionResponseRule`. `PURE_SCENARIO` maps to conditional/scenario support, not unconditional scientific support.

`M3_PROVENANCE_SCHEMA = READY`

`NON_A00_AUTHORITATIVE_PROVENANCE = SCIENTIFIC_GATE_REQUIRED`

### 1.4 Support state

M3 exposes `SUPPORTED`, `REFERENCE_BASED`, `SCENARIO_ASSUMPTION`, and `ABSTAIN` in the typed V2 response boundary.

- `SUPPORTED` is required for M4 to produce `AUTHORITATIVE` ranking authority.
- `REFERENCE_BASED` or `SCENARIO_ASSUMPTION` can produce only assumption-based/conditional M4 outputs even if the mapping and risk policy are executable.
- `ABSTAIN` produces no ranked risk metric.
- every included action must also preserve non-abstained seven-component M2 support through its action-conditioned consequence vector.

For a fully supported Exp2 comparison, every included action in every variant must yield `ResponseSupportClass.SUPPORTED`; otherwise Exp2 metric support is at most `PARTIAL` or `NOT_RUN`.

`M3_SUPPORTED_MULTI_ACTION_SET = SCIENTIFIC_GATE_REQUIRED`

### 1.5 Gap in the current Exp2 execution artifact

The current `M3ArtifactPayload` contains only:

- ordered action IDs;
- action registry hash;
- response registry hash.

It does not contain per-action response rule hashes, provenance, or support states. `Exp2DownstreamExecutor` compares rule hashes only after M3 callables run. Therefore the current loader can lock engineering identity, but it cannot pre-certify scientific M3 closure from the artifact alone.

`EXP2_M3_ARTIFACT_BINDING = ENGINEERING_ONLY`

Minimum adapter-facing closure requires either:

1. serialize the complete validated `ActionResponseRule` objects and action-to-rule map in the content-addressed M3 artifact; or
2. bind a content-addressed manifest that points to those typed objects and records their support/provenance exactly.

## 2. Exact M4 artifacts required

### 2.1 Monetary mapping

The required artifact is a complete `MonetaryMappingRegistry`, not only a hash/status assertion. It must contain:

- monetary system ID;
- registry ID, version, and content hash;
- `freeze_status=FROZEN`;
- freeze ID, reference period, and provenance;
- exactly one mapping for each of the seven consequence components;
- for each rule: component ID, mapping function, named parameters and units, parameter version, source type, references, freeze ID, provenance, rule ID, and rule hash;
- no `TEST_ONLY` source;
- `final_test_access_count=0` and `paper_full_run=false` before an authorized run.

M4 refuses evaluated metrics if mapping coverage is incomplete or M3 CU support abstains. `TEST_ONLY` mappings are executable for contract tests but can never be authoritative scientific mappings.

Current repository status:

- registry: `M4_MONETARY_MAPPING_DESIGN_V2`;
- `scientific_status=SCIENTIFIC_DECISION_REQUIRED`;
- `production_mapping_enabled=false`;
- all seven component statuses are `ABSTAIN`;
- human gate: `MONETARY_MAPPING_FREEZE_REQUIRED`.

`M4_MAPPING_SCHEMA_AND_CODE = ENGINEERING_ONLY`

`M4_AUTHORITATIVE_MONETARY_MAPPING = SCIENTIFIC_GATE_REQUIRED`

### 2.2 Residual-risk policy

The required artifact is a complete `ResidualRiskPolicy` with:

- alpha;
- expected-loss coefficient;
- CVaR coefficient;
- coefficients summing to 1;
- risk metric version;
- `policy_status=FROZEN`;
- freeze ID;
- tail support state;
- tail references and provenance;
- content-derived policy hash.

No values may be inferred from defaults, tests, old outputs, or this audit.

`M4_RESIDUAL_RISK_IMPLEMENTATION = ENGINEERING_ONLY`

`M4_FROZEN_RISK_POLICY = SCIENTIFIC_GATE_REQUIRED`

### 2.3 CVaR policy

CVaR is not a separate free-floating score in M4. It is governed inside the residual-risk policy by:

- a frozen `alpha`;
- the declared upper-loss tail convention;
- `TailSupportState.SUPPORTED`;
- named tail references/provenance;
- the frozen objective coefficient assigned to CVaR;
- the same scenario weights as the M3 envelope.

`evaluate_residual_risk` rejects `TailSupportState.UNRESOLVED` with `M1_POSITIVE_TAIL_DECISION_REQUIRED`. The code implements weighted upper-loss VaR/CVaR with fractional mass at the quantile boundary, but implementation alone does not select or justify alpha, the tail-support decision, or the objective weight.

`M4_CVAR_ALGORITHM = ENGINEERING_ONLY`

`M4_CVAR_SCIENTIFIC_POLICY = SCIENTIFIC_GATE_REQUIRED`

### 2.4 Ranking authority

Ranking authority is derived output state, not a parameter to choose:

- `AUTHORITATIVE`: M3 response support is `SUPPORTED`, the monetary mapping is scientifically `FROZEN` and authoritative, the risk policy is `FROZEN`, all seven mappings/CU values are available, and the output is fully evaluated;
- `CONDITIONAL`: numerical risk is available, but response or configuration is assumption-based/test-only/non-authoritative;
- `NOT_RANKED`: mapping, response, CU coverage, or other required support is unavailable.

`rank_risk_evaluations` keeps authoritative and conditional rankings separate. It requires all compared risk envelopes to share monetary system, mapping hash, and policy hash.

For Exp2 metrics to receive common-schema `SUPPORTED`, all relevant M4 envelopes must be `AUTHORITATIVE`. Conditional outputs are retained but Exp2 marks their metrics `PARTIAL`; not-ranked outputs make metrics unavailable.

`M4_RANKING_AUTHORITY_LOGIC = READY`

`AUTHORITATIVE_RANKING_INPUTS = SCIENTIFIC_GATE_REQUIRED`

### 2.5 Gap in the current Exp2 execution artifact

The current `M4ArtifactPayload` contains only:

- monetary mapping hash and enum status;
- risk policy hash and enum status.

The loader requires both status strings to be `FROZEN`, but it does not deserialize and validate the complete `MonetaryMappingRegistry` or `ResidualRiskPolicy`. It therefore cannot prove seven-component coverage, rule provenance, alpha, coefficients, tail support/reference, or authoritative source class before execution.

`EXP2_M4_ARTIFACT_BINDING = ENGINEERING_ONLY`

Minimum adapter-facing closure requires a content-addressed serialized mapping registry and risk policy, or a manifest binding those exact typed objects. A self-declared `FROZEN` string plus arbitrary hash is not sufficient scientific evidence.

## 3. Consolidated readiness classification

| Artifact/capability | Status | Reason |
| --- | --- | --- |
| M3 structural action registry loader/hash | `READY` | typed, deterministic, current 23-template identity verified |
| Actual Exp2 action comparison set | `SCIENTIFIC_GATE_REQUIRED` | must be frozen for cohort/node scope; structural catalog is not the evaluated set |
| A00 identity response path | `READY` | current V2 executable identity path |
| Non-A00 scenario response registry | `ENGINEERING_ONLY` | reproducible `PURE_SCENARIO`; `formal_support_upgrade=false` |
| Non-A00 typed component response mappings | `SCIENTIFIC_GATE_REQUIRED` | current V2 implementation and authoritative evidence are absent |
| M3 provenance/support schemas | `READY` | typed and propagated |
| Current Exp2 M3 summary artifact | `ENGINEERING_ONLY` | lacks per-action rules, provenance, and support states |
| M4 monetary mapping/risk code | `ENGINEERING_ONLY` | implementation exists, no production scientific parameters |
| Production seven-component monetary mapping | `SCIENTIFIC_GATE_REQUIRED` | design registry disabled; seven components abstain |
| Residual-risk policy | `SCIENTIFIC_GATE_REQUIRED` | no frozen scientific artifact supplied |
| Weighted CVaR algorithm | `ENGINEERING_ONLY` | formula implemented, scientific tail policy unresolved |
| Ranking-authority enforcement | `READY` | authoritative/conditional/not-ranked states are explicit |
| Authoritative M4 ranking inputs | `SCIENTIFIC_GATE_REQUIRED` | supported M3 + frozen authoritative mapping/policy unavailable |
| Exp2 manifest/hash/binding guards | `READY` for engineering identity | do not by themselves prove scientific support |

## 4. Can Exp2 run with each action-set option?

| Option | Engineering invocation | Supported scientific Exp2 execution | Exact reason |
| --- | --- | --- | --- |
| A00 only | `YES`, for identity/interface checks | `NO` for the required comparison metrics | only current V2 response path; one action makes ranking change `NOT_RUN` because at least two common ranked actions are required; action disagreement is trivially zero and not a meaningful multi-action comparison |
| Frozen supported subset | `YES` after binding | `YES`, after all M3/M4 gates close | code-level minimum is at least two identical common action IDs across all variants, each with supported typed response and complete seven-component M4 evaluation; exact membership, including whether A00 is mandatory, is a scientific protocol freeze not selected here |
| Full 23-template set | `NO` currently | `NO` currently; also not the minimum requirement | 22 structural templates remain `NOT_FROZEN`; their separate scenario parameters do not upgrade formal support; per-node eligibility may legitimately exclude actions, so forcing the full catalog would conflate library scope with comparison scope |

The minimum executable scientific action set is therefore a frozen, identical, supported subset of at least two actions. The current code does not require A00 in that subset, although A00 is the framework baseline; whether to require it must be frozen explicitly by the scientific protocol.

## 5. Can Exp2 produce decision-level or risk-level metrics?

### Decision-level metrics only

Current Exp2 does not have an M3-only decision evaluator. `DECISION_ACTION_DISAGREEMENT` and `DECISION_RANKING_CHANGE` are computed from `RiskEvaluationEnvelope.residual_risk_objective`, so they still require M4 mapping, risk policy, and ranked outputs.

- A00 only: action disagreement can mechanically evaluate to zero if risk exists, but ranking change is `NOT_RUN`; the Exp2 result remains blocked.
- At least two common conditional rankings: numeric metrics can be produced as `PARTIAL`, not supported scientific evidence.
- At least two common authoritative rankings under the same mapping/policy: decision metrics can be `SUPPORTED`.
- Without M4: decision metrics are `NOT_RUN`; using raw CU or an alternative action score would bypass the frozen protocol.

`DECISION_LEVEL_METRICS_NOW = SCIENTIFIC_GATE_REQUIRED`

### Risk-level metrics

`DECISION_RISK_DIFFERENCE` and `DECISION_CVAR_DIFFERENCE` are conceptually risk metrics but are stored at `MetricLevel.DECISION` because the common V1 schema has no separate risk level.

They require:

- the same supported action set and response rules across variants;
- complete supported seven-component action consequences;
- one authoritative frozen monetary mapping;
- one frozen residual-risk/CVaR policy with supported tail decision;
- the same mapping hash, policy hash, and alpha across reference/variant envelopes;
- authoritative ranking support for fully supported metrics.

Conditional M4 outputs yield `PARTIAL`; abstained/not-ranked outputs yield `NOT_RUN`.

`RISK_LEVEL_METRICS_NOW = SCIENTIFIC_GATE_REQUIRED`

## Minimum closure checklist before Exp2 execution

The smallest closure that can support the current required Exp2 decision/risk metrics is:

1. freeze one cohort/split-specific action-set manifest with at least two common action IDs;
2. provide a complete typed `ActionResponseRule` for every included action;
3. freeze the action-to-rule map, response registry hash, provenance, support state, parameter version, and freeze ID;
4. require non-abstained seven-component M2/M3 support for each included action and scenario;
5. serialize and validate a complete `MonetaryMappingRegistry` with `FROZEN` authoritative status and seven-component coverage;
6. serialize and validate a complete `ResidualRiskPolicy` with `FROZEN` status;
7. resolve and freeze alpha, objective coefficients, `TailSupportState.SUPPORTED`, tail references, and the named positive-tail decision;
8. state whether the accepted claim requires `AUTHORITATIVE` rankings; the current fully supported Exp2 result does;
9. extend or supplement the execution artifacts so the adapter can verify full M3 support/provenance and full M4 mapping/policy content before execution;
10. obtain separate authorization for the execution tier.

Until these gates close:

`EXP2_SCIENTIFIC_EXECUTION = BLOCKED`

`EXP2_ENGINEERING_BINDING = READY`

`EXP2_SCIENTIFIC_RESULTS = NOT_RUN`

## Audit restrictions observed

- no `model/M3` or `model/M4` changes;
- no registry changes;
- no execution adapter changes;
- no parameter or action-set selection;
- no experiment, M3/M4 execution, ranking, metric production, or scientific result generation.
