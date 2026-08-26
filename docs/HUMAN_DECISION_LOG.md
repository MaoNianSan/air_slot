# Air Slot V5 Human Decision Log

This append-only project log records human scientific decisions for the V5 Development freeze.
`PENDING` means that no user decision has been supplied and no affected scientific value may be
frozen.

## D0A_FIXED_HISTORY_SEMANTICS

- decision_id: `D0A_FIXED_HISTORY_SEMANTICS`
- date/time: `2026-08-16T20:43:59+08:00`
- status: `APPROVED`
- question: Define the principal `FIXED_HISTORY(W)` information representation.
- options: Earlier mixed D0 options were superseded by the user's revised decision structure.
- Codex recommendation: `SUPERSEDED`
- user decision: Closed maximum-lookback interval `[t-W, t]` within the current episode, using the same causal GRU family, probabilistic heads, targets, calibration contract, and approved `H_STAR` as the other principal information variants.
- scientific rationale: The only principal scientific difference from ADAPTIVE history is the available causal prefix length; downstream M2-M4 performance cannot select W.
- affected files: `exp/exp1/history.py`; `model/M1/data.py`; Development-only runner and tests
- affected hashes: `PENDING_IMPLEMENTATION`
- reversible_before_paper_full: `YES`

## D0B_MISSING_HISTORY_GRID_SEMANTICS

- decision_id: `D0B_MISSING_HISTORY_GRID_SEMANTICS`
- date/time: `2026-08-16T20:43:59+08:00`
- status: `APPROVED`
- question: Define missing evidence behavior inside CURRENT, FIXED, and ADAPTIVE histories.
- options: `PRESERVE_CANONICAL_GRID`; retrospective row deletion or imputation were rejected.
- Codex recommendation: `PRESERVE_CANONICAL_GRID`
- user decision: Preserve every canonical five-minute node and represent missingness, freshness, evidence, support, and fallback through formal M1 input fields; missing evidence is not a missing row or zero value.
- scientific rationale: This preserves PRE admissibility and prevents retrospective information repair.
- affected files: `exp/exp1/history.py`; history contract tests
- affected hashes: `PENDING_IMPLEMENTATION`
- reversible_before_paper_full: `YES`

## D0C_H_W_SELECTION_ORDER

- decision_id: `D0C_H_W_SELECTION_ORDER`
- date/time: `2026-08-16T20:43:59+08:00`
- status: `APPROVED`
- question: Select H and W jointly or sequentially.
- options: `SEQUENTIAL_H_THEN_W`; full H-by-W search was rejected.
- Codex recommendation: `SUPERSEDED`
- user decision: Select `H_STAR` on full ADAPTIVE current-episode histories first; after approval, hold H fixed and select `W_STAR`.
- scientific rationale: This prevents capacity and history horizon from being jointly optimized and keeps Exp1 information variants comparable.
- affected files: Development-only H and W runners
- affected hashes: `PENDING_IMPLEMENTATION`
- reversible_before_paper_full: `YES`

## D0D_W_SEED_BUDGET

- decision_id: `D0D_W_SEED_BUDGET`
- date/time: `2026-08-16T20:43:59+08:00`
- status: `APPROVED`
- question: Define the principal H and secondary W seed budgets.
- options: `FIVE_H_THREE_W`; the earlier five-seed W recommendation was rejected.
- Codex recommendation: `SUPERSEDED`
- user decision: H uses five deterministic training seeds; W uses three deterministic training seeds after `H_STAR` approval. Seeds are repeated training effects, not independent empirical observations.
- scientific rationale: H is the principal architecture selection and W is the secondary history-profile selection.
- affected files: Development-only H and W runners and evidence artifacts
- affected hashes: `PENDING_IMPLEMENTATION`
- reversible_before_paper_full: `YES`

## D0E_CURRENT_HISTORY_BOUNDARY

- decision_id: `D0E_CURRENT_HISTORY_BOUNDARY`
- date/time: `2026-08-16T20:43:59+08:00`
- status: `APPROVED`
- question: Define CURRENT.
- options: `CURRENT_NODE_ONLY`; alternate model families and FAST-path substitution were rejected.
- Codex recommendation: `CURRENT_NODE_ONLY`
- user decision: Evaluate the same `H_STAR` causal GRU with a one-node sequence containing only current decision node `t`, while preserving feature, head, target, calibration, and PRE semantics.
- scientific rationale: CURRENT is an information representation baseline, not a different prediction model.
- affected files: `exp/exp1/history.py`; history contract tests
- affected hashes: `PENDING_IMPLEMENTATION`
- reversible_before_paper_full: `YES`

## D0F_ADAPTIVE_HISTORY_BOUNDARY

- decision_id: `D0F_ADAPTIVE_HISTORY_BOUNDARY`
- date/time: `2026-08-16T20:43:59+08:00`
- status: `APPROVED`
- question: Define the ADAPTIVE full-history boundary.
- options: `CURRENT_EPISODE_FULL_PREFIX`; cross-episode or future history was rejected.
- Codex recommendation: `CURRENT_EPISODE_FULL_PREFIX`
- user decision: Use every admissible canonical decision node from the earliest legal node of the current predecessor-successor episode through current node `t`.
- scientific rationale: Full history is episode-bounded causal history, not unbounded aircraft history.
- affected files: `exp/exp1/history.py`; history contract tests
- affected hashes: `PENDING_IMPLEMENTATION`
- reversible_before_paper_full: `YES`

## D2_H_STAR

- decision_id: `D2_H_STAR`
- date/time: `2026-08-17T10:23:30+08:00`
- status: `APPROVED`
- question: Select `H_STAR` from 16 and 32 after five-seed ADAPTIVE Development evidence is available.
- options: `H_16`; `H_32`; `DEFER`
- Codex recommendation: `H_32`
- user decision: `H_STAR = 32`
- scientific rationale: Five-seed Development episode-balanced joint NLL was `4.036163 +/- 0.156007` for H=32 versus `4.240034 +/- 0.184308` for H=16. The relative difference was `5.0511%`, outside the pre-specified `0.5%` practical-equivalence region, so the simplicity tie-break for H=16 did not apply. No downstream M2-M4 metric or Final Test data participated.
- affected files: `configs/scientific/foundation.yaml`; `artifacts/diagnostics/v5_development_freeze/m1_hstar_evidence.json`; Development-only W-selection runner
- affected hashes: H evidence `sha256:a56a7254e5e08c959d8e9d8be58456469b2f37a293f33495dfaf58cdf452b3a5`; M1 base cache `sha256:9c647c03a4bb59d8cc6568e14a34f431f5da84b6d179e55d2e416fe7e7ed180a`
- reversible_before_paper_full: `YES`

