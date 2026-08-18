# Experimental Evaluation — English Draft (Air Slot V5)

> Working manuscript artifact for the Experimental Evaluation / Results sections.
> Source authority: GitHub `MaoNianSan/air_slot` main HEAD `7e6713678572ba772221c5ce980253ddbad43261` (2026-08-18) plus the locally frozen
> summaries that the pushed tracked summaries reproduce.
> All numbers are **Development evidence** (`DEVELOPMENT_ONLY`, `FINAL_TEST_ACCESS_COUNT=0`, `PAPER_FULL_RUN=FALSE`).
> Not committed to Git; edit freely.

---

## A. Source-State Audit (2026-08-18)

- `GITHUB_HEAD = 7e6713678572ba772221c5ce980253ddbad43261`; `HEAD_DATE = 2026-08-18`.
- Exp1 result availability: **available** (Development). Frozen freeze
  `AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE` (hash `sha256:a3ef4bd2...1c46`); GitHub carries the operating-point protocol
  `EXP1_WARNING_OPERATING_POINT_PROTOCOL_V1.json`, signed bundle manifest, principal S=250 inference rows, and the reproduced
  summary tables in `docs/TEMPORARY_DEVELOPMENT_REPORT_20260818.md` (pushed). Final Test (2019-10..12): untouched.
- Exp2 result availability: **available** (Development temporary). Pushed
  `docs/results/EXP2_DEVELOPMENT_TEMP_RESULT_SUMMARY.md`. Authoritative formal ranking: `BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN`.
- Exp3 result availability: **partially available** (Development). Pushed
  `docs/results/EXP3_DEVELOPMENT_RESULT_SUMMARY.md` and `docs/results/EXP3_DEEPSEEK_V2_AUDIT_SUMMARY.md`. M4-gated estimates: `PENDING`.
- Exp4 result availability: **design only**. No tracked result summary on GitHub; only development indicators inside
  `docs/EXPERIMENT_V5_IMPLEMENTATION_REPORT.md` section H (not a paper-facing result summary).
- Remaining scientific blockers: `M4_MATERIAL_COVERAGE_UNFROZEN` (Exp2 formal ranking, Exp3 ablations and authoritative coverage,
  Exp4 m4-ranking lanes); Final Test untouched; S=1000 final scale not run; hard-case stratum not frozen;
  flight-scope point-collapse metrics not recorded in Exp2 V1.

---

## B. Exp1-4 Experimental Design Map (paper-facing)

