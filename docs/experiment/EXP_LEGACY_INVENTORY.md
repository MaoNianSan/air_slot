# Experiment Legacy Inventory

Audit date: 2026-08-20  
Repository HEAD: `3a6b4f7045cadad45e9fac744a3ad2cb8b1f8bc1`  
Worktree at audit start: `?? codex_framework/` (pre-existing, not inspected or modified)  
Scope: read-only inspection of `exp/`, evaluation configuration/reporting, executable scripts, formal artifact wrappers, and PRE-M4 public interfaces. Historical outputs were not promoted to current evidence.

## Directory findings

- The active experiment package is `exp/`.
- There is no source directory named `evaluation/`; evaluation configuration is under `configs/evaluation/`, historical/generated outputs are under `outputs/evaluation/`, and model-local evaluation helpers are under `model/M1/evaluation.py` and `model/M2/evaluation.py`.
- There is no repository-root `scripts/` directory. `data2/scripts/` contains data utilities, not experiment entry points.
- Executable experiment entry points are module CLIs: `python -m exp.cli`, `python -m exp.development_closure`, `python -m exp.exp1.development.*`, and `python -m exp.exp234.*`.
- `formal/` is a generic artifactization wrapper. It accepts prepared mappings and does not itself execute the frozen typed PRE -> M1 -> M2 -> M3 -> M4 chain.

## Inventory and disposition

| Existing component | Location / entry point | Current purpose | Inputs | Outputs | Main dependencies | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| Generic experiment CLI | `exp/cli.py`; `python -m exp.cli` | Smoke, generic run, report, and old V5 status commands | JSON rows with precomputed `variant_metrics` | `result.json`, `manifest.json`, smoke/report bundles | `BaseRunner`, Exp1-Exp4 runner metadata | `REWRITE` |
| Cross-experiment contracts | `exp/common/contracts.py` | Split, runtime-mode, RNG and manifest contracts | `configs/evaluation/common.yaml` | typed contract and `ExperimentRunManifest` | Pydantic, content hashes | `REUSE_WITH_ADAPTATION` |
| Artifact guards | `exp/common/artifacts.py`, `formal/artifacts.py` | Frozen-input validation, write-once evaluation/formal artifacts | JSON-compatible artifacts | hashed immutable bundles | `content_id`, contract errors | `REUSE_WITH_ADAPTATION` |
| Cohort/split/bootstrap helpers | `exp/common/{cohorts,split,paired,bootstrap,rng}.py` | Episode-safe splits, paired rows, episode bootstrap, deterministic RNG | experiment rows | in-memory rows/statistics | NumPy | `KEEP` |
| Generic runner | `exp/common/runner.py::BaseRunner` | Repeats externally supplied scalar metrics across named variants | rows containing `variant_metrics` | generic result rows and manifest | common contracts | `REWRITE` |
| Reporting | `exp/reporting/{figures,tables}.py` | Generic CSV/PDF/PNG/TeX output | arbitrary two-column/table rows plus metadata | files and metadata JSON | pandas, matplotlib | `REUSE_WITH_ADAPTATION` |
| Status/readiness | `exp/{readiness,status}.py`; `python -m exp.cli status` | Old V5 component readiness and paper-full self-check | old evaluation configs and frozen registries | status JSON | M2 five-component scope, legacy M3 registry | `REWRITE` |
| Promotion | `exp/promotion.py` | Gate and copy eligible result bundles | old manifest schema | promoted bundle | filesystem | `REUSE_WITH_ADAPTATION` |
| Legacy wrapper | `exp/legacy.py` | Deprecation wrapper for `overall_run`; rejects `overall_adv`/`part_adv` | legacy callbacks | legacy result/error | caller pipeline | `REMOVE` from active path |
| Formal bundle wrapper | `formal/pipeline.py::run_formal_pipeline` | Package already-prepared node dictionaries | mapping fields for PRE-M4 | `FormalArtifactBundle` | action registry hash helper | `REWRITE` |

## Experiment-specific inventory