## D1_W_STAR

- decision_id: `D1_W_STAR`
- date/time: `2026-08-17T10:56:05+08:00`
- status: `APPROVED`
- question: Select `W_STAR` from 30, 60, 120, and 180 minutes after three-seed H=32 FIXED_HISTORY Development evidence is available.
- options: `W_30`; `W_60`; `W_120`; `W_180`; `DEFER`
- Codex recommendation: `W_30`
- user decision: `W_STAR = 30 minutes`
- scientific rationale: W=30 had the lowest mean Development episode-balanced joint NLL (`3.907730`) and was the shortest candidate in the pre-specified 0.5 percent practical-equivalence region. Relative differences from W=30 were 0.0891 percent for W=60, 0.2703 percent for W=120, and 0.4326 percent for W=180. No downstream metric or Final Test data participated.
- affected files: `configs/scientific/foundation.yaml`; `artifacts/diagnostics/v5_development_freeze/m1_wstar_evidence.json`; future Development-only warning-threshold runner
- affected hashes: W evidence `sha256:35fed8273d737762a8c48321a1ce8bbd0aee76ff7c27537a57266430d3038fa1`; M1 base cache `sha256:9c647c03a4bb59d8cc6568e14a34f431f5da84b6d179e55d2e416fe7e7ed180a`
- reversible_before_paper_full: `YES`

## D3_SIGNED_M1_H_W_REFREEZE

- decision_id: `D3_SIGNED_M1_H_W_REFREEZE`
- date/time: `2026-08-17T18:05:04+08:00`
- status: `APPROVED`
- question: Permanently freeze the signed M1 target chain and its Development-selected H/W values, then freeze the warning-model artifact without rerunning model selection.
- options: signed chain `R_IB -> DELTA_OB -> T_TX` with `H=32`, `W=30`; defer; reject
- Codex recommendation: approve the signed chain and H/W evidence; use the first pre-registered W seed as the artifact rule so Development seed performance is not used post hoc
- user decision: `R_IB -> DELTA_OB -> T_TX`, `SIGNED H_STAR = 32`, `SIGNED W_STAR = 30`; authorize permanent freeze synchronization, provenance reconciliation, D3 warning-probability implementation, and final warning-model-artifact freeze
- scientific rationale: Signed five-seed H evidence placed H=32 outside the 0.5 percent equivalence region versus H=16. Signed three-seed W evidence placed W=30 in the practical-equivalence set and selected the shortest equivalent window. `D_TO` is derived as `max(0, DELTA_OB + T_TX - train-frozen taxi reference)`; `R_OB` is derived only. No Final Test, downstream experiment metric, or warning operating point selected H/W.
- artifact rule: `FIRST_PRE_REGISTERED_W_SEED`; seed `20260813`; source `runs_signed_wstar/W30_H32_seed20260813.pt`; no Development score was used to choose the seed
- affected files: `configs/scientific/foundation.yaml`; signed H/W evidence; `model/M1/warning.py`; `M1_SIGNED_WARNING_MODEL_V1.pt`; warning-model manifest; reconciliation documents
- affected hashes: H evidence `sha256:ba8b6dd01ea0bcd00c9d94103bb2d7db7756178c01862fb6475a8f5ea1862057`; W evidence `sha256:a3da36adae926b206a7073edf88b7dcbf49b8ee01949820543c2aaf3473247ff`; warning checkpoint `sha256:a522985e07564c34d947b8ca891b1b3bf810ac0044e0b578710cd693957215db`
- execution boundary: H/W rerun `FALSE`; full Development warning inference `NOT_RUN`; Final Test access `0`; `paper_full` `FALSE`
- reversible_before_paper_full: `YES`

## EXP1_DEVELOPMENT_FREEZE

- decision_id: `EXP1_DEVELOPMENT_FREEZE`
- date/time: `2026-08-18`
- status: `APPROVED`
- question: Approve the Development warning freeze and permanently retain the empirical boundary result.
- user decision: `AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE` is `PASS`; do not rerun or retune Exp1 to reverse the result.
- freeze_hash: `sha256:a3ef4bd20048658783f36c2234df986409a7adaefbd3cca0bce722beb6ea1c46`
- scientific interpretation: ADAPTIVE_HISTORY does NOT outperform FIXED_HISTORY; extending admissible history from the frozen 30-minute window to the full current episode does not improve the frozen warning operating point.
- classification: `EMPIRICAL_BOUNDARY_NOT_FAILED_RUN`
- execution boundary: Final Test access `0`; `paper_full` `FALSE`
- reversible_before_paper_full: `YES`

## M2_FORMAL_FREEZE