| Experiment | Transportation question | Principal dataset | Scientific comparison | Independent unit | Repeated unit | Numerical unit | Principal metric | Secondary metrics | Frozen parameters | Current result availability | Current blockers | Permitted claim | Forbidden claim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Exp1 | How early can recovery risk be recognized? | Data2 Development (2019-08/09); Train Jan-Jun, Calibration Jul | CURRENT (30-min window) vs FIXED_HISTORY vs ADAPTIVE_HISTORY at theta10 (target FPR 0.1) | episode (120,092 positive / 826,133 negative evaluable) | decision node (13,608,096) | scenario (S=250 exact exceedance draws per node) | DecisionWindowGain | achieved FPR, episode recall, sustained recall, median/IQR risk lead | H=32, W=30 min; theta10; S=250 (S=500 paired sensitivity subset) | Available (Development freeze `sha256:a3ef4bd2...1c46`) | Final Test not run; S500 materiality `NOT_PRE_REGISTERED` | "Bounded recent history retains the useful temporal signal; extending admissible history to the full episode creates no additional warning-window benefit (DWG<0)" | "ADAPTIVE improves FIXED"; "history extends the actionable recovery decision window" (needs Final Test + controlled FPR) |
| Exp2 | When does joint uncertainty materially affect consequence assessment and recovery comparison? | Data2 Development; frozen M1 scenario artifact (128 episodes / 1,824 nodes / 250 scenarios per node) | DISTRIBUTIONAL (aligned, q=0) vs POINT COLLAPSE (frozen weighted joint medoid); ALIGNED vs LINEAGE-CORRUPTED (q = 0.25/0.50/0.75/1.00) | episode (128) | decision node (1,824) | scenario (250 per node; 456,000 total, **not** independent observations) | ConsequenceDistortion | ActionGapDistortion, Top1Disagreement, PairwiseRankingReversalRate, RankingAt3Overlap, ReferenceObjectiveSelectionPenalty | M1 scenario artifact `sha256:ca3370a3...1dfec`; M2/M3 frozen registries | Available (Development temporary, `NOT_FINAL_PAPER_RESULT`) | `EXP2_AUTHORITATIVE_FORMAL_RANKING = BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN` | "Point collapse materially alters the reconstructed consequence representation relative to the frozen distributional scenario representation in this Development cohort" | "Joint uncertainty changes the authoritative recovery ordering"; "point collapse always dominates lineage corruption"; ROSP renamed "regret" |
| Exp3 | When is a recovery recommendation sufficiently supported? | Data2 Development; frozen M2/M3; 23 candidate actions per node | Support-boundary characterization: candidate -> structurally admissible -> numerically evaluable -> lane-assigned -> authoritative decision (M4-gated) | episode (128) | decision node (1,824) | scenario (250 per node) | FormalMultiActionRate, FormalA00Rate, ConditionalRate, ScenarioOnlyRate, AbstainRate | BaselineOnlyFormalRate, InvalidatedTop1Rate, InvalidatedTopKShare, CoverageInflation; DeepSeek V2 auxiliary operational audit | M2 `M2_DATA2_FORMAL_CU_V1`; M3 `M3_RESPONSE_SCENARIO_V1`; M4 lambda=0.25, alpha=0.90 (contract **not** frozen) | Partial (Development support boundary); authoritative estimates `PENDING` | "The framework exposes the boundary between numerically evaluable and evidence-supported recovery decisions" | "Evidence discipline improves recommendation accuracy"; final authoritative multi-action coverage estimates |
| Exp4 | Where does the framework remain useful and trustworthy? | Data1 (portability environment) + Data2; M3 LOW/BASE/HIGH response sensitivity | A. specification robustness; B. operational heterogeneity / boundary; C. cross-evidence-environment portability; D. runtime / degraded mode | episode | decision node | scenario | portability hard gates; sensitivity agreement (top1 / rank agreement) | runtime, degraded-mode gates | M3 LOW/BASE/HIGH; lambda grid; alpha grid | Design only (no tracked result summary) | Final Test not run; portability and sensitivity estimates `PENDING` | "Portability is checked as a static registry-contract gate" (design-level only) | "Data1 is external validation"; any effect-size claim derived from code structure |

---

## C. English Experimental Evaluation Draft

### 4 Experimental Evaluation

### 4.1 Experimental Protocol and Evaluation Boundary

The evaluation is organized around four transportation questions rather than model components:
(i) how early can recovery risk be recognized; (ii) when does preserving joint operational
uncertainty materially change consequence assessment and recovery comparison; (iii) when is a
recovery recommendation sufficiently supported; and (iv) where does the framework remain useful
and trustworthy.

Data2 is the principal environment and Data1 is the portability environment; the two are never
pooled. Within Data2, the temporal split is Train = January-June, Calibration = July,
Development = August-September, Final Test = October-December. Three nested units are used
throughout: an **episode** (an independent empirical unit, a full aircraft-day operational
trajectory), a **decision node** (a repeated observation within an episode at which a recovery
decision is evaluated), and a **scenario** (a numerical representation: aligned exceedance draws
of the operational state given decision-time evidence). Scenarios are not independent
observations; all empirical summaries are episode-balanced or node-level with episode counts
reported.

Development evidence was used only for the frozen model, policy, and threshold choices (H=32,
W=30 minutes; theta10 operating point). The Final Test period was never accessed
(`FINAL_TEST_ACCESS_COUNT=0`), and no `paper_full` run exists; every result below is therefore
Development evidence. Formal outputs are distinct from evaluation perturbations: all Exp1-Exp4
ablations and representation transforms are evaluation-only and never write back into PRE,
M1, M2, M3, or M4.

The formal model chain is PRE (decision-time admissible evidence) -> M1 (signed warning model
`R_IB -> DELTA_OB -> T_TX`, with derived `R_OB`, `T_OB`, `T_TO`, and decision time
`D_TO = max(0, DELTA_OB + T_TX - taxi_ref)`) -> M2 (formal consequence-unit registry
`M2_DATA2_FORMAL_CU_V1`, five principal components: `F_continuity`, `F_execution`,
`F_propagation`, `P_time`, `R_operating`) -> M3 (scenario response registry
`M3_RESPONSE_SCENARIO_V1`, 23 actions; a scenario numerical response is **not** an empirical
causal effect) -> M4 (evidence-bounded lane assignment `FORMAL / CONDITIONAL / SCENARIO /
EXCLUDED`, lambda = 0.25, alpha = 0.90). The M4 material-coverage contract is currently
identifier-only and unfrozen (`M4_MATERIAL_COVERAGE_UNFROZEN`); this boundary is preserved
throughout the experiments.

