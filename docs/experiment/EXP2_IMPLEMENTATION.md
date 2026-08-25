# Exp2 Information-Sufficiency Implementation

## Status

`EXP2_IMPLEMENTATION_STATUS = CODE_READY_SCIENTIFIC_EXECUTION_BLOCKED`

The six frozen representation variants and their experiment-layer adapters are implemented. No paper experiment, variant selection, parameter tuning, M1 retraining, M2 recomputation, scientific comparison, or paper-result promotion has been run.

The current model boundary still blocks a scientific end-to-end comparison: non-A00 M3 response is not frozen, and M4 does not have the production monetary mapping and risk-policy freezes required for supported ranking. The implementation preserves those gates rather than substituting legacy action scores, manual CU arithmetic, or test-only money scales.

## Implemented package

| File | Responsibility |
| --- | --- |
| `exp/exp2/variants.py` | Frozen six-variant registry and claim scopes |
| `exp/exp2/representation.py` | Immutable M1 scenario and M2 consequence representation adapters |
| `exp/exp2/protocol.py` | Common prepare/run/evaluate/report lifecycle and mandatory M3 then M4 interface |
| `exp/exp2/runner.py` | Typed in-memory and content-addressed manifest execution entries; legacy scalar-row execution is limited to smoke mode |
| `exp/exp2/evaluator.py` | Common evaluator metrics over paired M4 envelopes |
| `exp/exp2/reporting.py` | `exp/common/result_schema.py` result construction and common reporters |

The legacy `exp/exp2/representations.py` remains unchanged for historical callers. It is not the V1 information-sufficiency execution entry.

## Variant registry

| Variant | Transformation | Fixed inputs |
| --- | --- | --- |
| `EXP2A_JOINT` | Identity-preserving view of the frozen weighted M1 joint samples | M1 model/calibration, M2 artifact, cohort, seed, action set, response registry, monetary mapping, risk policy |
| `EXP2A_MARGINAL` | Deterministic independent field permutation within equal-weight strata | Same as above |
| `EXP2A_COLLAPSED` | One weighted expected consequence state with weight 1 | Same as above |
| `EXP2B_COMPONENT` | Preserve all seven M2-emitted components | Same as above |
| `EXP2B_CHANNEL` | Aggregate M2-emitted CU values into `Flight`, `Passenger`, and `Resource` | Same as above |
| `EXP2B_SCALAR` | Aggregate all seven M2-emitted CU values into one scalar representation | Same as above |

Every registry item contains `variant_id`, `description`, `changed_factor`, `fixed_factor`, and `claim_scope`. The registry defines representation comparisons only; it does not encode a preferred variant.

## M1 scenario adapter

`ScenarioRepresentationAdapter` accepts typed `M1V2Scenario` instances or schema-compatible serialized rows. Its experiment surface is exactly:

- `scenario_id`;
- `scenario_weight`;
- `D_OB`;
- `D_TX`;
- `D_TO`;
- non-empty lineage.

The adapter validates unique scenario identity, normalized positive weights, nonnegative delays, and the source identity `D_TO = D_OB + D_TX` when values are present. It hashes the normalized frozen source before transformation and rechecks the hash after transformation.

`JOINT` deep-copies every sample without changing identity, weight, values, or lineage. `MARGINAL` preserves each weighted marginal exactly and records the source scenario for each field. Exact weighted preservation permits permutation only within equal-weight strata; if a nontrivial weighted permutation is impossible, the adapter stops with `EXP2_MARGINAL_WEIGHTED_PERMUTATION_UNAVAILABLE`. `COLLAPSED` computes the weighted expectation for each declared consequence field and carries the union of all source lineages. It does not add a distributional assumption.

## M2 consequence adapter

`ConsequenceRepresentationAdapter` accepts typed `ScenarioConsequenceDistribution` output or schema-compatible serialized consequences. It requires the exact seven-component ontology in canonical order and uses only M2-emitted `constructed_value_cu`, support, aspect, scenario weight, and reference lineage.

The adapter does not call M2 drivers or CU normalization. `CHANNEL` and `SCALAR` perform experiment-layer sums of already emitted CU values. If any required input component is abstained or null, the aggregate remains null and `ABSTAINED`; missing values are never treated as zero. These aggregates are representation degradations, not new M2 formal estimands and not monetary values.

## Downstream interface

All six variants use the same `Exp2DownstreamInterface` object:

1. `run_m3(...)` must return current `model.M3.action_response.ActionEvaluationEnvelope` objects.
2. `run_m4(...)` must consume those exact M3 envelope hashes and return current `model.M4.residual_risk.RiskEvaluationEnvelope` objects.

The protocol rejects changed action sets, changed response-rule hashes, a changed M4 monetary mapping, a changed M4 risk policy, duplicate actions, or an M4 result that does not reference the M3 envelope supplied to it. Metrics cannot be computed from raw CU or precomputed arbitrary scalar rows. The old BaseRunner route is allowed only for non-scientific smoke checks.

The reference representation is `EXP2A_JOINT` for Exp2A and `EXP2B_COMPONENT` for Exp2B. Both reference and comparison are evaluated through the same downstream object.

## Metrics and result schema

Implemented common-evaluator outputs are:

- `STATE_REPRESENTATION_LINEAGE_PRESERVED`: an engineering diagnostic that checks both compared representations retain the same frozen M1 and M2 source identities; it is not a calibration or accuracy claim;
- `STATE_CRPS`: explicitly `NOT_RUN` until observations and a frozen state-uncertainty protocol exist;
- `DECISION_ACTION_DISAGREEMENT`;
- `DECISION_RANKING_CHANGE` as pairwise M4 ranking reversal rate;
- `DECISION_RISK_DIFFERENCE` as paired variant-minus-reference M4 residual-risk difference;
- `DECISION_CVAR_DIFFERENCE` when supported by M4.