| Existing experiment | Location / entry point | Current purpose | Inputs | Outputs | Classification |
| --- | --- | --- | --- | --- | --- |
| Exp1 generic protocol | `exp/exp1/{runner,variants,metrics}.py` | Old warning/history comparison with empirical, independent-head and leakage variants | frozen artifact copies or precomputed metrics | warning/lead-time metrics | `REWRITE` |
| Exp1 history adapter | `exp/exp1/history.py` -> `model/M1/history.py` | `CURRENT`, closed-window `FIXED_HISTORY`, full causal-prefix `ADAPTIVE_HISTORY` | ordered typed `PREState` sequence | typed state subsequence | `KEEP` |
| Exp1 H/W selection | `python -m exp.exp1.development.hstar`; `wstar` | Historical Development model-size/window selection | local Data2 development preparation/cache | selection evidence and checkpoints | PRE development, M1 lifecycle | `REMOVE` from new active experiments; retain as historical provenance |
| Exp1 signed refreeze / warning freeze | `signed_refreeze.py`, `warning_freeze.py`, `warning_operating_point.py`, `warning_evaluation.py` | Historical V1 signed-model and warning operating-point production | V1 caches/checkpoints/scenarios | V1 frozen artifacts and warning metrics | legacy M1 scenario/warning APIs | `REMOVE` from new active experiments; retain historical files |
| Exp2 representation transforms | `exp/exp2/representations.py` | Weighted joint medoid and marginal-preserving lineage corruption | legacy scenario dictionaries | transformed scenarios plus audit | legacy M1 fields | `REUSE_WITH_ADAPTATION` |
| Exp2 metrics | `exp/exp2/metrics.py` | Consequence/ranking distortion and decision disagreement | action-value mappings | scalar metrics | pure Python | `REUSE_WITH_ADAPTATION` |
| Exp2 generic runner | `exp/exp2/runner.py` | Old P-F/P-C/D-F/D-C/lineage variant labels only | precomputed metrics | generic runner output | `BaseRunner` | `REWRITE` |
| Exp3 ablation protocol | `exp/exp3/{runner,ablations,metrics}.py` | Old evidence/coverage/induced-consequence ablations | legacy formal artifact dictionaries | copied ablations and lane metrics | old M2/M3/M4 fields | `REMOVE` from new Exp3; reusable pure helpers may move to diagnostics |
| Exp3 LLM audits | `exp/exp3/llm_audit.py`, `exp/exp234/llm_audit_v2*.py` | Auxiliary DeepSeek operational reasonableness audit | prepared cases | cached/API audit records | external API client | `REMOVE` from new Exp1-Exp4 path; retain as separate auxiliary audit |
| Exp4 protocol | `exp/exp4/runner.py` | Old sensitivity/portability/deployability labels | precomputed metrics | generic runner output | `BaseRunner` | `REWRITE` |
| Exp4 portability | `exp/exp4/portability.py` | Data1 support transitions and no-silent-substitution gates | typed support-state rows or source text | transition rates / hard gates | PRE raw schema tokens | `KEEP` |
| Exp4 strata | `exp/exp4/strata.py` | Apply Development-frozen strata without retraining | principal rows + frozen bins | annotated rows | common stratification | `REUSE_WITH_ADAPTATION` |
| Exp4 runtime/ranking metrics | `exp/exp4/metrics.py` | Top-1/rank overlap and latency p50/p95/p99 | ranking lists or latency rows | scalar summaries | pure Python | `REUSE_WITH_ADAPTATION` |
| Exp234 scenario artifact | `python -m exp.exp234.scenario_artifact` | Historical V1 M1 Development scenario materialization | V1 cache/model/local Data2 | Parquet scenario/node artifacts | legacy M1 sampler | `REMOVE` from active path; preserve artifacts as historical-only |
| Exp234 Development executor | `python -m exp.exp234.development_execution` | Historical Exp2-Exp4 temporary analysis | V1 scenarios, old M2 five-component registry, legacy M3 response | Development Parquet/manifests | dictionary M2 path, legacy M3 response | `REMOVE` |
| Fixture closure | `python -m exp.development_closure` | Small offline old-protocol component demonstration | embedded fixtures | diagnostic closure JSON | old Exp2-Exp4 helpers | `REMOVE` from readiness evidence |

## Summary

The repository has useful infrastructure but no current experiment implementation aligned to the newly frozen Exp1-Exp4 philosophy. The active migration unit is therefore a new typed experiment layer. Historical scripts and artifacts should remain readable for provenance, but they must not be imported by the new runners or counted as implementation readiness.

