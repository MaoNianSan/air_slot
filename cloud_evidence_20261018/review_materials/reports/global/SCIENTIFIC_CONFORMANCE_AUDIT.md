# Global Scientific Contract Conformance Audit

> Historical audit snapshot before the final pre-real-data implementation closure. For the current
> status of the M1 ancestral sampler, PRE target support, M3 registry contracts, M4 response sampler,
> typed PRE-M4 chain, and bounded smoke, use
> `reports/pre_real_data/IMPLEMENTATION_CLOSURE.md` and `VALIDATION_SUMMARY.md`.

Date: 2026-08-12  
Method: read-only-first source audit, followed only by local corrections of unambiguous contract errors  
Authoritative semantics: `mission.md`, `roadmap.md`, `tech-stack.md`, manuscript `(14)`  
Authoritative physical structure: `framework.txt`

## Executive determination

| Readiness dimension | Determination | Meaning |
|---|---|---|
| `ENGINEERING_CONFORMANCE` | **PASS** | Source imports, static boundaries, modularity, complete tests, compile validation, and deterministic foundation artifact checks pass. |
| `SCIENTIFIC_SPECIFICATION_CONFORMANCE` | **MISMATCH** | Important core contracts are present, but M1 aligned sampling, M4 Bernoulli-Beta response, PRE production completeness, experiments, and provenance promotion are not scientifically complete. |
| `REAL_DATA_READINESS` | **DEVELOPMENT_ONLY** | Bounded real reads work for selected sources; full canonical PRE publication, complete source availability, production manifests, real M1 training/calibration, and full-chain validation do not. |
| `PAPER_EXPERIMENT_READINESS` | **NOT_IMPLEMENTED** | Current Exp1-Exp4 runners replicate an input scalar across declared variant names. They are not the frozen paper protocols and cannot support paper promotion or claims. |

No middle, paper-full, large real-data, model-training, formal experiment, promotion, or LLM run was executed.

## Conformance matrix

