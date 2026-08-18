# Air Slot EXPERIMENT_PROTOCOL_V5 Implementation Report

Date: 2026-08-18
Repository: `D:\research\air_slot\code\explore`
Branch: `main`

## A. Changed Files

| Path | Purpose | Scientific contract affected |
| --- | --- | --- |
| `docs/EXPERIMENT_V5_IMPLEMENTATION_AUDIT.md` | Read-only pre-implementation audit and authority boundary | Audit-first requirement; current PRE-M4 and legacy-entry classification |
| `docs/EXPERIMENT_V5_IMPLEMENTATION_REPORT.md` | Final implementation/readiness handoff | V5 delivery and unresolved-item disclosure |
| `configs/evaluation/common.yaml` | Single serialized cross-experiment contract | DATA2 split, units, bootstrap, rolls, lead times, risk, scenario scales, modes |
| `configs/evaluation/exp1.yaml` | Canonical Exp1 variants and frozen-selection candidates | history-only ownership, fixed FPR, sustained warning, DWG headline |
| `configs/evaluation/exp2.yaml` | Canonical Exp2 design | D-C reference, joint medoid, fixed scopes, corruption grid |
| `configs/evaluation/exp3.yaml` | Canonical one-change ablations and LLM boundary | supportability semantics, unsupported-not-zero, evaluation-only DeepSeek |
| `configs/evaluation/exp4.yaml` | V5 sensitivity/portability/deployment grid | normative valuation, response sensitivity, roll/MC, Data1 gates, 300 s runtime gate |
| `formal/__init__.py` | Public immutable-formal package | formal/evaluation responsibility separation |
| `formal/artifacts.py` | Typed node/bundle schemas, hashes, write-once guard | required formal hashes and immutability |
| `formal/pipeline.py` | Reusable typed PRE-M4 artifactization entrypoint | one frozen formal run reused by experiments |
| `exp/common/contracts.py` | `ExperimentCrossContract`, runtime modes, expanded manifests | cross-experiment source of truth and evaluation lineage |
| `exp/common/rng.py` | Named deterministic RNG streams | worker/order invariance and stream separation |
| `exp/common/split.py` | Four-way V5 split and episode containment | no episode crosses Train/Calibration/Development/Final Test |
| `exp/common/artifacts.py` | Artifact namespaces and evaluation writer | evaluation references formal hash and cannot overwrite |
| `exp/common/bootstrap.py` | Named-stream episode bootstrap and paired cluster bootstrap | episode is the independent bootstrap unit |
| `exp/common/runner.py` | Mode/paper gate, formal hash and RNG manifest fields | immutable reference and explicit `paper_full` approval |
| `exp/cli.py` | V5 modes, protocol variants, status command | smoke/development/paper_full/numerical_stress interface |
| `exp/status.py` | Cross-contract and implementation manifests | pre-paper-full acceptance gate |
| `exp/legacy.py` | Explicit legacy wrappers/deprecation errors | old runners no longer define scientific hierarchy |
| `exp/exp1/runner.py` | Canonical protocol metadata | ADAPTIVE vs FIXED headline |
| `exp/exp1/variants.py` | V5 variants and leakage flags | history-only changes; invalid retrospective state excluded from selection |
| `exp/exp1/metrics.py` | Sustained warning, DWG, fixed-FPR recall, episode false warnings | Exp1 metric hierarchy |
| `exp/exp2/runner.py` | Canonical 2x2/reference metadata | D-C reference evaluator |
| `exp/exp2/representations.py` | Joint medoid and keyed marginal-preserving corruption | coherent point rule; q=0 aligned; lineage corruption only |
| `exp/exp2/metrics.py` | Distortion/ranking/selection-penalty metrics and cohort claim gate | no regret naming; variant choice rescored under reference |
| `exp/exp3/runner.py` | Canonical supportability variants | reliability is contractual supportability |
| `exp/exp3/ablations.py` | One-rule evaluation copies | evidence only, coverage only, or Delta-plus only |
| `exp/exp3/metrics.py` | Feasibility/lane/invalidated-ranking metrics | relaxed Top1 means not FORMAL under FULL |
| `exp/exp3/llm_audit.py` | Stratified selection and strict response schema | DeepSeek is evaluation-only and cannot change ranking |
| `exp/exp4/runner.py` | Exp4 protocol ownership and runtime gate metadata | robustness, portability, deployability only |
| `exp/exp4/metrics.py` | ranking stability and latency summaries | p50/p95/p99 and p95 under 300 s gate |
| `exp/exp4/portability.py` | support transitions and hard gates | no silent substitution or downstream semantic redefinition |
| `model/M1/semantics.py` | Event-time/reference-derived total-delay contract | `T_TO=T_OB+T_TX`; no formal `D_TO=D_OB+D_TX` assumption |
| `model/M1/contracts.py` | Optional event/reference fields and non-fabricating `D_TO` | total delay remains unavailable without required reference terms |
| `model/M1/scenarios.py` | Named `m1_scenario` RNG key | stable aligned sampling |
| `model/M4/response.py` | Named `m3_m4_response` RNG key | response draws exclude decision time |
| `tests/contract/test_experiment_v5_contract.py` | New V5 contract tests | split, delay, medoid, corruption, artifacts, RNG, gates, portability |
| `tests/integration/test_reconciliation_contracts.py` | Migrated point-collapse expectations | coherent scenario rather than synthetic means |
| `tests/integration/test_refactor_behavioral_equivalence.py` | Removed additive-delay expectation | no fabricated total delay without references |
| `README.md`, `exp/README.md` | Corrected DATA2/Data1 roles and runtime documentation | principal vs portability environment; mode separation |
| `EXPERIMENT_CROSS_CONTRACT.json` | Machine-readable resolved contract | single shared V5 configuration |
| `EXPERIMENT_CROSS_CONTRACT_STATUS.json` | Detailed pre-paper-full checks | critical/partial gate visibility |
| `EXPERIMENT_V5_IMPLEMENTATION_STATUS.json` | Component implementation/run status | no aggregate PASS masking unresolved items |