### 4.2 Exp1: Earlier Operational Risk Recognition

The experiment asks whether historical information creates earlier useful risk recognition, and
whether unlimited episode history adds value beyond a bounded recent window. Three variants share
the frozen signed model: CURRENT (recent 30-minute window), FIXED_HISTORY (a fixed bounded
history representation), and ADAPTIVE_HISTORY (full episode history). Operating points are frozen
at theta10 (target false-positive rate 0.1), and the principal cohort is S=250 scenarios per node
over 946,981 episodes (13,608,096 nodes); 120,092 positive episodes and 826,133 negative episodes
are evaluable at the operating point (coverage 0.996 and 1.000 respectively; 431/300 abstain; 25
unknown episodes abstain).

At theta10, CURRENT achieves 4.99% episode recall and 4.56% sustained warning recall at a 9.50%
achieved FPR with a 105-minute median risk lead (IQR 62 min); FIXED_HISTORY achieves 5.18% recall
and 4.81% sustained recall at 9.84% FPR with a 108-minute median lead; ADAPTIVE_HISTORY achieves
4.65% recall and 4.27% sustained recall at 8.76% FPR with a 109-minute median lead (IQR 61 min).
The principal contrast, DecisionWindowGain (ADAPTIVE - FIXED in per-episode sustained warning
lead, N = 120,092 positive episodes), is **-0.623 min** (median 0.0; share of episodes with a
positive gain 0.34%; share >= 30 min 0.33%).

Operationally, this implies that bounded recent history captures most of the useful temporal
signal: the lightweight recurrent representation retains decision-time information, but extending
the admissible history to the full episode does not create an additional warning-window benefit in
this Development cohort. Historical information is useful; more history is not always better.
The result direction is preserved: no formulation of these Development results supports the claim
that adaptive history improves fixed history. A paired S=500 sensitivity subset (47,452 episodes,
5,977 positive; identical deterministic subset) reproduces the sign of the contrast
(s250-subset DWG -0.858 min, s500-subset -0.633 min, s500-s250 +0.225 min) with a mean absolute
probability change of 0.0139 (CURRENT); the difference is not pre-registered against a frozen
materiality threshold (`NOT_PRE_REGISTERED`).

### 4.3 Exp2: Decision Value of Joint Operational Uncertainty

The experiment asks when preserving joint operational uncertainty materially changes the
reconstructed consequence representation and the recovery comparison. The principal controlled
comparison holds all scientific conditions fixed and contrasts the DISTRIBUTIONAL representation
(frozen aligned M1 scenarios through the frozen M2 chain, reference q=0) with POINT COLLAPSE
(the frozen weighted joint medoid through the same M2 chain). The cohort is 128 independent
episodes, 1,824 decision nodes, 250 scenarios per node (456,000 numerical scenarios in total);
the distributional reference is exactly self-consistent (all distortion 0.0, top-3 overlap 1.0).

Point collapse materially alters the consequence representation: ConsequenceDistortion is
1.727 (node mean) / 1.762 (episode-balanced mean), with tail consequence differences of 1.720
(p90) and 1.916 (max, node level). Distortion concentrates in early and high-uncertainty
operating states: PRE_IB nodes show 3.182 (N=269) versus 1.502 for POST_IB_PRE_OB (N=1,502) and
0.735 for POST_OB_PRE_TO (N=53); high-uncertainty nodes show 1.856 (N=462) versus 1.684 for the
comparison group (N=1,362). This is consistent with the idea that preserving uncertainty matters
most before the operational state has contracted.

A second mechanism analysis corrupts the joint lineage of aligned scenarios while preserving
marginals (marginal-preserving within-scenario shuffle, q = 0.25/0.50/0.75/1.00). Consequence
distortion rises monotonically with corruption severity (0.042 -> 0.069 -> 0.090 -> 0.114 at node
level) but remains substantially smaller than the distortion associated with collapsing the
predictive distribution to a point representation in this Development cohort. This does not imply
that lineage is unimportant, nor that point collapse always dominates lineage corruption; it is
Development evidence only.