- decision_id: `M2_FORMAL_FREEZE` (`AIR_SLOT_POST_EXP1_DEVELOPMENT_FREEZE_RESOLUTION` DECISION 1)
- date/time: `2026-08-18`
- status: `APPROVED`
- user decision: Data2 formal M2 consequence scope is exactly `K_FORMAL_DATA2 = {F_continuity, F_execution, F_propagation, P_time, R_operating}`; `P_itinerary`/`P_service` stay `OUTSIDE_PRINCIPAL_FORMAL_SCOPE` and must not enter the principal aggregate; the component set is fixed episode-by-episode.
- native quantities: `Z_turn = max(0, R_IB - turnaround_reference)`; `Z_exec = max(0, DELTA_OB)`; `Z_takeoff = max(0, DELTA_OB + T_TX - taxi_reference)`; `Z_taxi = max(0, T_TX - taxi_reference)`; `q_F_continuity = Z_turn`; `q_F_execution = Z_exec`; `q_F_propagation = Z_takeoff * E_down`; `q_P_time = V_OD_pax * Z_takeoff`; `q_R_operating = Z_taxi`.
- valuation: `s_k_CU = positive Train-period median` per frozen component; `U_pre_CU = q / s_k_CU`; `w_k = 1` for every formal component; total `= sum over the five components ONLY IF every required component is supported`; otherwise `UNAVAILABLE / ABSTAIN` (no drop, no renormalization, no zero-fill, no proxy).
- passenger reference: existing train-frozen `DATA2_PASSENGER_REFERENCE_H1@1.0.0` (Q1+Q2 DB1B coupon, x10); supports `P_time` as frozen passenger exposure proxy; no global route fallback; if the OD reference is unavailable, `P_time` is unsupported and the five-component total is unavailable.
- registry: `M2_DATA2_FORMAL_CU_V1` immutable registry with schema, formal scope, native quantity definitions, train-scale artifact paths/hashes, reference IDs/hashes (turnaround/taxi/downstream exposure/passenger), component weights, aggregation rule, support rule, `final_test_access_count = 0`.
- affected files: `model/M2/freeze.py`; `model/M2/freeze_cli.py`; `model/M2/drivers.py`; `model/M2/context.py`; `registries/m2_data2_formal_cu_v1.json`; `artifacts/diagnostics/v5_development_freeze/M2_DATA2_FORMAL_CU_V1_MANIFEST.json`; focused M2 tests
- affected hashes: registry hash and manifest hash recorded in `artifacts/diagnostics/v5_development_freeze/M2_FORMAL_FREEZE_CLOSURE.json`
- execution boundary: no normative value selected from Development performance; Final Test access `0`; `paper_full` `FALSE`
- reversible_before_paper_full: `YES`

## M3_RESPONSE_PARAMETER_FREEZE

- decision_id: `M3_RESPONSE_PARAMETER_FREEZE` (`AIR_SLOT_POST_EXP1_DEVELOPMENT_FREEZE_RESOLUTION` DECISION 2; user-approved `M3_RESPONSE_SCENARIO_V1` scenario-only numerical response freeze)
- date/time: `2026-08-18`
- status: `APPROVED`
- user decision: freeze the 23-template active structural action registry as the authoritative M3 action catalog (A12 absent; no legacy 13/21/26-action matrix import); freeze `M3_RESPONSE_SCENARIO_V1` as a scenario-only numerical response contract with `BERNOULLI_BETA` (`beta_concentration = 12.0`, `induced_score_to_cu = 0.10`), tiers T1-T6, LOW/BASE/HIGH deltas `pm 0.15 / pm 0.10`, LOW/HIGH clipping `p in [0.05, 0.95]`, `mean in [0.20, 0.95]`, secondary burden `[0.075, 0.10, 0.125]`.
- core rule: FROZEN numerical response `!=` FORMAL empirical support; scenario-defined response `!=` empirical action response; numerically evaluable action `!=` FORMAL action; freezing scenario parameters never upgrades evidence class (`formal_support_upgrade = false`).
- provenance hierarchy preserved: `EMPIRICAL_ACTION_LOG > OPERATOR_INDUSTRY > STRUCTURAL_BOUNDED_SCENARIO > PURE_SCENARIO`, with `UNSUPPORTED` retained separately; all 22 non-A00 actions are `FROZEN`/`PURE_SCENARIO`; `A00` is `NOT_REQUIRED`/`DETERMINISTIC`.
- registry: `registries/m3_response_scenarios.yaml` (23 IDs), manifest `M3_RESPONSE_SCENARIO_V1_MANIFEST.json`
- affected hashes: response registry `sha256:ff8adb3034603ec225930ed9187bc296b46d58637a974c9de64b341248755ce0`; structural registry `ACTION_TEMPLATES_V1` unchanged (response parameters stay `NOT_FROZEN` there by design)
- execution boundary: no response utility weight selected from Development performance; Final Test access `0`; `paper_full` `FALSE`
- reversible_before_paper_full: `YES`
## AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION

- decision_id: `AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION`
- date/time: `2026-08-18`
- status: `APPROVED`
- question: Execute Exp234 Development work on a derived downstream scenario artifact (frozen M1 Development scenarios) and run the Exp3.7 LLM audit on that artifact.
- user decision: Derive `M1_SIGNED_DEVELOPMENT_SCENARIOS_V1` (1824 nodes, 250 scenarios/node, 128 episodes; `sha256:ca3370a3...1dfec`) as a frozen-input Development artifact; run Exp2/Exp3/Exp4 Development execution and the LLM audit against it; classification `DERIVED_DOWNSTREAM_ARTIFACT_GENERATION / DEVELOPMENT_EXECUTION`.
- boundaries: no PRE rebuild, no M1 retrain, no H/W rerun, no Final Test access; `PAPER_FULL_RUN=FALSE`; LLM outputs do not feed back into PRE/M1/M2/M3/M4.
- affected hashes: scenario artifact `sha256:ca3370a3...1dfec`
- reversible_before_paper_full: `YES`

## AIR_SLOT_LLM_AUDIT_V2_STATE_CONDITIONED_EXPLANATION

- decision_id: `AIR_SLOT_LLM_AUDIT_V2_STATE_CONDITIONED_EXPLANATION`
- date/time: `2026-08-18`
- status: `APPROVED`
- question: Replace the superseded V1 blinded-choice LLM audit construct with a state-conditioned operational reasonableness explanation protocol for Exp3.7.
- user decision: V2 protocol with cost-first model rule (`deepseek-v4-flash`, escalate only if pilot gates fail), strict response schema, frozen prompt/schema/contract hashes, and pilot gates (schema >= 0.98, parse <= 0.02, unsupported-fact-assertion = 0, known-false-prerequisite-ignored <= 0.05, unknown-prerequisite-asserted-true = 0); auxiliary/evaluation-only; `LLM_TO_MODEL_FEEDBACK=FALSE`.
- execution: pilot PASS on 50 cases; principal 128 episodes x 3 = 382 judgements; report `DEEPSEEK_LLM_AUDIT_REPORT_V2.json` (`status=COMPLETED`).
- boundaries: Final Test access 0; `PAPER_FULL_RUN=FALSE`; V1 evidence preserved as `DIAGNOSTIC_FAIL_UNDER_SUPERSEDED_AUDIT_CONSTRUCT`.
- reversible_before_paper_full: `YES`

