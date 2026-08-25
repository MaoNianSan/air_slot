# Temporary Development Report — Air Slot (2026-08-18)

> `DEVELOPMENT_ONLY` · `TEMPORARY_REPORT` · `NOT_FINAL_PAPER_RESULT`
>
> `TEMPORARY_DEVELOPMENT_REPORT=TRUE` · `TEMPORARY_REPORT_PURPOSE=INTERIM_PRESENTATION_ONLY` · `PAPER_RESULT=FALSE` · `FINAL_RESULT=FALSE`
> `PRE_REBUILT=FALSE` · `M1_RETRAINED=FALSE` · `H_W_RERUN=FALSE` · `EXP1_RERUN=FALSE` · `EXPENSIVE_UPSTREAM_RERUN_COUNT=0` · `FINAL_TEST_ACCESS_COUNT=0` · `PAPER_FULL_RUN=FALSE`

All numbers below are Development evidence only (2019-08/09). October–December Final Test was never accessed. No upstream rerun; DeepSeek audit reused (no API calls). Full regression baseline reused: **508 passed, 1 skipped**.

## 1. Current model / experiment freeze

| Component | Status |
|---|---|
| PRE (raw → canonical → episodes) | Frozen, not rebuilt |
| M1 (signed warning model + calibration + normalization + taxi reference) | Frozen, not retrained |
| M2 (valuation scales / formal CU registry) | Frozen |
| M3 (numerical response freeze) | Frozen; response seed 20260813 recorded (seed itself not in registry) |
| M4 (material coverage contract) | **UNFROZEN** — identifier only, no frozen artifact |
| Exp1 warning inference | Frozen (S=250 principal + S=500 sensitivity subset) |
| Exp2/Exp3 development execution | Frozen V1 artifacts |
| DeepSeek LLM audit | V2 completed (auxiliary) |

Key hashes:

- Scenario artifact `M1_SIGNED_DEVELOPMENT_SCENARIOS_V1`: `sha256:ca3370a3…1dfec` (1824 nodes, 456,000 scenarios, 128 episodes; `--verify-only` PASS); **reused, no new pure inference** (`M1_PURE_INFERENCE_REUSED=TRUE`, `M1_PURE_INFERENCE=REUSED`).
- Exp1 warning freeze: `sha256:a3ef4bd2…1c46`; artifact bundle `sha256:dc5ec267…2bf7`.
- Exp2 development V1: `sha256:1cf8a7ac…666d`; Exp3 development V1 source_exp2 same.
- Exp2/3/4 component closure: `sha256:ffd6506a…1ee8`; global closure: `sha256:d43ae36f…1b1ad`.
- LLM audit V2: prompt `sha256:771121de…c8af`, schema `sha256:16ca615e…cc88`, contract `sha256:8cc0b226…e350`.

## 2. Exp1 — early risk recognition

Frozen operating point θ10 (target FPR 0.1); episode unit; positive episodes 120,092; negative episodes 826,133; unknown 25 (abstain). Principal S=250 (946,981 episodes, 13,608,096 nodes).

**TABLE A — Exp1 (θ10)**

| Variant | θ10 | Achieved FPR | Recall | Sustained recall | Median lead (min) | IQR lead (min) |
|---|---|---|---|---|---|---|
| CURRENT (30-min window) | 0.364 | 9.498% | 4.990% | 4.556% | 105 | 62 |
| FIXED_HISTORY | 0.384 | 9.843% | 5.184% | 4.806% | 108 | 62 |
| ADAPTIVE_HISTORY | 0.392 | 8.764% | 4.652% | 4.273% | 109 | 61 |

**DecisionWindowGain** (ADAPTIVE − FIXED sustained warning lead, per-episode mean; episodes 120,092): **-0.6234** (median 0.0; share>0 0.339%; share≥15 min 0.336%; share≥30 min 0.331%).

Additional operating points (achieved FPR at target 0.05 / 0.2):

| Variant | FPR@0.05 | FPR@0.2 |
|---|---|---|
| CURRENT | 4.291% | 18.608% |
| FIXED_HISTORY | 4.490% | 19.148% |
| ADAPTIVE_HISTORY | 4.634% | 19.375% |

S=500 sensitivity (paired deterministic subset, 5,977 positive / 47,452 episodes): DWG s250 subset −0.858, s500 subset −0.633, s500−s250 +0.225; node probability mean abs change 0.0139 (CURRENT); no frozen materiality threshold (`NOT_PRE_REGISTERED`).