Scenario-conditioned action comparisons show non-trivial sensitivity to the uncertainty
representation (Top1Disagreement 0.489, ActionGapDistortion 0.231, PairwiseRankingReversalRate
0.121, RankingAt3Overlap 0.701, ReferenceObjectiveSelectionPenalty 0.054 normalized / 0.097 raw).
These outputs are SCENARIO_CONDITIONED, NON_AUTHORITATIVE, TEMPORARY_DEVELOPMENT_ONLY: they are
not authoritative rankings, optimal actions, or causal action effects, and
ReferenceObjectiveSelectionPenalty is not regret. Authoritative formal ranking remains blocked
by the unfrozen M4 material-coverage contract
(`EXP2_AUTHORITATIVE_FORMAL_RANKING = BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN`).

### 4.4 Exp3: Reliability under Bounded Evidence

The experiment asks when a recovery recommendation is sufficiently supported, and exposes the
narrowing chain candidate -> structurally admissible -> numerically evaluable -> evidence-supported
(lane-assigned) -> authoritative decision. On the Development cohort (1,824 nodes, 128 episodes,
23 candidate actions per node: A00 plus 22 non-A00), all nodes are numerically scenario-evaluable
(FormalMultiActionRate 1.0; FormalA00Rate 1.0; ConditionalRate 1.0; ScenarioOnlyRate 1.0;
BaselineOnlyFormalRate 0.0), and no numerically evaluated recommendation is invalidated by the
support check (InvalidatedTop1Rate 0.0; CoverageInflation 0.0).

The boundary is sharp: because the M4 material-coverage contract is not frozen, zero of 1,824
nodes currently receive an authoritative decision; every node abstains with blocker
`M4_MATERIAL_COVERAGE_UNFROZEN` (AbstainRate 1.0). The current Development evidence is sufficient
to characterize the support boundary but not yet to report the final authoritative multi-action
coverage estimates. All M4-gated ablations (FULL_CONTRACT, NO_EVIDENCE_DISTINCTION,
NO_INDUCED_CONSEQUENCE, NO_MATERIAL_COVERAGE_GATE) remain `NOT_RUN_M4_BLOCKED`; each ablation is
evaluation-only and would intentionally violate one decision-support rule at a time to quantify
how apparently attractive but insufficiently supported recommendations would be promoted under a
weaker contract.

The DeepSeek operational audit is an auxiliary, evaluation-only component of Exp3. Using the
frozen model `deepseek-v4-flash` under a cost-first rule with a quality gate (no escalation),
the pilot passed on 50 cases (schema pass 0.98; parse failure 0.02; all error-detector gates
0.0), and the principal run covered 128 episodes x 3 repeated judgements = 382 judgements:
ACCEPT 15 (3.93%), ACCEPT_WITH_RESERVATIONS 268 (70.16%), REJECT 0 (0.00%),
INSUFFICIENT_INFORMATION 99 (25.92%). The external audit rarely endorsed recommendations
unconditionally; most were considered plausible only with explicit reservations, while a
non-trivial subset could not be responsibly assessed from the available decision-time state
(repeat exact agreement 0.453). This pattern is consistent with the framework's distinction
between numerical scenario evaluability and evidential authority. The audit is state-conditioned,
provides no feedback to the model (`LLM_TO_MODEL_FEEDBACK=FALSE`), is not ground truth, and does
not validate the model or modify M3/M4.

### 4.5 Exp4: Robustness, Operational Boundary, and Portability

Exp4 is currently design-only; no tracked result summary exists and no effect-size claims are
made. The design covers four facets: (A) specification robustness (M3 LOW/BASE/HIGH response
sensitivity, lambda and alpha grids); (B) operational heterogeneity and boundary (strata, support
transition); (C) cross-evidence-environment portability to Data1 -- a portability check, not an
external validation, with no pooling of Data1 and Data2; and (D) runtime and degraded-mode
behavior. Portability hard gates are static registry-contract checks; numerical portability
estimates and all Final-Test-based statements are `PENDING`/`BLOCKED` until the M4 contract is
frozen and the Final Test is authorized.

---

## D. Exp1 Results Draft (standalone)

**Cohort and operating point.** Frozen signed M1 model (H=32, W=30 min); Development cohort
2019-08/09; S=250 scenarios per node; 946,981 episodes, 13,608,096 nodes; positive evaluable
120,092 (coverage 0.996), negative evaluable 826,133 (coverage 1.000), unknown 25 (abstain).
Operating point theta10 (target FPR 0.1) per variant; freeze hash `sha256:a3ef4bd2...1c46`.