## B. New Architecture

```text
canonical/raw dataset adapters
        |
        v
PRE -> M1 -> M2 -> M3/M4
        |
        v
formal.run_formal_pipeline
        |
        v
artifacts/formal/  (immutable, hashed, write once)
        |
        +---------> Exp1: history representation only
        +---------> Exp2: uncertainty representation only
        +---------> Exp3: one contract rule at a time
        +---------> Exp4: sensitivity/portability/deployability
                          |
                          v
                    evaluation artifacts
                          |
                          v
                  publication tables/figures
                  (read-only artifact consumer)
```

The formal artifact records episode/node identity, decision time/cutoff, PRE/M1/M2/M3/M4 hashes,
global seed, and `formal_output_hash`. Evaluation manifests reference that hash. An existing formal
path is not overwritten unless an explicit low-level override is supplied outside experiment code.

## C. Legacy/V4 Migration

| Old behavior | V5 behavior | Status |
| --- | --- | --- |
| `fast/middle/full` as experiment modes | `smoke/development/paper_full/numerical_stress`; M1 `FAST` remains a model path | MIGRATED |
| component-wise point means | weighted joint scenario medoid | MIGRATED |
| total delay inferred as `R_OB + T_TX` in experiment evaluation | total delay requires signed off-block timing plus train-frozen taxi reference | MIGRATED to `max(0, DELTA_OB + T_TX - taxi_reference)` |
| unkeyed/offset shuffle RNG | episode/node/q/replicate/component keyed stream | MIGRATED |
| generic Exp1/2/3/4 variant names | canonical V5 protocol variants plus legacy aliases | MIGRATED |
| available-component total could be mistaken for formal scope | fixed formal scope remains distinct from diagnostic sum | CONTRACT ENFORCED |
| no central paper gate | detailed cross-contract and implementation manifests | MIGRATED |
| historical overall aggregate hierarchy | deprecated compatibility wrappers | MIGRATED; no active historical script found |

## D. Unresolved Items

