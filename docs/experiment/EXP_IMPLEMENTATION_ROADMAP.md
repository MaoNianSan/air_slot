# Experiment Implementation Roadmap

This is a migration plan only. It does not authorize source changes, model changes, experiment execution, parameter selection, Final Test access, paper-result generation, or Git operations.

## Phase 1: Common experiment infrastructure

### Files to create

- `exp/common/model_chain.py`: load and validate serialized current PRE/M1/M2/M3/M4 artifacts without executing compatibility paths.
- `exp/common/result_schema.py`: versioned run manifest and metric record contracts.
- `exp/common/evaluator.py`: support-aware paired evaluation interface.
- `tests/experiments/test_current_chain_boundary.py`.
- `tests/experiments/test_result_schema_v2.py`.

### Files to modify

- `exp/common/{contracts,artifacts,runner}.py`;
- `exp/cli.py`;
- `exp/reporting/{figures,tables}.py`;
- `exp/status.py` and `configs/evaluation/common.yaml` so new readiness is not inferred from old V5 checks.

### Interfaces used

`PREState`, `M1V2Scenario`, `ScenarioConsequenceDistribution`, `ActionEvaluationEnvelope`, `M4ActionEnvelopeInput`, `RiskEvaluationEnvelope`, and `RiskRankingEnvelope`.

### Required tests

typed round-trip and content hashes; write-once outputs; no legacy schema acceptance; paired cohort/seed identity; support/authority propagation; no model mutation; Final Test and paper-full guards.

### Exit gate

One fixture-only chain artifact can be loaded and evaluated with complete lineage. Blocked M3/M4 fields remain blocked. No scientific number is required.

## Phase 2: Exp2 implementation first

### Files to create

- `exp/exp2/transforms_v2.py` for `COLLAPSED`, `MARGINAL`, `JOINT` over one M1 V2 artifact;
- `exp/exp2/aggregation_v2.py` for `SCALAR`, `CHANNEL`, `COMPONENT` over M2 output;
- `tests/experiments/test_exp2_v2_transforms.py`;
- `tests/experiments/test_exp2_v2_aggregation.py`.

### Files to modify

- `exp/exp2/{runner,metrics,README}.py`/`.md` as applicable;
- `configs/evaluation/exp2.yaml`;
- `exp/cli.py` and result/report mappings.

### Interfaces used

same immutable `M1V2Scenario` distribution for every variant; `M2Mapper.map_m1_scenarios`; M2 component/aspect/formal estimand objects; M3/M4 envelopes for decision/risk metrics when supported.

### Required tests

same source hash and no retraining; joint identity; coherent collapse; marginal preservation; scenario-weight preservation; support-aware aggregation; no manual M2/M3/M4 arithmetic; deterministic transforms.

### Exit gate

All representation/resolution variants execute on fixtures with aligned hashes. Scientific outputs that require unresolved V2 CU, non-A00 response or M4 mapping remain `BLOCKED`.

## Phase 3: Exp1

### Files to create

- `exp/exp1/information_pathway.py` for `FULL`/`NO_DIRECT_REUSE`;
- `exp/exp1/evaluator_v2.py`;
- `tests/experiments/test_exp1_information_pathway.py`;
- `tests/experiments/test_exp1_v2_runner.py`.

### Files to modify

- `exp/exp1/{variants,runner,metrics,README}.py`/`.md`;
- `configs/evaluation/exp1.yaml`.

### Interfaces used

typed PRE state, `model.M1.history.represent_history`, frozen M1 model/scenario interface, and current downstream typed artifacts for decision/risk metrics.

### Required tests

declared-field-only ablation; no raw bypass; history cutoff/episode/grid invariants; identical non-intervention identities; V1 artifact rejection; support-aware paired metrics.

### Exit gate

Both Exp1A and Exp1B fixture matrices are executable and provenance-complete. No old warning freeze is consumed as current evidence.

## Phase 4: Exp3

### Files to create

- `exp/exp3/decision_loop.py` for `ONE_SHOT`/`ROLLING` orchestration;
- `exp/exp3/lag_variants.py` for `SYNC`/`LAG_5`/`LAG_10` experiment contracts;
- `tests/experiments/test_exp3_decision_loop.py`;
- `tests/experiments/test_exp3_lag_contract.py`.

### Files to modify

- replace the active purpose of `exp/exp3/{runner,metrics,README}.py`/`.md`;
- replace `configs/evaluation/exp3.yaml`;
- keep the LLM audit outside the new Exp3 runner.

### Interfaces used

PRE rolling node and factual availability contracts, typed PRE states, M1 history/service, and typed M2-M4 outputs.

### Required tests

freeze one-shot anchor semantics; immutable rolling prefixes; exact lag availability; no future/outcome leakage; weather-lag separation; paired node/cohort/seed identities; episode aggregation.

### Exit gate

The five protocol combinations run on fixtures without altering PRE/M1-M4. If a lag cannot be expressed through current public interfaces, stop and request a separate model-interface decision rather than patching PRE in this phase.

## Phase 5: Exp4

### Files to create

- `exp/exp4/prediction_evaluation.py`;
- `exp/exp4/validation_evaluation.py`;
- `exp/exp4/runtime_evaluation.py`;
- `tests/experiments/test_exp4_prediction_metrics.py`;
- `tests/experiments/test_exp4_validation.py`;
- `tests/experiments/test_exp4_runtime.py`.

### Files to modify

- `exp/exp4/{runner,metrics,portability,README}.py`/`.md`;
- `configs/evaluation/exp4.yaml`;
- common reporting schema/templates.

### Interfaces used

M1 predictive distributions/scenarios and calibration metadata; typed M2-M4 outputs; Data1/Data2 support contracts; stage timers around existing public boundaries.

### Required tests

CRPS/Brier/calibration/coverage fixtures; support-aware validation denominators; Data1 no-substitution/role checks; latency percentile and stage-accounting tests; result/report lineage round-trip.

### Exit gate

All four Exp4 evaluation areas produce fixture-only, provenance-complete outputs. Dataset and system readiness are reported separately from scientific ranking availability.

## Implementation order and global stop gates

`Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5`

At every phase:

- do not modify `model/`, PRE, or M1-M4 under this experiment migration authorization;
- do not use Final Test, `paper_full`, tuning, or scientific parameter selection;
- do not treat fixture/smoke tests as scientific evidence;
- do not commit or push without separate authorization;
- stop at any missing scientific freeze instead of importing a legacy substitute.

`IMPLEMENTATION_PLAN_STATUS = READY_FOR_HUMAN_REVIEW`
