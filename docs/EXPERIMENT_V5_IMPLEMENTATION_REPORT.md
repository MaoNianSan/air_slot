# Air Slot EXPERIMENT_PROTOCOL_V5 Implementation Report

Date: 2026-08-16
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
| total delay inferred as `R_OB + T_TX` in experiment evaluation | total delay requires event time plus schedule/taxi reference | MIGRATED; legacy fixture helper isolated |
| unkeyed/offset shuffle RNG | episode/node/q/replicate/component keyed stream | MIGRATED |
| generic Exp1/2/3/4 variant names | canonical V5 protocol variants plus legacy aliases | MIGRATED |
| available-component total could be mistaken for formal scope | fixed formal scope remains distinct from diagnostic sum | CONTRACT ENFORCED |
| no central paper gate | detailed cross-contract and implementation manifests | MIGRATED |
| historical overall aggregate hierarchy | deprecated compatibility wrappers | MIGRATED; no active historical script found |

## D. Unresolved Items

- `H_STAR=32` and `W_STAR=30 minutes` are Development-frozen by `D2_H_STAR` and `D1_W_STAR`.
- Development-frozen Exp1 warning thresholds have not been produced.
- `N_FORMAL_MULTI` is unknown because no real frozen formal cohort was generated in this turn.
- The paper-frozen M2 valuation registry/formal estimand artifact is not available.
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

- `python -m compileall -q formal exp model tests`: PASS.
- `pytest -q`: 354 passed, 1 skipped.
- `python -m validation.cli all --fixtures-only`: 421 PASS, 0 FAIL/BLOCKED.
- `python -m exp.cli smoke-all --output artifacts\diagnostics\v5_smoke`: PASS;
  synthetic only, `paper_result=false`.

Final state: `PAPER_FULL_BLOCKED` pending Development freezes and a real frozen formal cohort.