- Signed-target `H_STAR=32` and `W_STAR=30 minutes` are Development-frozen by `D3_SIGNED_M1_H_W_REFREEZE`.
- The final signed warning-model checkpoint is frozen by the first pre-registered W seed rule; Exp1 Development warning inference and operating-point freeze are `PASS` under `AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE`.
- `N_FORMAL_MULTI` is unknown because no real frozen formal cohort was generated in this turn.
- The paper-frozen M2 valuation registry/formal estimand artifact is not available. The M2 context adapter (`model/M2/context.py`) is implemented and consumes frozen Data2 reference payloads without rebuilding PRE/M1.
- Most non-A00 M3 response parameters are not frozen; formal multi-action support is therefore
  expected to remain limited until that scientific work is authorized.
- Exp4 valuation profiles are named, but their numerical weights still require Development freeze.
- Exp4 LOW/BASE/HIGH response ranges still require Development freeze.
- The Data1 support-transition and positive-evidence analysis is implemented as a contract/helper,
  but has not been executed over the real portability cohort.
- DeepSeek schema and selection are implemented; no provider call or 1,200-repetition audit ran.
- The formal pipeline artifactizes typed PRE-M4 node outputs; production-scale cohort scheduling and
  real model artifact loading remain caller-owned and have not run here.
- No Final Test, `paper_full`, 10,000-scenario full cohort, large bootstrap, or paper promotion ran.

## E. Commands

Smoke contracts and all experiment shells:

```powershell
python -m exp.cli smoke-all --output artifacts\diagnostics\v5_smoke
```

Bounded Development evaluation from prepared frozen-artifact evaluation rows:

```powershell
python -m exp.cli run --experiment exp1 --input artifacts\diagnostics\exp1_development_rows.json --output artifacts\exp1\development --mode development --protocol-variants
```

Paper-full command shape (currently blocked; do not run until every cross-contract check is PASS):

```powershell
python -m exp.cli run --experiment exp1 --input artifacts\formal\final_test_exp1_rows.json --output artifacts\exp1\paper_full --mode paper_full --protocol-variants --approve-paper-full
```

Numerical-stress command shape for a bounded deep subset only:

```powershell
python -m exp.cli run --experiment exp4 --input artifacts\diagnostics\exp4_numerical_subset_rows.json --output artifacts\exp4\numerical_stress --mode numerical_stress --protocol-variants
```

Refresh machine-readable gates:

```powershell
python -m exp.cli status --output .
```

## F. Validation Evidence

Historical initial validation (current overnight-focused evidence is in G):

- `python -m compileall -q formal exp model tests`: PASS.
- Full regression baseline: 412 passed, 1 skipped.
- `python -m validation.cli all --fixtures-only`: 421 PASS, 0 FAIL/BLOCKED.
- `python -m exp.cli smoke-all --output artifacts\diagnostics\v5_smoke`: PASS;
  synthetic only, `paper_result=false`.

Final state: `PAPER_FULL_BLOCKED` pending Development freezes and a real frozen formal cohort.

## G. Overnight Development Closure 2026-08-18

Exp1 Development freeze is recorded as `PASS` and reused without upstream rerun.

Frozen Development contracts (scenario-only numerical freeze; freeze does not equal formal
empirical support):

- M2 formal freeze `M2_DATA2_FORMAL_CU_V1` is COMPLETE:
  - registry `registries/m2_data2_formal_cu_v1.json`, registry hash
    `sha256:c257debc032bff2553b7ffdc4eb4305261f7183c45c1a43ad9164d865af2b029`;
  - train fit (2019-01..06 On-Time + Q1/Q2 DB1B, train partition only) is PRE-owned
    (`model/PRE/reference/data2_m2_train_fit.py`); turnaround/downstream-exposure/passenger
    references re-fitted deterministically; frozen taxi reference reused;
  - train scales = positive Train-period medians (`F_continuity` 43.0 min,
    `F_execution` 17.0 min, `F_propagation` 11.0 exposure-min, `P_time` 1,037,820
    passenger-min, `R_operating` 5.0 excess-taxi-min), byte-identical to the earlier
    partial run;
  - closure `artifacts/diagnostics/v5_development_freeze/M2_FORMAL_FREEZE_CLOSURE.json`
    (elapsed 786.8 s, `final_test_access_count=0`).
