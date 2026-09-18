# Phase 3 Report — M3 decision layer

Branch `v2/paper-primary`; instruction `docs/AirSlot_V2_Instruction_rev2_20260918.md`.
Phase 2 checkpoint: `672f969 v2(phase2): M1 representation ownership and M2 comparison support + CU V5`.

## 1. Completed scope

- Implemented the single M3 Stage-I selector (`model/M3/stage1.py`):
  `K = ceil(qN)` on the manuscript capacity grid `q in {0.05,0.10,0.20,0.30}`,
  nominal `q_0 = 0.10`, deterministic tie-break
  `(-score, episode_id, node_id)`, and one shared candidate queue for the delay
  comparator `P^D` and the consequence authority `P^C`. Signals attested
  `ABSTAIN_NO_COMMON_SUPPORT` are excluded from `N` and `K`, never zero-filled;
  an all-abstaining queue returns `ABSTAIN_NO_EVIDENCE`.
- Implemented the M3 Stage-II transition (`model/M3/transition.py`) exactly as
  the manuscript defines it: `AOBT^0 = SOBT + D_OB`,
  `LB^OB = max(SOBT, T_IB + T^{turn,lb})`, `H = [AOBT^0 - LB^OB]_+`,
  `r(u) = min(u,H)`, `D^OB(u) = max(D^OB - r(u), 0)`, with `T_IB` and `D_TX`
  unchanged and `D^TO(u) = D^OB(u) + D_TX`.
- Implemented the Train-derived Stage-II support (`model/M3/support.py`):
  `T^{turn,lb} = Q_0.20(T^turn | Train)` with Q10/Q30 sensitivities;
  `U_max = 5 floor(Q_0.90(H^{+,fact}_Train)/5)` with Q80/Q95 sensitivities;
  only strictly positive factual headroom enters the `U_max` quantile; the
  quantile rule is linear interpolation over sorted Train values.
- Implemented the Stage-II recovery problem (`model/M3/stage2.py`): action grid
  `{0,5,10,...,U_max}`, objective
  `J(u;lambda) = sum_s w_s Phi_C(C^CU_s(u)) + lambda u/U_max`,
  nominal `lambda_0 = 0.25` with grid `{0.10,0.25,0.50,1.00}`, exact complete
  enumeration as the formal path, ties resolved to the smaller intervention,
  and `V = J(0) - J(u*)`. TAXI/COMP return `U = {0}` with typed
  `NOT_ACTIONABLE`; `A00`/`u = 0` is reported as the baseline counterfactual and
  is never emitted as a recovery recommendation.
- Restored the mandatory M2 callback chain
  `u -> S(u) -> M2 -> C(u) -> J(u)` in
  `model/M2/consequence_service.py`: the seven manuscript native formulas, the
  V5 CU normalization, and typed failures for missing state quantities,
  missing references and `D^TO` identity violations. No action-specific
  percentage reductions exist on this path.
- Added the Pyomo + HiGHS parity backend (`model/M3/solver.py`) as a
  development-time check only. It re-solves the finite one-hot action-grid
  problem, compares `u*` and `J(u*)` to exact enumeration, and fails closed on a
  non-optimal solver termination. Production Stage II remains enumeration.

## 2. Core files changed/added

- `model/M2/consequence_service.py`
- `model/M3/stage1.py`
- `model/M3/transition.py`
- `model/M3/support.py`
- `model/M3/stage2.py`
- `model/M3/solver.py`
- `tests/m3/test_stage1_v2.py`
- `tests/m3/test_stage2_v2.py`
- `validation/m3_enumeration_highs_parity.py`
- `requirements.txt` (`pyomo==6.10.1`, `highspy==1.15.1`)

## 3. Scientific interfaces now available

- `AttentionCapacityRule`, `attention_capacity_k`, `rank_signals`,
  `select_attention`, `select_paired_attention`; outputs are
  `AttentionDecision` / `AttentionEntry` with score, rank, `q`, `K`, selected
  flag, signal type and stable identity.
- `TransitionContext`, `off_block_boundary`, `scenario_headroom`,
  `effective_recovery`, `apply_recovery`.
