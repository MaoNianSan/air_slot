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
| `exp/exp2/runner.py` | Typed execution entry; legacy scalar-row execution is limited to smoke mode |
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

- `STATE_CRPS`: explicitly `NOT_RUN` until observations and a frozen state-uncertainty protocol exist;
- `DECISION_ACTION_DISAGREEMENT`;
- `DECISION_RANKING_CHANGE` as pairwise M4 ranking reversal rate;
- `DECISION_RISK_DIFFERENCE` as paired variant-minus-reference M4 residual-risk difference;
- `DECISION_CVAR_DIFFERENCE` when supported by M4.

Decision and risk metrics remain `NOT_RUN` when common supported M4 values are unavailable. Their metadata preserves monetary-mapping hash, risk-policy hash, alpha, and ranking authority.

Results are `exp.common.result_schema.ExperimentResult` with `experiment_id="EXP2"`, variant, dataset, seed, scenario hash, metrics, support status, provenance, and model/artifact versions. The user-facing singular `artifact_version` input is stored in the common schema's canonical `artifact_versions["EXP2_SOURCE_ARTIFACT"]` map.

## Future execution entry

Create a concrete `Exp2DownstreamInterface` backed by the frozen current M3 action-response registry and M4 monetary/risk artifacts, then construct `Exp2RunContext` and call:

```python
result = Exp2Runner().execute(context)
```

This is a future gated entry only. It does not authorize a Development, Final Test, `paper_full`, or paper experiment run.

## Verification

The focused tests under `tests/experiment/test_exp2/` cover registry metadata, representation transformations, source lineage, support propagation, the identical M3-to-M4 interface, and common result-schema compatibility. They are engineering checks and do not test scientific superiority.