**Interpretation (frozen result preserved):** ADAPTIVE does **not** beat FIXED. The lightweight recurrent representation retains useful history, but extending the admissible history beyond the frozen 30-minute window does not provide an additional warning-window benefit in the current Development evidence.

## 3. Exp2 — value of joint uncertainty

Question: when does preserving joint operational uncertainty materially change the consequence representation and recovery comparison? Episode unit: 128 episodes; node unit: 1,824 nodes; scenario unit: 250 scenarios/node (456,000 total). Reused verified scenario artifact; aggregation checkpoint against frozen `EXP2_DEVELOPMENT_V1.json` = PASS (all means match to 1e-9).

**TABLE B — Exp2**

| Contrast | N_episode | ConsequenceDistortion (node / episode) | Tail p90 (node) | Top1Disagreement |
|---|---|---|---|---|
| DISTRIBUTIONAL (reference q=0) | 128 | 0.0 / 0.0 | 0.0 | 0.0 |
| POINT COLLAPSE (full scope) | 128 | 1.7272 / 1.7624 | 1.7202 | 0.4890 |
| LINEAGE_CORRUPTION q=0.25 | 128 | 0.0420 / 0.0438 | 0.0443 | 0.0208 |
| LINEAGE_CORRUPTION q=0.50 | 128 | 0.0688 / 0.0712 | 0.0718 | 0.0340 |
| LINEAGE_CORRUPTION q=0.75 | 128 | 0.0898 / 0.0910 | 0.0933 | 0.0417 |
| LINEAGE_CORRUPTION q=q1.00 | 128 | 0.1138 / 0.1145 | 0.1177 | 0.0493 |

Point collapse also changes ranking (node-level): ActionGapDistortion 0.2310, PairwiseRankingReversalRate 0.1214, RankingAt3Overlap 0.7014, ReferenceObjectiveSelectionPenalty (normalized) 0.0536 — **scenario-conditioned, NON-AUTHORITATIVE** (M4 formal ranking blocked).

Stratified ConsequenceDistortion (point collapse, node mean): PRE_IB 3.182 (N=269) · POST_IB_PRE_OB 1.502 (N=1502) · POST_OB_PRE_TO 0.735 (N=53); high-uncertainty nodes 1.856 (N=462) vs 1.684 (N=1362); tight-turnaround nodes 1.535 (N=480) vs 1.796 (N=1344). High-uncertainty nodes also show larger Top1Disagreement (0.602 vs 0.451).

Lineage corruption (frozen q budget 0/0.25/0.5/0.75/1.0): ConsequenceDistortion rises monotonically 0 → 0.042 → 0.069 → 0.090 → 0.114; point collapse (1.73) dominates any corruption level — the point approximation, not lineage noise, is the dominant distortion.

- `EXP2_CONSEQUENCE_RESULTS = VALID_TEMPORARY`; `EXP2_FORMAL_RANKING_RESULTS = BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN`; `EXP2_SCENARIO_CONDITIONED_ACTION_RESULTS` = SCENARIO_CONDITIONED / NON_AUTHORITATIVE / TEMPORARY_DEVELOPMENT_ONLY; `EXP2_LINEAGE_CORRUPTION_TEMP = COMPLETED_DEVELOPMENT_BUDGET`.
- Full Exp2 temporary details: `artifacts/_archive/2026-08-25/exp2_development_temp/EXP2_TEMPORARY_REPORT.md` (+ summary JSON and parquet tables).

## 4. Exp3 — evidence-supported decision boundary

**TABLE C — Exp3 decision/support states (1,824 nodes, 128 episodes)**

| Decision/support state | N | Percentage |
|---|---|---|
| Numerically evaluable | 1824 | 100.0% |
| FORMAL multi-action lane (formal_action_count=23) | 1824 | 100.0% |
| A00-only formal state (a00_formal) | 1824 | 100.0% |
| CONDITIONAL lane (22 non-null actions) | 1824 | 100.0% |
| SCENARIO lane (all 23 actions) | 1824 | 100.0% |
| Authoritative decision available | 0 | 0.0% |
| Authoritative abstain (blocker M4_MATERIAL_COVERAGE_UNFROZEN) | 1824 | 100.0% |
| Relaxed top1 lane = FORMAL | 1824 | 100.0% |