- M3 numerical response freeze `M3_RESPONSE_SCENARIO_V1` is COMPLETE (scenario-only,
  `formal_support_upgrade=false`): response registry
  `sha256:ff8adb3034603ec225930ed9187bc296b46d58637a974c9de64b341248755ce0`, manifest
  `M3_RESPONSE_SCENARIO_V1_MANIFEST.json`. FROZEN numerical response does not imply formal
  empirical support.
- M4 formal support-aware ranking is COMPLETE: non-A00 scenario response parameters cannot
  enter a formal aggregate or authoritative ranking; `scenario_conditioned` /
  `post_total_status` labeling is sticky and validated.

Exp2-Exp4 Development:

- Readiness: `EXP2_READINESS=PASS`, `EXP3_READINESS=PASS`, `EXP4_READINESS=PASS`
  (evidence: `M2_FORMAL_SCOPE_READY`, `M3_RESPONSE_PARAMETERS_FROZEN`,
  `M2_VALUATION_AND_M3_RESPONSE_SENSITIVITY_FROZEN`).
- Component closure `AIR_SLOT_EXP2_3_4_DEVELOPMENT_COMPONENT_CLOSURE.json` hash
  `sha256:48c889fa1f605dec5d74c28ac7c73d9fa16c0ffe68c8a6728cbbbbf151c00607`: Exp2
  point/lineage/metric gates, Exp3 ablations/feasibility/lane, Exp4 portability/strata all
  `PASS` on fixtures.
- Cohort-scale Exp2/3/4 runs remain data-path blocked:
  `DEVELOPMENT_M1_SCENARIO_DRAWS_NONEXISTENT` (no per-node M1 scenario-draw artifact exists
  for the Development cohort; reconstruction would require re-running the Development PRE
  stream / signed M1 cache, which is prohibited), plus
  `DEVELOPMENT_FORMAL_ARTIFACT_ROWS_NONEXISTENT` (Exp3) and
  `DEVELOPMENT_PRINCIPAL_OUTPUT_ROWS_NONEXISTENT` (Exp4). These are recorded as blocked
  subcomponents, not scientific PASS.

DeepSeek LLM audit:

- Protocol implemented and offline-tested (`exp/exp3/llm_audit.py`): pilot 50 -> principal
  1200 -> 10% repeat-stability on the same frozen model, request-hash cache, checkpoint/
  resume, `MAX_LLM_CALLS=1500`, `MODEL_SELECTION_RULE=COST_FIRST_WITH_QUALITY_GATE`
  (DeepSeek-V4-Flash first, cheaper chat fallback, escalation only when the pilot quality
  gate fails: `schema_pass_rate>=0.98`, `parse_failure<=0.02`, no systematic prerequisite or
  hallucination failures).
- Runtime `BLOCKED`: `DEEPSEEK_API_KEY` is not configured in the environment. No pilot or
  principal calls were made (`calls_used=0`). The key is read only from `DEEPSEEK_API_KEY`
  and never written to code, logs, artifacts, manifests, or git.

Gates:

- `FINAL_TEST_ACCESS_COUNT=0`, `PAPER_FULL_RUN=FALSE`, `EXPENSIVE_UPSTREAM_RERUN_COUNT=0`;
  formal 2019-10..12 Final Test is never accessed; PRE/M1/Exp1/taxi upstreams were reused,
  not rerun.

Validation during this pass:

- Focused suites: `tests/m2` 26, `tests/m3` 18, `tests/m4` 17,
  `tests/experiments`+`tests/contract` 64, `tests/pre`+reference unit 82, integration and
  static green; `python -m validation.cli all --fixtures-only`: 515 PASS / 0 FAIL.
- `python -m exp.cli status --output artifacts/diagnostics/v5_development_freeze/status_refresh`:
  `status=PASS` with all readiness gates `PASS`.
- Full regression at global closure: `python -m pytest -q` -> 464 passed, 1 skipped.
