# Experiment Model Interface Audit

Audit basis: source at `3a6b4f7045cadad45e9fac744a3ad2cb8b1f8bc1`. Current typed code and registries outrank historical experiment manifests and README claims.

## Frozen chain and public boundaries

| Stage | Current typed boundary | Output required by experiments | Audit status |
| --- | --- | --- | --- |
| PRE | `PREState` in `model/PRE/contracts/pre_state.py`; production publication via `ProductionPRERequest` and `publish_production_pre` | admissible state, decision/information time, evidence/support/lineage, references | `ALIGNED` |
| M1 | `M1Service.generate_scenarios`; `M1V2Scenario` | full weighted scenario distribution with scenario ID/seed lineage and `D_OB`, `D_TX`, `D_TO` semantics | `ALIGNED` at model boundary |
| M2 | `M2ScenarioInput.from_m1`; `M2Mapper.map_m1_scenarios`; `ScenarioConsequenceDistribution` | immutable seven-component baseline `C0_CU` per scenario | `ALIGNED` interface, formal aggregate scientifically unresolved |
| M3 | `M3BaselineConsequenceInput`; `ActionEvaluationEnvelope`; `m4_payload()` | action eligibility and full action-conditioned `Ca_CU` distribution | `BLOCKED` for non-A00: only A00 identity is executable in V2 |
| M4 | `M4ActionEnvelopeInput`; `evaluate_residual_risk`; `rank_risk_evaluations` | monetary loss and risk envelope with labelled ranking authority | `BLOCKED` for scientific ranking: no production monetary mapping and required policy freezes |

`C0_CU` means M2 baseline `C^{0,CU}`. `Ca_CU` means M3 action-conditioned `C^{a,CU}`. Experiments must not replace these typed objects with raw delay, a manually summed CU vector, or a legacy action score.

## Current experiment consumption versus required consumption

| Experiment path | Current dependency | New required dependency | Status | Reason |
| --- | --- | --- | --- | --- |
| `exp/common/runner.py` | externally supplied scalar `variant_metrics` | typed chain artifacts and evaluator-owned metric computation | `STALE` | no model-interface validation; variant labels can be attached to arbitrary numbers |
| `formal/pipeline.py` | prepared dictionaries named `pre_state`, `m1_scenarios`, `m2_consequences`, `m3_actions`, `m4_decision` | validated typed PRE/M1/M2/M3/M4 envelopes | `STALE` | hashing wrapper does not prove the chain was executed or compatible |
| current Exp1 generic runner | old labels and copied formal dictionaries | PRE state/M1 scenario pathway variants plus frozen model identity | `STALE` | no `FULL`/`NO_DIRECT_REUSE` adapter; no V2 scenario evaluation |
| Exp1 history adapter | typed PRE sequences through `model/M1/history.py` | `CURRENT`/`FIXED_HISTORY`/`ADAPTIVE_HISTORY` | `ALIGNED` | causal cutoff, one-episode and five-minute-grid checks exist |
| `exp/exp2/representations.py` | legacy `r_ib_minutes`, `r_ob_minutes`, `t_tx_minutes` dictionaries | one immutable `M1V2Scenario` bundle transformed to `COLLAPSED`, `MARGINAL`, `JOINT` | `STALE` | useful algorithms, wrong schema and no typed artifact guard |
| `exp/exp234/development_execution.py::map_node_pre` | `M2Mapper.map_scenarios` dictionary compatibility API | `M2Mapper.map_m1_scenarios` and typed `ScenarioConsequenceDistribution` | `STALE` | uses historical V1 mapping path |
| `exp/exp234/development_execution.py::_fast_pre_rows` | manual five-component M2 arithmetic and old D_TO identity | M2-emitted seven-component `C0_CU` only | `STALE` | duplicates M2 authority and is already documented as obsolete |
| `exp/exp234/exp234_helpers.py::_post_scope` | legacy `action_post_consequences`, manual mitigation/induced fields, hard-coded `induced_score_to_cu=0.10` | M3-emitted `Ca_CU` | `STALE` | bypasses the V2 M3 response boundary |
| old Exp234 action maps | distributional raw-CU sums used as action values | M4 `RiskEvaluationEnvelope`/`RiskRankingEnvelope` | `BLOCKED` | raw CU is not money and cannot replace M4 residual risk |
| current Exp4 runner | labels only; optional old ranking/latency helpers | frozen M4 risk envelopes plus prediction/validation/portability/runtime artifacts | `BLOCKED` | no typed evaluator; authoritative ranking inputs are not scientifically frozen |

## Per-experiment model alignment

| Experiment | PRE | M1 scenario | M2 `C0_CU` | M3 `Ca_CU` | M4 risk | Overall |
| --- | --- | --- | --- | --- | --- | --- |
| Exp1 | required | required | optional for downstream decision metrics | required when action comparison is reported | required for risk difference | `STALE` |
| Exp2 | lineage only; no rebuild per variant | same immutable artifact for all variants | required for SCALAR/CHANNEL/COMPONENT | required for decision metrics | required for risk difference | `BLOCKED` |
| Exp3 | required at each legal decision node | required at each one-shot/rolling node | required | required | required for risk metrics | `BLOCKED` |
| Exp4 | required for dataset/support audit | required for prediction evaluation | required for validation | required for decision evaluation | required for risk/runtime end-to-end evaluation | `BLOCKED` |

## Mandatory migration rules

1. New experiment code must accept typed or schema-validated serialized artifacts, record their exact hashes, and reject legacy V1 scenario fields.
2. Exp2 transformations must reuse one M1 artifact; no variant may retrain or resample M1 unless the frozen protocol explicitly makes sampling seed part of the shared artifact.
3. Experiments may aggregate M2 outputs but may not reconstruct native consequence or CU values.
4. Experiments may compare M3 outputs but may not call compatibility response code to manufacture `Ca_CU`.
5. Decision/risk metrics must consume M4 envelopes and preserve `ranking_authority`, support state, reason codes, monetary registry hash, and risk-policy hash.
6. A blocked scientific mapping must remain blocked. A legacy five-component result, test-only money scale, or scenario-only response cannot fill a V2 seven-component or authoritative gap.

## Final interface status

`MODEL_ALIGNMENT = STALE_AND_BLOCKED`

The model modules expose the intended chain, but current experiment execution does not consume it end to end. Migration can proceed without editing PRE or M1-M4 only if experiment-layer adapters can serialize and compare the existing typed outputs. Non-A00 M3 response, V2 CU normalization, production monetary mapping, and risk-policy freezes remain external scientific blockers rather than experiment-code tasks.