Decision and risk metrics remain `NOT_RUN` when common supported M4 values are unavailable. Every metric records its own `support_status` and nested `artifact_lineage`, including M1/M2 source identities, reference/comparison representation hashes, and the M3/M4 envelope hashes produced for that comparison. Where M4 outputs exist, metadata also preserves monetary-mapping hash, risk-policy hash, alpha, and ranking authority.

Results are `exp.common.result_schema.ExperimentResult` with `experiment_id="EXP2"`, variant, dataset, seed, scenario hash, metrics, support status, provenance, and model/artifact versions. The user-facing singular `artifact_version` input is stored in the common schema's canonical `artifact_versions["EXP2_SOURCE_ARTIFACT"]` map.

## Execution preparation

The pre-execution binding layer is implemented under `exp/exp2/execution/`:

- `execution_manifest.py` defines `Exp2ExecutionManifest`, exact M1-M4 artifact references, the three readiness statuses, and cross-variant fixed-identity validation;
- `artifact_loader.py` loads versioned JSON envelopes, checks canonical payload hashes, validates M1 cutoff provenance, validates the M1 scenario and M2 seven-component contracts, retains CU lineage, and blocks missing, invalid, test-only, or unfrozen M4 artifacts without fallback;
- `downstream_binding.py` defines `Exp2DownstreamExecutor`, which binds one supplied M3 callable and one supplied M4 callable to the frozen artifact set for every variant.

The loader recognizes only `READY`, `BLOCKED_MISSING_ARTIFACT`, and `BLOCKED_UNSUPPORTED_MAPPING`. `READY` means that the supplied artifacts satisfy the adapter's structural and frozen-status checks; it is not scientific approval and does not authorize a run.

The binding layer does not load the current M3 scenario-design registry as formal support, construct a monetary mapping, create a risk policy, choose a sensitivity level, select actions, or execute Exp2. The repository's current M4 design registry still declares `production_mapping_enabled=false`; a future authoritative artifact must come through the human scientific gate.

## Executable pipeline and variant flow

`Exp2Runner.execute_manifest(...)` is the executable binding path for one explicitly declared variant:

1. validate and load the exact content-addressed M1, M2, M3, and M4 artifacts from `Exp2ExecutionManifest`;
2. construct the requested M1 or M2 representation while keeping the other family at its reference representation;
3. bind the caller-supplied M3 executor and M4 evaluator to the artifact action set, response registry, monetary mapping, and risk policy;
4. evaluate both the family reference and requested comparison through that same binding;
5. evaluate supported metrics and return `exp.common.result_schema.ExperimentResult`.

The M2 pipeline boundary consumes the frozen seven-component M2 artifact. It does not rerun M2, reconstruct consequences, or recalculate CU. Likewise, the runner requires the M3 and M4 callables and explicit model versions; it does not discover implementations or select scientific parameters.

For an explicitly supplied compatible set, `execute_manifests(...)` first verifies identical dataset, split, seed, artifact identities, and config hash, then runs every manifest through one `Exp2DownstreamExecutor` instance. Variant switching therefore changes only `JOINT/MARGINAL/COLLAPSED` or `COMPONENT/CHANNEL/SCALAR`; it cannot change the downstream binding.

The configuration shape is frozen in `configs/experiment/exp2.yaml`. Its artifact and dataset entries intentionally remain `REQUIRED`; it is not a runnable scientific configuration and contains no tuning values.

A future authorized caller supplies approved artifacts and already-bound M3/M4 scientific objects, then calls:

```python
result = Exp2Runner().execute_manifest(
    manifest,
    artifact_root=artifact_root,
    m3_executor=frozen_m3_executor,
    m4_evaluator=frozen_m4_evaluator,
    model_versions=approved_model_versions,
)
```

This implementation does not authorize a Development, Final Test, `paper_full`, or paper experiment run. Missing/invalid artifacts block before downstream execution; unsupported/unfrozen M4 mapping or policy uses the existing explicit blocked status and no fallback.

## Scientific claim boundary

The implemented claim is limited to **representation sensitivity under a fixed downstream system**: whether changing only the information representation changes downstream recovery evaluation outcomes. It does not compare trained models, establish an optimal policy, identify causal action effectiveness, validate non-A00 response parameters, or make real-world monetary claims. Those stronger claims remain blocked by their respective M3/M4 scientific gates; the pipeline records the mismatch and does not resolve it.

The current manuscript evaluation draft is aligned with that narrow non-causal/non-optimal claim boundary and explicitly blocks authoritative Exp2 ranking while M4 is unfrozen. It is not protocol-identical to this pipeline, however: the draft reports the historical Development point-collapse/lineage-corruption design and temporary outputs, whereas this implementation freezes the six `EXP2A_*`/`EXP2B_*` representation variants and has produced no results. Historical Development outputs therefore cannot be cited as evidence from this pipeline. This protocol/result mismatch is recorded here only; no manuscript claim or result was changed by this implementation task.

## Verification

The focused tests under `tests/experiments/test_exp2/`, `tests/experiments/test_exp2_execution/`, and `tests/experiments/test_exp2_pipeline/` cover registry metadata, representation transformations, source lineage, artifact blocking, variant switching, the identical M3-to-M4 binding, metric lineage, and common result-schema compatibility. They use test fixtures only; they are engineering checks and do not test scientific superiority.