## AIR_SLOT_TEMPORARY_REPORT_EXECUTION

- decision_id: `AIR_SLOT_TEMPORARY_REPORT_EXECUTION`
- date/time: `2026-08-18`
- status: `APPROVED`
- question: Produce an interim (temporary) Development report and publish small tracked Exp2/Exp3 Development result summaries before the final Exp1/Exp3/M4 closure.
- user decision: `TEMPORARY_DEVELOPMENT_REPORT=TRUE`; `TEMPORARY_REPORT_PURPOSE=INTERIM_PRESENTATION_ONLY`; `PAPER_RESULT=FALSE`; `FINAL_RESULT=FALSE`; reuse verified frozen artifacts (`M1_PURE_INFERENCE_REUSED=TRUE`); no Exp1 recomputation, no Exp2 rerun, no PRE/M1 rerun; sync only small summaries/status/docs to GitHub; keep large artifacts ignored.
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; `PAPER_FULL_RUN=FALSE`; `EXPENSIVE_UPSTREAM_RERUN_COUNT=0`; M4 material coverage remains unfrozen.
- reversible_before_paper_full: `YES`

## AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_20260825

- decision_id: `AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_20260825`
- date/time: `2026-08-25`
- status: `APPROVED`
- question: How should Exp1 Development evidence closure proceed now that the paper-facing
  display logic is fixed but bottom-level results are not yet saved at paper-statistic granularity?
- user decision: (1) Exp1A: stop all M2 interface changes; run the state-driven-vs-
  context-conditioned-consequence ranking analysis on frozen outputs only (q_state vs q_ctx on
  common supported S_i; main threshold >= 0.90, sensitivity >= 0.50; typed exclusions).
  (2) Exp1B: train the H32 CURRENT-only Development comparator now with the exact H32 History
  budget and calibration path (G1 answered: run now). (3) Final Test remains forbidden:
  `FINAL_TEST_ACCESS_COUNT = 0`, `PAPER_FULL_RUN = FALSE`.
- execution: implemented in `exp/exp1/closure.py`, `exp/exp1/current_only_training.py`,
  `exp/exp1/current_only_scenarios.py`; outputs under
  `artifacts/experiment/exp1_full_development/exp1_closure_20260825/` with `DEVELOPMENT_ONLY`
  filenames; comparator `M1_V2_GRU_H32_CURRENT_ONLY` checkpoint
  `sha256:cea56794...`, `budget_identical_to_reference = true`,
  `calibration_path_identical_to_reference = true`; 13/13 tests passed
  (`tests/experiments/exp1`, incl. 10 new CONTRACT_FAST closure tests).
- boundaries: `EXP1A_M2_INTERFACE_CHANGES = NONE`; no Final Test access; no paper_full; no
  calibration data read; baseline closure doc untouched; no commit/push.
- reversible_before_paper_full: `YES`


## AIR_SLOT_EXP23_G2_FREEZE_20260825

- decision_id: `AIR_SLOT_EXP23_G2_FREEZE_20260825`
- date/time: `2026-08-25`
- status: `APPROVED`
- question: Freeze the Exp2/Exp3 G2 paper-facing contracts (Exp2A point rule,
  Exp3 state-vintage rule, M3 declared scenario-response, M4 constructed-EUR
  reporting, positive-tail policy) before Development figures and the
  paper-output audit.
- user decision: F1-F6 as listed in
  `codex_framework/AIR_SLOT_EXP23_G2_FREEZE_DECISIONS_20260825.md`, based on
  the manuscript lines `Rolling_Airline_Recovery_v2/sections/05_experiment.tex`
  L121-159, L206-237; `sections/03_methodology.tex` L400-444;
  `sections/04_implement.tex` L275-345, L388-396.  Numbers are fixed and must
  not be changed.
- execution: F1 implemented in `exp/exp2/representation.py` (primitive
  coordinates `(R_IB, D_OB, D_TX)`; D_TO identity-only) and re-materialized
  to `artifacts/experiment/exp2/exp2_representation_refactor_20260825/`
  (DEVELOPMENT_ONLY; old real-fast records retained and marked SUPERSEDED);
  F2 recorded: "partial-q 未采用（原稿未定义）"; F3 guard added in
  `exp/exp3/runner.py` and `exp/exp3/formal_preparation.py`
  (`EXP3B_VINTAGE_NOT_AVAILABLE`, fallback forbidden); F4-F6 recorded in
  protocol docs and the freeze-decisions document.
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; `PAPER_FULL_RUN=FALSE`; no git
  commit/push; no artifact deletion/move; no change to `model/**`,
  `registries/**`, `configs/**`, `exp/exp1/**`, `exp/common/**`, or the
  baseline audit document.  Residual gates: G2-RMB-beta 数值锚;
  G3-PAPER_OUTPUT_SPEC_V1.json 草稿.
- reversible_before_paper_full: `YES`


## AIR_SLOT_EXP3_EXACT_VINTAGE_P2_20260825

- decision_id: `AIR_SLOT_EXP3_EXACT_VINTAGE_P2_20260825`
- date/time: `2026-08-25`
- status: `APPROVED`
- question: Refine freeze F3 to exact-vintage matching for Exp3B lagged state.
- user decision: P2 small fix — LAG_5 / LAG_10 bind only the decision node
  whose `decision_time` is exactly `t - delta`; nodes without an exact vintage
  are typed-excluded `EXP3B_VINTAGE_NOT_AVAILABLE`; no nearest-past selection,
  no fallback.
- execution: `exp/exp3/vintage.py::exact_vintage_bindings`; `exp/exp3/runner.py`
  switches lagged variants to it; `exp/exp3/formal_preparation.py` contract
  adds `vintage_match_rule=EXACT_DECISION_TIME_T_MINUS_DELTA`; tests
  `tests/experiments/exp3/test_vintage_exclusion.py` (4 tests).
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; `PAPER_FULL_RUN=FALSE`; no git; no
  change to `exp/common/**` (bindings live in `exp/exp3/**`).