| AREA | REQUIREMENT | IMPLEMENTATION | STATUS | EVIDENCE | ACTION |
|---|---|---|---|---|---|
| Framework | No new top-level architecture or duplicate science packages | Top level has `model/`, `exp/`, configs/registries/validation/reporting support; the previously proposed orchestration package is absent | PASS | `framework.txt`; repository root; `reports/foundation/FRAMEWORK_CONFORMANCE_AUDIT.md` | None |
| Framework | Dataset logic stops at PRE adapters | Raw names occur in PRE canonical/adapters only; M1-M4 do not reference BTS/OpenSky columns | PASS | `model/PRE/adapters/`, `model/PRE/canonical/`; raw-token scan of `model/M1`-`M4` | None |
| Dependencies | Formal model does not import experiments; experiments do not redefine model | Static scan has zero FAIL | PASS | `validation/dependency_rules.py`; `tests/static/test_dependency_boundaries.py` | None |
| PRE | `tau_avail <= decision_time` | Production selection admits only episode-member records with availability at/before cutoff and excludes `POSTHOC_ONLY` | PASS | `model/PRE/evidence/publication.py`; integration future-leakage test | None |
| PRE | Principal replay is event-time, lag 0; 5/10 only sensitivity | Principal scientific config now freezes 0 and sensitivity `[0,5,10]`; PRE CLI defaults to 0; real smoke explicitly uses diagnostic 5 | PASS | `configs/scientific/foundation.yaml`; `model/PRE/cli.py` | Keep real smoke labelled diagnostic |
| PRE | Replay lag applied exactly once | Canonicalizer produces availability time; selector now compares that time directly to cutoff | PASS | `model/PRE/canonical/normalization.py`; `model/PRE/evidence/admissibility.py`; double-lag negative test | None |
| PRE | Post-hoc outcomes never enter inference | BTS actuals are nested `POSTHOC_ONLY`; publication excludes post-hoc basis | PASS | `canonicalize_ontime_row`; `select_and_publish` | Needs real end-to-end leakage validation |
| PRE | Object ABSTAIN does not invalidate valid node | Node-level `ABSTAINED` requires critical invalidation; data1 fixture locally abstains R_OB | PASS | `DecisionNodeRecord`; `build_pre_state`; `test_node_object_abstention.py` | None |
| PRE | Support monotonicity, no undeclared fallback | Evidence rank and fallback checks reject upgrades/unregistered fallback | PASS | `model/common/enums.py`; `model/PRE/evidence/support.py` | Expand checks to every production transformation |
| PRE | No silent forward fill/proxy/zero | No forward fill exists; unsupported formal values require null+reason. Missing M2/M4 parameters now fail | PASS | value-object validators and new negative tests | M1 numerical masks remain explicit representation, not support upgrades |
| PRE | Production PRE publishes complete state/ledger/lineage/references/targets/manifests | `publish_production_pre` only publishes `current_state` and one R_IB target; CLI `publish` merely counts partitions | NOT_IMPLEMENTED | `model/PRE/pipeline.py`; `model/PRE/cli.py` | Implement complete production publication before real formal run |
| PRE | Cache/resume verifies all scientific dependencies | Cache verifies registry/config only; no model/action/valuation registry or completed-partition validation | NOT_IMPLEMENTED | `model/PRE/cache/resume.py` | Extend production run manifest/resume contract |
| Dataset | data1/data2 independent; no physical pooling | Independent IDs/profiles and disabled overlay are enforced | PASS | adapter description, capability registry, integration independence test | None |
| Dataset | data1 trajectory-rich; data2 event-rich post-hoc | Profiles and capability ceilings match | PASS | `registries/dataset_capabilities.yaml`; metadata profiles | Needs coverage validation on full data |
| Dataset | data1 R_OB ABSTAIN; no departure proxy replacement | Foundation target support makes data1 R_OB inactive/ABSTAIN; derived events retain separate naming | PASS | `model/PRE/foundation.py`; `scientific_variables.yaml` | Production PRE must reproduce this target support |
| Dataset | All audited source readers available | OpenSky/METAR/Eurostat/OurAirports/BTS/reference paths exist; DB1B and T-100 source directories currently contain no files | NEEDS_REAL_DATA_VALIDATION | adapter registry; bounded reader tests; dataset profiles | Obtain/verify missing DB1B/T-100 files before full run |
| Dataset | Adapter source identity matches scientific rule identity | METAR unified as `iem_metar`; Eurostat registered as `json_stat` | PASS | `source_adapter_registry.yaml`; `data_usage_rules.yaml` | None |
| M1 | One-layer unidirectional GRU, H=8; H=16 sensitivity; no attention/stack/bidirectional/TO head | Architecture is one GRU layer, unidirectional, H=8 in principal/smoke; three ordered heads only | PASS | `model/M1/network.py`; scientific config; architecture test | Add explicit production constructor from frozen config |
| M1 | Formal IB -> OB -> TX conditional factorization | Training forward conditions OB on IB and TX on IB/OB, using teacher labels or probability-weighted embeddings | PASS | `OrderedEventGRU.forward` | Needs real training and calibration validation |
| M1 | Five-minute categorical bins with overflow | Contract enforces five-minute principal config and overflow class | PASS | `TargetBinContract`; scientific config | Finite maxima remain development-frozen |
| M1 | Inactive targets masked/ABSTAINED | Loss masking exists; sampler now retains ABSTAIN as null rather than sampling | PASS | `TargetLabel`, losses, `aligned_sample`; targeted test | Integrate target support from production PRE automatically |
| M1 | Interval labels use probability marginalization | `interval_nll` uses log-sum probability over bins with positive interval overlap | PASS | `model/M1/loss.py`; interval test | Validate edge semantics on real reconstructed intervals |
| M1 | Observed-event contraction | Stage validator requires observed IB/OB as stage advances and fixes observed values | PASS | `model/M1/scenarios.py`; contraction test | Production node-to-observed mapping not implemented |
| M1 | Stable scenario identity excludes decision time | Uniform key is seed+episode+scenario+target; decision node/time excluded | PASS | `_uniform`; stable scenario test | None |
| M1 | Principal S=1000; smoke explicit 64; exact horizons/thresholds | Principal config now records S=1000, horizons `[0,30,...,480]`, thresholds `[15,30,60]`; no formal horizon-output interface exists | DEVELOPMENT_ONLY | scientific config; tech stack; `M1Pipeline` | Implement horizon evaluation and execution profiles |
| M1 | Sequential aligned sampling uses sampled IB to condition OB and sampled IB/OB to condition TX | Current sampler draws independently from precomputed head marginals; it does not re-run conditional heads per sampled upstream state | MISMATCH | `model/M1/scenarios.py`; `M1Pipeline.predict_distributions` | Implement true ancestral conditional scenario generation before formal inference |
| M1 | Training/calibration/save/load/evaluation production pipeline | Smoke training and basic temperature/evaluation functions exist, but no production fit/calibrate/cohort pipeline or real artifact manifest | NOT_IMPLEMENTED | `model/M1/cli.py`, `pipeline.py`, `calibration.py`, `evaluation.py` | Implement before middle/paper-full run |
| M2 | Exactly seven components | Fixed tuple contains all seven and each scenario outputs seven rows | PASS | `model/M2/contracts.py`; M2 tests | None |
| M2 | Deterministic, scenario-preserving, no future predictor/effect estimator | Pure mapping retains decision node/scenario ID; no learned predictor/action input | PASS | `M2Mapper` | None |
| M2 | Unsupported is null, never zero | Missing targets/components abstain; missing required context now raises typed error | PASS | `model/M2/drivers.py`; M2 negative tests | Audit future production drivers similarly |
| M2 | Native quantities separate from Constructed Units | `NativeQuantity` and `ConsequenceRow.constructed_cu` are separate | PASS | M2 contracts/valuation | None |
| M2 | Formal and observed outcome evaluation separate | Reconstruction is explicitly `EVALUATION`; mapper consumes formal scenario/context | PASS | `model/M2/evaluation.py` | Real reconstruction is only a stub |
| M2 | Valuation parameters scientifically frozen; monetary bridge bounded | Only `ValuationRegistry.smoke()` with `DEV-1` multipliers exists; no 1 RMB/CU reporting bridge is implemented | DEVELOPMENT_ONLY | `model/M2/valuation.py` | Freeze valuation registry and wording before formal use |
| M3 | Exactly approved 23 templates including A00 | Registry loads exact ordered set | PASS | `registries/action_templates.yaml`; registry test | None |
| M3 | Input is PRE state + frozen registry; no M2 scenario input | Instantiator receives PRE dictionary and registry only | PASS | `model/M3/instantiate.py` | Strongly type PRE projection in production |
| M3 | FALSE remove, UNKNOWN retain, TRUE retain | Implemented exactly | PASS | `instantiate_candidates`; test | None |
| M3 | Footprints use seven-component M2 ontology | Existing mappings use ontology names, but schema does not reject unknown component keys | MISMATCH | action registry; `ActionTemplate` lacks component-key validation | Add registry schema validator before formal use |
| M3 | Response provenance never upgrades public scenario assumptions | Default provenance is `PURE_SCENARIO`; no template claims empirical action logs | PASS | action registry and test | Keep formal lane restrictions |
| M3 | Episode-specific action parameters actually instantiated | Candidate parameters currently contain only episode/node IDs; target/timing/resource parameters are not template-specific | NOT_IMPLEMENTED | `instantiate_candidates` | Implement per-template parameter extraction from PRE |
| M4 | Consumes PRE support + M1 + M2 + M3; raw columns none | Raw dependency is none, but API accepts no PRE support object and cannot invalidate baseline by PRE/M2 support contract | MISMATCH | `evaluate_decision` signature and logic | Add typed PRE/M1/M2/M3 decision request before formal use |
| M4 | Four lanes; only FORMAL ranked | Lanes exist; authoritative ranking filters FORMAL only | PASS | `lanes.py`, `decision.py`; formal-prefix test | None |
| M4 | Post-action equation; opportunity gates mitigation and induced consequences | Equation implemented; audit fixed induced consequence so closed opportunity adds neither term | PASS | `decision.py`; manuscript Eq. 47-48; new test | Separate attempt/response-induced terms in future schema |
| M4 | Exact A00 identity | A00 copies every pre-component per scenario | PASS | `decision.py`; A00 test | None |
| M4 | Principal lambda=.25, alpha=.90; lower J ranks first | Defaults and config match; sort ascending by J | PASS | `decision.py`; scientific config | None |
| M4 | Bernoulli-Beta response with stable action-level realization | Missing parameters now fail, but implementation uses Bernoulli times fixed mean; no Beta intensity draw and response is keyed by component instead of one action-level draw | MISMATCH | `model/M4/response.py`; manuscript Eq. 36-38 | Implement frozen Bernoulli-Beta draw and declared shared-driver semantics |
| M4 | Diagnostics do not alter ranking | Only J and template ID tie-break order ranking | PASS | `decision.py` | Diagnostics themselves are mostly absent |
| M4 | Ranking@1/2/3/5 are prefixes without fill | Implemented as prefixes; unavailable depths are null | PASS | `EpisodeDecision`; ranking test | None |
| Experiments | E1=C1, E2=C2, E3=C3, E4 robustness | Package names/variant labels broadly follow contribution organization | PASS | `exp/exp1`-`exp4` | Package organization only; protocol status below |
| Exp1 | Required baselines/analyses; Joint NLL primary | Variant list omits explicit history-window and contraction variants; runner copies provided scalar across all variants and does no M1 evaluation | NOT_IMPLEMENTED | `exp/exp1/runner.py`; `BaseRunner` | Implement frozen E1 protocol and joint NLL |
| Exp2 | Point/Distributional x Flight/Full; lineage shuffle preserves marginals | Labels exist, but no scenario transformation, shuffle, metrics, or marginal-preservation check | NOT_IMPLEMENTED | `exp/exp2/runner.py` | Implement lineage-aware E2 protocol |
| Exp3 | Candidate support, contract ablations, mean/CVaR, formal outcomes | Labels exist; no ablation isolation, candidate statistics, or formal decision metrics | NOT_IMPLEMENTED | `exp/exp3/runner.py` | Implement E3 evaluation on frozen artifacts |
| Exp3 LLM | Evaluation-only; no call in audit | Provider absence returns `NOT_RUN`; no provider invoked | PASS | `exp/exp3/llm_audit.py`; test | Add frozen case-selection stream later |
| Exp4 | Robustness only, not final-test selection | Parameter labels exist and no selector exists; no actual robustness computation | NOT_IMPLEMENTED | `exp/exp4/runner.py` | Implement robustness protocol without model selection |
| Experiments | Episode chronological split; paired bootstrap 2000 | Split prevents episode crossing; bootstrap default now 2000 but is not paired-contrast aware and split lacks frozen Jan-Jun/Jul/Aug-Sep/Oct-Dec profile | DEVELOPMENT_ONLY | `split.py`; `bootstrap.py` | Implement named chronological profile and paired contrasts |
| Formal/eval | `O_eval` cannot modify `O_formal` | Evaluation functions are separate; no path writes model state | PASS | model evaluation modules and exp dependency direction | Add immutable formal artifact validation |
| Dataset roles | data2 main; data1 appendix | Base runner and promotion enforce fixed dataset-role mapping; main-text promotion rejects data1 | PASS | `BaseRunner`, `exp/promotion.py`; negative test | None |
| Promotion | Canonical paper_candidate, validated provenance chain, single numeric authority | `paper_numbers.json` exporter exists, but promotion copies the whole run and does not validate source-table -> evaluation -> formal -> PRE -> lineage chain | NOT_IMPLEMENTED | `exp/promotion.py` | Implement allowlisted paper candidate and provenance validator |
| Reporting | Figure four-piece/table three-piece and metadata | Basic bundles exist; generators do not validate complete required metadata or artifact provenance | DEVELOPMENT_ONLY | `exp/reporting/` | Add schemas and source-artifact validation |
| Runtime artifacts | Obsolete smoke and diagnostic outputs must not be mistaken for current formal evidence | Stale runtime, canonical-smoke, experiment-smoke, audit scratch, and rendered-manuscript artifacts were removed; only the runtime-area README remains | PASS | `outputs/runtime/`; `outputs/experiments/` | Regenerate only through a validated current pipeline |
| CLI | Shared CLI, execution profiles, runtime manifests/progress/resume/cleanup | Module-specific smoke CLIs exist; no framework-approved shared CLI or paper execution mode | NOT_IMPLEMENTED | PRE/M1/M2/M4/exp CLIs; absence of shared entry point | Resolve physical placement under frozen framework before implementation |
| Validation | Actual global scientific invariants enforced | Foundation validation and tests cover many local invariants, but validation CLI still fixture-scoped and has no global scientific audit command | DEVELOPMENT_ONLY | `validation/cli.py`, this audit | Implement machine-readable global checks before middle/full |
| Modularity | <=250 preferred; review >350; refactor >500 | 149 Python files audited; max 145; zero above thresholds | PASS | `validation/code_size.py`; static test | None |