**Table 1 -- Exp1 operating points (Development, theta10).**

| Variant | theta10 threshold | Achieved FPR | Episode recall | Sustained warning recall | Median lead (min) | IQR lead (min) |
|---|---|---|---|---|---|---|
| CURRENT (30-min window) | 0.364 | 9.50% | 4.99% | 4.56% | 105 | 62 |
| FIXED_HISTORY | 0.384 | 9.84% | 5.18% | 4.81% | 108 | 62 |
| ADAPTIVE_HISTORY | 0.392 | 8.76% | 4.65% | 4.27% | 109 | 61 |

**Table 2 -- DecisionWindowGain (ADAPTIVE - FIXED, per-episode sustained warning lead; N = 120,092 positive episodes).**

| Statistic | Value |
|---|---|
| Mean | -0.623 min |
| Median | 0.0 min |
| Share of episodes with gain > 0 | 0.34% |
| Share with gain >= 15 min | 0.34% |
| Share with gain >= 30 min | 0.33% |

**Table 3 -- Additional operating points (Development; achieved FPR at target).**

| Variant | FPR @ target 0.05 | FPR @ target 0.2 |
|---|---|---|
| CURRENT | 4.29% | 18.61% |
| FIXED_HISTORY | 4.49% | 19.15% |
| ADAPTIVE_HISTORY | 4.63% | 19.37% |

**S=500 paired sensitivity (Development; 47,452 episodes, 5,977 positive, 682,218 nodes).**
DWG on the identical deterministic subset: s250 -0.858 min; s500 -0.633 min; s500-s250 +0.225
min; mean absolute probability change 0.0139 (CURRENT); node warning-classification disagreement
rate 0.042. Materiality of the s500-s250 difference is `NOT_PRE_REGISTERED` (no frozen
materiality threshold).

**Interpretation.** Did history create earlier useful information? Yes, in the bounded sense:
the windowed variants match or exceed the full-history variant in recall and sustained recall at
controlled FPR, with median leads of 105-109 minutes. Did unlimited episode history add value
beyond a bounded recent window? No: the principal gain is negative (-0.623 min) and essentially
zero for virtually all episodes. The result does not support an "adaptive history improves
warning" claim; it supports the narrower statement that bounded recent history captures most of
the useful temporal signal in this Development cohort.

---

## E. Exp3 Results Draft (standalone)

**Current decision-support coverage state (Development; 1,824 nodes, 128 episodes, 23 actions per node).**

| State | N | Percentage |
|---|---|---|
| Numerically evaluable | 1824 | 100.0% |
| FORMAL lane (A00 only formal; formal_action_count=23) | 1824 | 100.0% |
| CONDITIONAL lane (22 non-null actions) | 1824 | 100.0% |
| SCENARIO lane (all 23 actions) | 1824 | 100.0% |
| Authoritative decision available | 0 | 0.0% |
| Authoritative abstain (blocker `M4_MATERIAL_COVERAGE_UNFROZEN`) | 1824 | 100.0% |
| Relaxed top-1 lane = FORMAL | 1824 | 100.0% |

Lane rates: FormalA00Rate 1.0; ConditionalRate 1.0; ScenarioOnlyRate 1.0; AbstainRate 1.0
(authoritative); BaselineOnlyFormalRate 0.0; InvalidatedTop1Rate 0.0; CoverageInflation 0.0.
All M4-gated fields and ablations: `NOT_RUN_M4_BLOCKED`.

**Scenario vs authoritative distinction.** Numerical M3 scenario response is a scenario-
conditioned numerical representation, not an empirical causal effect, and does not by itself
create FORMAL authority. With no frozen material-coverage contract, every node abstains from an
authoritative decision. The current Development evidence characterizes the support boundary but
does not yet support final authoritative multi-action coverage estimates.

**DeepSeek V2 operational audit (auxiliary; `deepseek-v4-flash`, COST_FIRST_WITH_QUALITY_GATE).**

| Judgement | N | Percentage |
|---|---|---|
| ACCEPT | 15 | 3.93% |
| ACCEPT_WITH_RESERVATIONS | 268 | 70.16% |
| REJECT | 0 | 0.00% |
| INSUFFICIENT_INFORMATION | 99 | 25.92% |