- reversible_before_paper_full: `YES`

## AIR_SLOT_EXP_DEVELOPMENT_FIGURES_20260825

- decision_id: `AIR_SLOT_EXP_DEVELOPMENT_FIGURES_20260825`
- date/time: `2026-08-25`
- status: `APPROVED`
- question: Run the Exp development-figures phase in baseline order: Exp2A Point
  variogram closure, Exp3 valuation-only records, Exp4 per-node records,
  Development figures (6A Point / remove 6B-C / 7B valuation-only / 8A-C),
  paper-output audit rerun, then stop at the G3 draft boundary.
- user decision: (1) Exp2A Point variogram runs directly with the F1 medoid
  rule `(R_IB, D_OB, D_TX)`; `D_TO` is identity-checked only. (2) Exp3
  sensitivity is valuation-only: LOW/BASE/HIGH move the frozen five-anchor
  monetary coefficients only (EUR 0.5x/1.0x/2.0x); response parameters stay at
  the F4-frozen declared values.  Response-only perturbation is NOT
  implemented (`EXP3_RESPONSE_ONLY = NOT_AUTHORIZED_PER_F4`); the baseline
  document's section-2 item-4 scope correction is recorded here and the
  baseline audit document is not modified. (3) Exp4 per-node records use the
  Exp1 lead-time/CRPS conventions; 95% CI is episode-cluster bootstrap (2000
  replicates, seed 20260825). (4) Figure 6B-C are removed per F2
  (`PARTIAL_Q_SERIES_NOT_IMPLEMENTED`; q-series frozen). (5) Stop at the G3
  draft boundary: no `PAPER_OUTPUT_SPEC_V1.json` is created; a ready-output
  list with manuscript field/line mapping is handed to the user.
- execution: `exp/exp2/closure.py` (Exp2A records + summaries),
  `exp/exp3/valuation_only.py` (records + manifest + summary),
  `exp/exp4/per_node_records.py` (records + lead-time grid + manifest),
  `exp/reporting/section5_secondary_analysis.py` (figures 6A/7A/7B/8, table 1,
  audit); outputs under the three new artifact roots and
  `outputs/manuscript_values/section5_secondary_analysis/`, all
  `DEVELOPMENT_ONLY` with `paper_result=false`.
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; `PAPER_FULL_RUN=FALSE`; no git
  commit/push; no change to `model/**`, `registries/**`, `configs/**`,
  `exp/exp1/**`, `exp/common/**`, existing artifacts, or the baseline audit
  document.  Residual gates: G2-RMB-beta 数值锚; G3-草稿.
- reversible_before_paper_full: `YES`


## AIR_SLOT_EXP_DEVELOPMENT_FIGURES_SUPPLEMENT_20260826

- decision_id: `AIR_SLOT_EXP_DEVELOPMENT_FIGURES_SUPPLEMENT_20260826`
- date/time: `2026-08-26`
- status: `APPROVED`
- question: Adjust acceptance criteria for the Exp development-figures phase;
  data-layer strict checks unchanged, figure-layer acceptance relaxed.
- user decision: (1) Data layer stays strict: record row counts, schema,
  input hashes, manifest safety all zero, Exp2A F1 point-variogram parity with
  the 1,769 POINT records, Exp3 valuation-only LOW/BASE/HIGH monetary-only
  (response frozen declared, ASSUMPTION_GROUNDED), Exp4 per-node records with
  the full 10-bin lead-time grid, explicit lead_time_source, NA without
  interpolation, D_TX bins NA, episode-cluster bootstrap (2,000 reps, seed
  20260825), DEVELOPMENT_ONLY/paper_result=false/FINAL_TEST_ACCESS_COUNT=0, no
  git, no Final Test, no paper_full. (2) Figure layer: scripts must run to
  completion, files must land at expected paths, and figure-data bindings must
  be correct; no visual/publishing-style QA is performed; a figure that fails
  to generate is reported per-figure with reason. (3) Style/visual alignment
  with PAPER_OUTPUT_SPEC_V1.json is deferred until after G3.
- execution: reran `exp/exp2/closure.py`, `exp/exp3/valuation_only.py`,
  `exp/exp4/per_node_records.py`, and
  `exp/reporting/section5_secondary_analysis.py`; results identical to the
  2026-08-25 materialization (Exp3 artifact hash unchanged). Exp4 grid was
  made explicit: `_grid_summary` now emits NA rows (estimate/CI empty,
  n_episodes=0, n_nodes=0) for manuscript bins without node support
  (`na_grid_policy=EXPLICIT_NA_ROW_FOR_UNSUPPORTED_BINS_NO_INTERPOLATION`);
  D_OB bin 480 and T_IB_A00 bins 180-480 are empty in the cohort and are
  reported as NA, never interpolated; D_TX keeps OVERALL rows only. Data-layer
  audit: 37/37 PASS. Figures regenerated: 4 figures x pdf/png/svg.
  G3 draft input written to
  `outputs/manuscript_values/section5_secondary_analysis/G3_DRAFT_INPUT_20260826.md`
  (no PAPER_OUTPUT_SPEC_V1.json created).
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; `PAPER_FULL_RUN=FALSE`; no git; no
  change to `model/**`, `registries/**`, `configs/**`, `exp/exp1/**`,
  `exp/common/**`, existing artifacts, or the baseline audit document.
  Residual gates: G2-RMB-beta 数值锚; G3-草稿.
- reversible_before_paper_full: `YES`


## AIR_SLOT_G2_MONETARY_LITERATURE_AND_G3_SPEC_DRAFT_20260826

- decision_id: `AIR_SLOT_G2_MONETARY_LITERATURE_AND_G3_SPEC_DRAFT_20260826`
- date/time: `2026-08-26`
- status: `APPROVED` (2026-08-26 freeze instruction `AIR_SLOT_G2_MONETARY_AND_G3_SPEC_FREEZE_20260826`; D1-D3 approved, T1-T2 executed)
- question: Draft the paper-facing spec from the manuscript and close the
  remaining G2 monetary anchors with retrieved literature plus explicitly
  declared assumptions where needed.