- `TrainQuantileRule`, `turnaround_lower_bound_minutes`, `floor_to_grid`,
  `max_recovery_minutes`, `build_headroom_summary` -> `HeadroomSummary`.
- `RecoveryPolicy`, `action_grid`, `consequence_value`, `expected_objective`,
  `objective_by_grid`, `solve_recovery` -> `RecoveryDecision` with
  `SolverStatus.EXACT_ENUMERATION`.
- `ConsequenceReferenceBinding`, `native_consequence_vector`,
  `M2ConsequenceService` -> `ConsequenceScenario` / `ConsequenceScenarioSet`.
- `solve_with_highs` -> `HighsParityResult` (`SolverStatus.HIGHS_PARITY`) for
  representative PRE/TURN parity only.

## 4. Legacy assets reused

- The V5 CU registry produced in Phase 2
  (`registry_hash sha256:219c6d37a47080df1b6687cae682ca57bdd0233eb83f3bb746cdacd25cea1bef`)
  supplies the component scales through the same `M2ConsequenceService` used by
  baseline and post-action states.
- `p_itinerary_native` already carries `s_conn`, so
  `P_itinerary = N_pax s_conn 1(D^TO > 45)` needed no new formula.
- The legacy M3 A01–A23 template action-response path is not reused in the
  paper-primary optimization contract; it remains legacy only.
- The uncommitted 2026-09-16 M3/M4 WIP was left in place byte-for-byte and was
  not staged; the baseline recovery point is
  `tmp/v2_wip_baseline_20260918/`.

## 5. Scientific blockers / new assumptions

- **No new scientific assumption was introduced.** The stage rule, action space,
  transition, objective, tie-break and solver path all come from the current
  manuscript body and instruction rev2.
- `m^CS` remains nominal `0.90` only; the current manuscript body predefines no
  sensitivity values, so no grid is activated. This is carried into Phase 5.
- The HiGHS parity inputs are deliberately synthetic, contract-valid diagnostics
  (`SYNTHETIC_PARITY_INPUT_NOT_SCIENTIFIC_TRAIN_SUPPORT`). They are not Train
  support, not Development evidence and not paper results.
- Pre-existing legacy failures outside Phase 3 scope (unchanged from Phase 2):
  `tests/m1/test_feature_gate_b2.py` (2), `tests/m1/test_feature_gate_b2r.py`
  (2) and `tests/m1/test_model_baseline_fingerprint.py` (1). They are reported,
  not used as a V2 completion gate, per instruction section 28.

## 6. Artifacts created

- `artifacts/diagnostics/v2_phase3/M3_ENUMERATION_HIGHS_PARITY.json`
  (`status = PASS`, `formal_path = EXACT_ENUMERATION`,
  `parity_backend = PYOMO_HIGHS`, `final_test_access_count = 0`,
  `final_test_paths_read = []`).
- Focused tests: `tests/m3/test_stage1_v2.py`,
  `tests/m3/test_stage2_v2.py`.
- This report.

## 7. Verification and next dependency unlocked

- `python -m pytest tests/m3/test_stage1_v2.py tests/m3/test_stage2_v2.py -q`
  -> 45 passed.
- `python -m pytest tests/decision tests/pre tests/m1 tests/m2 tests/m3 -q`
  -> 454 passed, 5 pre-existing legacy failures (listed in section 5); no new
  Phase-3 failure.
- `python validation/split_isolation.py` -> PASS (6 cases,
  `final_test_access_count = 0`).
- `python validation/m3_enumeration_highs_parity.py` -> PASS for representative
  PRE and TURN nodes; exact enumeration and HiGHS agree on `u*` and `J(u*)`;
  TAXI `U = {0}` typed `NOT_ACTIONABLE` check passes.
- `python -m compileall -q model/common model/PRE model/M1 model/M2 model/M3`
  -> clean.
- No Final-Test path was read or written; `FINAL_TEST_ACCESS_COUNT` remains 1.
- Phase 4 (M4 common-basis evaluator) is unlocked.
