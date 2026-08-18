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