- proposal: (1) `P_itinerary`/`P_service`: keep ABSTAIN
  (`OPTION_A_KEEP_ABSTAIN`). Cook & Tanner 2015 v4.1 (official PDF
  downloaded, page-verified) §3.6.4 states EU261 covers departure delay only
  ("nothing is due to the passenger for any type of arrival delay or missed
  connection per se"); §3.6.7/§3.6.9 document hard/care costs only
  qualitatively (Jovanovic [18] meal vouchers/hotel/FFP miles/phonecards);
  Tables 17-18 are per-passenger-minute rates conditioned on delay duration,
  not per-event rates; no per-event EUR anchor exists in the retrieved
  literature. Ball et al. 2010 could not be retrieved (ROSAP 403; no local
  copy) and is not used to anchor values. (2) RMB `beta_k^m`: close by
  system-level ABSTAIN (`m=RMB` uninstantiated; no `beta_k^RMB`); the
  manuscript makes RMB conditional on availability and F5 forbids fabricated
  values. (3) G3: spec draft written to
  `codex_framework/PAPER_OUTPUT_SPEC_V1_DRAFT_20260826.json` (DRAFT, not
  frozen) from `G3_DRAFT_INPUT_20260826.md` plus the three materialized
  manifests (Exp2A source hash sha256:2ce9650a…; Exp3 artifact hash
  sha256:631d01a4…; Exp4 artifact hash sha256:162fbdb0…).
- execution: created
  `codex_framework/AIR_SLOT_G2_MONETARY_LITERATURE_PROPOSAL_20260826.md` and
  `codex_framework/PAPER_OUTPUT_SPEC_V1_DRAFT_20260826.json`; literature
  copies at `D:\Cache\Python\Temp\cook_tanner_2015_v4_1.pdf` /
  `cook_tanner_2015_text.txt`. No registry/model/config edits; no
  `PAPER_OUTPUT_SPEC_V1.json` created.
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; `PAPER_FULL_RUN=FALSE`; no git; no
  change to `model/**`, `registries/**`, `configs/**`, `exp/**`, existing
  artifacts, or the manuscript TeX. Residual gates after approval: freeze
  `PAPER_OUTPUT_SPEC_V1.json` (G3), then re-resolve the two
  `HUMAN_DECISION_REQUIRED` registry statuses in a new registry version.
- reversible_before_paper_full: `YES`

- approved_decisions:
  - D1: `P_itinerary`/`P_service` = `OPTION_A_KEEP_ABSTAIN`; event-count CUs
    (`N_miss`, `N_svc`) stay visible; monetary layer
    `monetary=NOT_ANCHORED`; no zero-fill, no inference.  Literature basis:
    Cook & Tanner 2015 v4.1 section 3.6.4 (EU261 covers departure delay
    only), sections 3.6.7/3.6.9 (hard/care costs qualitative only), Tables
    17-18 (per-passenger-minute rates, not per-event).
  - D2: RMB = system-level ABSTAIN; `m=RMB` not instantiated; no
    `beta_k^RMB` values; constructed-EUR five-component system is the single
    reporting system.
  - D3: `PAPER_OUTPUT_SPEC_V1_DRAFT_20260826.json` approved in full and
    frozen as `codex_framework/PAPER_OUTPUT_SPEC_V1.json`
    (`status=FROZEN_APPROVED_20260826`, `spec_id=PAPER_OUTPUT_SPEC_V1`,
    `approval_decision_id=AIR_SLOT_G2_MONETARY_AND_G3_SPEC_FREEZE_20260826`).
- approval_products:
  - `codex_framework/PAPER_OUTPUT_SPEC_V1.json` (new, FROZEN).
  - `registries/m4_eur_mapping_assumption_grounded_v2.json` (new; inherits
    v1 fields; P_itin/P_serv `anchor_status=ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY`
    with null money; `rmb_reporting_system=NOT_INSTANTIATED_NO_BETA_K_RMB`;
    `changed_since_v1` records; registry_hash
    `sha256:befc10aab3a9b9ca5292ac82331e728f7d28b1546077725ab7cdf5564fcbc072`).
  - Draft marked `SUPERSEDED_BY_FROZEN_V1` -> `codex_framework/PAPER_OUTPUT_SPEC_V1.json`.
  - v1 registry file sha256 unchanged: `4B18B02223C9989F8C203AA1638DDF6728736E64AA2BB1199DF3A08AE515D67E`;
    frozen Exp2/Exp3/Exp4 artifacts rewritten: 0.
- gates_closed: G2-RMB-beta 数值锚 (system-level ABSTAIN); G3
  (`PAPER_OUTPUT_SPEC_V1.json` frozen).  Remaining: Section 4<->5 text
  corrections handled separately.



## AIR_SLOT_HUMAN_GATES_ALL_APPROVED_20260826

- decision_id: `AIR_SLOT_HUMAN_GATES_ALL_APPROVED_20260826`
- date/time: `2026-08-26`
- status: `APPROVED` (all items; interactive round 1+2)
- question: Close every remaining human gate before manuscript filling and
  Final Test; decisions documented in
  `codex_framework/AIR_SLOT_HUMAN_GATE_DECISION_MEMO_20260826.md`.
- user decision: D1=A (Exp2B matched-case same-decile-band total-J pairing +
  top-3 channel-share flip, declared in protocol); D2=A (consistent with
  frozen DATA2_FACTUAL_REPLAY_POLICY_A1: retrospective event-time replay,
  observed/production availability claims false); D3=A (Table 1
  STATE_AWARE_H32 D_OB/D_TX CRPS stay blank + caption caveat); D4=A (all
  eight Section 4/5 text fixes, TeX text-only); D5=A (Exp1 spec addendum
  template pre-approved, freeze after T1 hash verification); D6=A (Final Test
  = no retraining, reuse frozen checkpoints, rerun materialization+figures+
  Table 1 under frozen spec with paper_result=true into
  artifacts/paper_results_v1/ and
  outputs/manuscript_values/section5_secondary_analysis/paper/, seeds
  unchanged; approval does not auto-start Final Test); D7=B with D7a-D7d=A
  (fit shared calibration artifact on calibration split only, two contracted
  pieces, quantile stays NOT_APPLIED, contract V1 untouched, dev records
  untouched, Final Test applies artifact); C1-C3=OK.
- execution: none yet. The approval is recorded; the executable T-cal/T1-T5
  instruction is issued to the VS session separately. foundation.yaml stays
  untouched; its stale calibration note is superseded by the future artifact
  manifest and this log entry.
- boundaries: `FINAL_TEST_ACCESS_COUNT=0` until the explicit Final Test
  instruction; `PAPER_FULL_RUN=FALSE`; no git; no `model/**`; no
  `configs/**`; frozen artifacts untouched.
- reversible_before_paper_full: `YES`

## AIR_SLOT_HUMAN_POINTS_FINAL_20260826

- decision_id: `AIR_SLOT_HUMAN_POINTS_FINAL_20260826`
- date/time: `2026-08-26`
- status: `APPROVED`
- question: Remaining human points after the autonomous overnight chain.
- user decision: HP1=A (V3 dispatch = automatic Final Test authorization;
  no intermediate confirmation); HP2=A (morning: user scans
  PAPER_FILL_READY then sends one "填" message; VS fills TeX numbers/tables/
  figures then); HP3=B with mandatory recording (AUTO_ASSUMED_FIX accepted by
  default; all fixes/quarantines/citations recorded in the failure list and
  decision log; frozen-contract changes surface at the top of the morning
  report for optional scan).
- boundaries: unchanged — no retraining, no model/** edits, no frozen
  artifact rewrites, no configs/** edits, TeX text fixes only the eight items
  plus the authorized fill step, no Git, ABSTAIN over fabrication.
- reversible_before_paper_full: `YES`


## AIR_SLOT_OVERNIGHT_CHAIN_HP_DECISIONS_20260826

- decision_id: `AIR_SLOT_OVERNIGHT_CHAIN_HP_DECISIONS_20260826`
- date/time: `2026-08-26`
- status: `APPROVED`
- question: Remaining human points for the autonomous overnight chain
  (`codex_framework/AIR_SLOT_AUTONOMOUS_OVERNIGHT_CHAIN_20260826.md`).
- user decision: HP1=A (Final Test auto-run authorized; dispatching the
  chain file IS the authorization; no further confirmation); HP2=A (chain
  stops at the morning report; TeX number-filling requires the user's
  explicit "填" instruction; the morning report must include a ready-to-apply
  TeX fill diff preview that is NOT applied); HP3=B with mandatory recording
  (all AUTO_ASSUMED_FIX accepted by default but fully recorded: failure
  entry + page-level citation + label + decision-log entry + morning-report
  line; ABSTAIN preferred where no source exists).
- execution: decisions appended as Section 8 of the chain file; no code
  changes; no Final Test access from this session.
- boundaries: `FINAL_TEST_ACCESS_COUNT` changes only inside the authorized
  chain execution; `PAPER_FULL_RUN=FALSE`; no git; no `model/**` edits; no
  retraining.
- reversible_before_paper_full: `YES`

## T_CAL_CALIBRATION_ARTIFACT_20260826

- decision_id: `T_CAL_CALIBRATION_ARTIFACT_20260826`
- date/time: `2026-08-26`
- status: `EXECUTED` (D7=B, D7a-D7d=A approved; V3 overnight chain)
- question: Fit the two contracted M1 V2 calibration pieces as a single shared artifact before Final Test.
- user decision: D7a=A (fit only DISCRETE_HAZARD_EVENT_TIME_NLL + HURDLE_ZERO_BINARY_CE_TEMPERATURE; positive quantile stays QUANTILE_CALIBRATION_NOT_APPLIED; contract V1 unmodified); D7b=A (one-shot fit on calibration split 2019-07-01..2019-07-31, 64 episodes; no selection loop; Train/Development/Final Test not read); D7c=A (one shared artifact applied identically to STATE_AWARE H32 and CURRENT-only comparator); D7d=A (dev records untouched; Final Test applies artifact and reruns materialization).
- execution: `exp/reporting/calibration_artifact.py`; artifact at `artifacts/calibration/m1_v2_calibration_20260826/M1_V2_CALIBRATION_ARTIFACT.json`; manifest at `.../M1_V2_CALIBRATION_MANIFEST.json`.
- results: STATE_AWARE H32 fitted hazard temperature 1.7435, D_OB zero 4.5146, D_TX zero 20.0 (clamp upper bound); CURRENT_ONLY fitted hazard 1.3574, D_OB zero 20.0, D_TX zero 20.0; both models 64 episodes / 1060 nodes; before/after metrics recorded as provenance only; checkpoint hashes unchanged (e3401c76..., cea56794...); positive-quantile coverage diagnostics recorded, status NOT_APPLIED.
- interpretation: "one shared artifact" = a single artifact file used by both models; each model applies its own fitted temperature set from that file under the identical procedure (calibration-path-identical claim preserved).
- affected files: `exp/reporting/calibration_artifact.py` (new); `tests/experiments/exp1/test_calibration_artifact_contract.py` (new, 6 passed); `artifacts/calibration/m1_v2_calibration_20260826/*` (new); `configs/scientific/foundation.yaml` untouched; its stale note is superseded by the artifact manifest + this entry.
- boundaries: `FINAL_TEST_ACCESS_COUNT=0`; no retraining; no `model/**` or `configs/**` edits; no git.

## T_TEX_SECTION45_TEXT_FIXES_20260826

- decision_id: `T_TEX_SECTION45_TEXT_FIXES_20260826`
- date/time: `2026-08-26`
- status: `EXECUTED` (D4=A approved; V3 overnight chain)
- question: Apply the eight Section 4/5 text fixes (TeX text-only; no numbers filled).
- user decision: D4=A (all eight fixes); only the eight items may change; other paragraphs, labels, citations, and `.bib` untouched.
- execution: 7 minimal patches applied; item 7 (grammar/dedup) verified already absent in the current manuscript snapshot (2026-08-23): `05_experiment.tex` L290 "across the two datasets" is grammatically correct (two datasets); no duplicated "the" found in any section TeX; no-op recorded.
- diffs: `docs/T_TEX_DIFFS_20260826.json` (file:line, old/new text):
  1. `05_experiment.tex` L109: same-checkpoint claim -> same architecture, identical training budget and calibration path, separate checkpoints.
  2. `05_experiment.tex` L131: R^IB kept as operating-state coordinate; scenario mapping = T_IB_A00 (data-side identifier), not a new measured variable.
  3. `05_experiment.tex` L111: principal delay event stated uniformly as D^+,TO>30.
  4. `05_experiment.tex` L263: historical reference baseline named HISTORICAL.
  5. `05_experiment.tex` L261: D_TX caveat (no planned wheels-off reference; lead-time bins NA; only overall rows; never interpolated).
  6a. `05_experiment.tex` L167 (Exp2A) and 6b. L197 (Exp2B): Top-1 comparisons only on common supported observations; unsupported components/actions typed-excluded, never zero-filled.
  7. Grammar/dedup: verified absent (no-op).
  8. `04_implement.tex` L403: calibration wording -> single shared artifact fitted on calibration split (discrete-hazard NLL + hurdle zero-mass temperature); positive-quantile not applied.
  plus `04_implement.tex` L171: same-checkpoint claim aligned with item 1.
- affected files: `Rolling_Airline_Recovery_v2/sections/05_experiment.tex`; `Rolling_Airline_Recovery_v2/sections/04_implement.tex`; `docs/T_TEX_DIFFS_20260826.json` (new).
- boundaries: no numbers filled; no other text changed; no git.

## T1_EXP1_SPEC_ADDENDUM_FREEZE_20260826

- decision_id: `T1_EXP1_SPEC_ADDENDUM_FREEZE_20260826`
- date/time: `2026-08-26`
- status: `FROZEN` (D5=A pre-approved; no second review after hash verification)
- question: Freeze the Exp1 figure/statistics addendum into the Final Test QA baseline.
- user decision: D5=A from `AIR_SLOT_HUMAN_GATE_DECISION_MEMO_20260826.md`: template pre-approved; freeze directly after T1 output hash verification.
- hash verification (all PASS):
  - `input_summary_hash_verified = sha256:f6a39b0f20cc47b6910fa8ce07a910cdadfc72c2cddd4437cc53a4a27d93e311` (EXP1_DEVELOPMENT_CLOSURE_SUMMARY_DEVELOPMENT_ONLY.json file hash, recomputed identical).
  - `closure_artifact_hash_verified = sha256:0134a6605ea0543428d6046bb1fbe32581ca546b6e8fd21d5981338fbbba5909` (summary `artifact_hash`, recomputed identical).
  - Row counts verified: Exp1A 3,538; sorting diagnostic 1,769; Exp1B 10,614.
  - Checkpoints verified: HISTORY `sha256:e3401c76...`, CURRENT_ONLY `sha256:cea56794...` (unchanged).
- products: `codex_framework/PAPER_OUTPUT_SPEC_V1_ADDENDUM_EXP1_20260826.json` (`status=FROZEN_APPROVED_20260826`); draft `..._DRAFT_20260826.json` retained with `supersedes_draft` pointer.
- boundaries: no spec content change; no git; `FINAL_TEST_ACCESS_COUNT=0`.

## FINAL_TEST_AUTO_RUN_20260826

- decision_id: `FINAL_TEST_AUTO_RUN_20260826`
- date/time: `2026-08-26`
- status: `EXECUTED` (HP1=A; `AIR_SLOT_AUTONOMOUS_OVERNIGHT_CHAIN_20260826.md` Section 8)
- question: Automatic Final Test per pre-approved D6 scope after the dev chain completed.
- execution: `exp/reporting/final_test_run.py` + `exp/reporting/final_test_scenarios.py`; shared T-cal artifact applied in memory to the frozen STATE_AWARE H32 and CURRENT-only checkpoints (checkpoint files unchanged; no retraining).
- stages (all `MATERIALIZED` in `artifacts/paper_results_v1/`): scenarios, exp1 (Exp1A 3,538 rows + sorting diagnostic 1,769 rows + Exp1B 10,614 rows), exp2 (full-development consequences), exp2a (Point/Marginal/Joint variogram, 124 paired episodes), exp2b (r=7/3/1, Top-1 difference rate 0.0 on 1,765 common-scope nodes; D1 matched-case 1,488 pair-direction rows), exp3 (action risk), exp3_valuation (122,061 rows, ASSUMPTION_GROUNDED), exp3_refresh_sync (1,769 nodes, exact-vintage), exp4 (21,228 per-node rows, 10-bin lead-time grid, D_TX NA policy), m3m4 (122,061 records, 1,765 ranked, top-1 A00 share 1.0 in all bands), figures (5A-C, 6A, 7A, 7B, 8 + Table 1) in `outputs/manuscript_values/section5_secondary_analysis/paper/`.
- tests: 106 passed (`pytest -q tests/experiments/exp1 tests/experiments/exp2 tests/experiments/exp3 tests/experiments/exp4 tests/experiments/test_section5_secondary_analysis.py tests/experiments/reporting/test_final_test_run.py tests/experiments/reporting/test_final_test_scenarios.py`).
- verification notes: Final Test split file never read; `FINAL_TEST_ACCESS_COUNT=0`; calibration drift of STATE_AWARE_H32 vs stored dev metrics is expected Final Test semantics (max abs diff 0.1029, documented in the Exp4 manifest parity block); tabular baselines parity PASS (max abs diff <= 7.1e-15).
- morning deliverable: `outputs/manuscript_values/PAPER_FILL_READY_20260827.md` (per-anchor values + unapplied TeX fill diff preview); `docs/AUTONOMOUS_FAILURE_LIST_20260826.md` (zero failures).
- boundaries: `FINAL_TEST_ACCESS_COUNT=0` (split not read), `PAPER_FULL_RUN=FALSE`, no git, no `model/**`/`configs/**` edits, frozen artifacts unrewritten.