Rates (frozen `EXP3_DEVELOPMENT_V1.json`): FormalA00Rate=1.0, ConditionalRate=1.0, ScenarioOnlyRate=1.0, AbstainRate=1.0 (authoritative), BaselineOnlyFormalRate=0.0; invalidated_top1_rate=0.0; coverage inflation (full−relaxed)=0.0. All M4-gated fields and ablations: `NOT_RUN_M4_BLOCKED`. Candidate actions per node: 23; precondition/support: schedule and taxi reference supported on all nodes.

**Temporary scientific message:** the framework explicitly separates actions that are numerically scenario-evaluable from actions that are sufficiently supported for authoritative comparison. Current public Data2 does not identify real non-null action-response effects, so numerical M3 scenario response does not itself create FORMAL authority. For now: *the framework exposes the boundary between numerically evaluable and evidence-supported recovery decisions* — no claim that evidence discipline improves recommendation accuracy.

## 5. DeepSeek operational explanation audit

**TABLE D — LLM audit V2 (auxiliary; model `deepseek-v4-flash`, COST_FIRST_WITH_QUALITY_GATE, no escalation)**

| Judgement | N | Percentage |
|---|---|---|
| ACCEPT | 15 | 3.93% |
| ACCEPT_WITH_RESERVATIONS | 268 | 70.16% |
| REJECT | 0 | 0.00% |
| INSUFFICIENT_INFORMATION | 99 | 25.92% |

Pilot: N=50, schema pass 0.98, parse failure 0.02, all error-detector gates 0.0. Principal: 128 episodes × 3 repetitions = 382 judgements. Repeat exact agreement 0.453; accept-family agreement 0.453; confidence HIGH 95 / MEDIUM 264 / LOW 23. `LLM_TO_MODEL_FEEDBACK=FALSE`.

**Interpretation:** most model outputs were judged operationally plausible only with explicit reservations (70.2%), while a substantial minority could not be responsibly assessed from the current state information (25.9%). This is an auxiliary, state-conditioned operational reasonableness audit — **it does not validate the model** and was not used to alter M3/M4.

## 6. Current limitations

- **M4 material coverage is not frozen** (`M4_MATERIAL_COVERAGE_UNFROZEN`): all M4 decision lanes, formal multi-action ranking, Exp3 ablations and Exp2 authoritative ranking remain provisional/blocked. No interim rule invented.
- Hard-case stratum: not frozen; not computed. Tight-turnaround / high-uncertainty strata are descriptive derivations from the frozen scenario artifact (definitions in `artifacts/_archive/2026-08-25/exp2_development_temp/exp2_temp_consequence_summary.json`).
- S=250 temporary Development budget (S=500 sensitivity subset reused from Exp1; S=1000 is final-run scale only).
- Exp1 DWG is a Development operating-point result; ADAPTIVE does not beat FIXED; S500−S250 difference is not pre-registered materiality.
- DeepSeek audit is auxiliary only; repeat agreement 0.45 reflects that most outputs carry reservations.
- Point-flight (flight-scope) collapse rows exist in the Exp2 parquet but V1 metrics were recorded for the full-scope point collapse; flight-scope comparison is a final-Exp2 item.
- `M3_RESPONSE_SEED=20260813` is recorded, not registry-frozen.

## 7. Next steps before final experiment freeze

1. Freeze the M4 material-coverage contract as a real artifact (currently identifier-only).
2. Rerun M4-gated lanes: authoritative multi-action ranking, Exp3 ablations, Exp2 formal ranking claims.
3. Final Exp2 additions if protocol requires (e.g., flight-scope collapse metrics, hard-case stratum).
4. One full regression at the next major scientific closure (current baseline 508 passed / 1 skipped reused here).
5. Publication-quality figures from the plot-ready tables in `artifacts/_archive/2026-08-25/exp2_development_temp/figures/`.

---

Artifacts: `docs/TEMPORARY_DEVELOPMENT_REPORT_20260818.md` (this file) · `artifacts/_archive/2026-08-25/exp2_development_temp/EXP2_TEMPORARY_REPORT.md` · `artifacts/_archive/2026-08-25/exp2_development_temp/EXP2_TEMPORARY_MANIFEST.json` · `artifacts/_archive/2026-08-25/exp2_development_temp/exp2_temp_consequence_summary.json` · parquet tables · `figures/*.csv`.