## Critical blockers before any middle, paper-full, or large real-data run

1. Implement true M1 ancestral conditional sampling, not independent marginal draws from one forward pass.
2. Complete production PRE publication and target-support propagation, including data1 R_OB local abstention.
3. Implement real M1 training, calibration, horizon evaluation, frozen artifacts, and validation manifests.
4. Freeze M2 valuation parameters and implement a provenance-complete valuation registry.
5. Instantiate episode-specific M3 parameters and validate ontology keys.
6. Implement the actual Bernoulli-Beta response draw and typed PRE/M1/M2/M3 request in M4.
7. Replace scalar-repetition experiment runners with the specified E1-E4 protocols.
8. Implement strict canonical-run/paper-candidate provenance validation and single-number authority chain.
9. Resolve shared CLI placement without changing the frozen framework.
10. Verify missing DB1B/T-100 source availability and complete bounded-to-production real-data validation.

## Verification after audit corrections

| Check | Result |
|---|---:|
| Complete test suite | PASS: 68 passed |
| Compile validation | PASS |
| Foundation validation | PASS |
| Static dependency/modularity tests | PASS |
| File-size audit | PASS: 149 files; zero above 250/350/500 |
| Foundation fixture SHA-256 | unchanged: `44A418F4F6F47B091BC53E99A722F453A32BA9CFCF5CDC12E6A152C18BC70926` |

## Stop boundary

This audit deliberately stops without training, full experiments, paper promotion, LLM calls, or architecture changes. The implementation is engineering-testable but is not scientifically or paper-run complete.