Pilot (N=50): schema pass 0.98, parse failure 0.02, all error-detector gates 0.0. Principal:
382 judgements; repeat exact agreement 0.453; confidence HIGH 95 / MEDIUM 264 / LOW 23;
`LLM_TO_MODEL_FEEDBACK=FALSE`. The audit is state-conditioned, evaluation-only, not ground truth,
and does not validate the model.

**Unresolved M4 boundary.** `M4_MATERIAL_COVERAGE_UNFROZEN` remains the current scientific
boundary; the framework exposes the boundary between numerically evaluable and
evidence-supported recovery decisions. No claim is made that evidence discipline improves
recommendation accuracy.

---

## F. Claim-Support Audit

| Claim | Experiment | Required evidence | Current evidence | Status |
|---|---|---|---|---|
| Bounded recent history retains useful temporal signal for risk recognition | Exp1 | Controlled FPR operating points; recall/lead comparisons across variants | theta10: CURRENT/FIXED recall 4.99%/5.18% vs ADAPTIVE 4.65%; leads 105-109 min; controlled FPR 8.8-9.8% | SUPPORTED (Development) |
| Extending admissible history to the full episode creates earlier useful recognition | Exp1 | Positive DecisionWindowGain with controlled FPR | DWG -0.623 min; share>0 0.34% | NOT_SUPPORTED (Development; negative result) |
| Adaptive history improves fixed history | Exp1 | DWG > 0 at controlled FPR | DWG -0.623 min; S=500 subset reproduces sign | NOT_SUPPORTED (do not write as improvement) |
| Historical information is useful => more history is always better | Exp1 | Monotone benefit with history length | Contradicted: full-history variant is not better | FORBIDDEN (illicit inference) |
| Joint uncertainty changes the reconstructed consequence representation | Exp2 | Distributional vs point-collapse contrast, frozen inputs | ConsequenceDistortion 1.727/1.762; q=0 self-consistency exact | SUPPORTED (Development temporary) |
| Joint uncertainty changes the authoritative recovery ordering | Exp2 | Authoritative formal ranking under frozen M4 contract | Only scenario-conditioned NON_AUTHORITATIVE outputs; M4 unfrozen | PENDING (blocked by `M4_MATERIAL_COVERAGE_UNFROZEN`) |
| Evidence discipline improves decision reliability | Exp3 | Authoritative coverage estimates + ablations | Ablations `NOT_RUN_M4_BLOCKED`; authoritative abstain 100% | PENDING |
| Framework identifies the empirical support boundary | Exp3 | Coverage-state characterization under current contract | 1,824/1,824 numerically evaluable; 0 authoritative; abstain 100% | PARTIALLY_SUPPORTED (Development; final coverage estimates pending) |
| Framework is robust across operating regimes | Exp4 | Sensitivity/strata/runtime results | Design only; no tracked result summary | PENDING |
| Data1 demonstrates portability | Exp4 | Cross-environment numerical portability estimates | Static contract gates only; no numerical estimates | PENDING |
| DeepSeek validates recommendations | Exp3 (auxiliary) | Validation-grade agreement with ground truth | Auxiliary, evaluation-only; `LLM_TO_MODEL_FEEDBACK=FALSE`; not ground truth | FORBIDDEN |

---

## G. Remaining Result Placeholders

- Exp1: Final Test (2019-10..12) operating points and DWG; S=1000 final-run scale; pre-registered materiality for the S500-S250 difference (`NOT_PRE_REGISTERED`).
- Exp2: authoritative formal ranking under a frozen M4 contract (`BLOCKED`); flight-scope point-collapse metrics (not in V1); hard-case stratum (`NOT_FROZEN`).
- Exp3: final authoritative multi-action coverage estimates (`PENDING`); all four ablations (FULL_CONTRACT, NO_EVIDENCE_DISTINCTION, NO_INDUCED_CONSEQUENCE, NO_MATERIAL_COVERAGE_GATE) (`NOT_RUN_M4_BLOCKED`); FormalDecisionLeadTime (not yet available).
- Exp4: all numerical results -- M3 LOW/BASE/HIGH sensitivity tables, lambda/alpha grids, portability estimates, runtime and degraded-mode measurements (`PENDING`; design only).
- DeepSeek: escalation-tier judgements (flash-only under cost-first rule) and final-scale repeat-stability statistics (`PENDING`).
