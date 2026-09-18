# Phase 4 Report — M4 common-basis evaluator

Branch `v2/paper-primary`; instruction `docs/AirSlot_V2_Instruction_rev2_20260918.md`.
Phase 3 checkpoint: `3fe541c v2(phase3): M3 shared Stage-I selector and exact-enumeration Stage II`.

## 1. Completed scope

- Implemented M4 as a pure common-basis evaluator
  (`model/M4/evaluation.py`). It never reconstructs state, defines consequences,
  chooses a shortlist, optimizes recovery, or combines loss families.
- Stage-I common-basis evaluation follows the manuscript reference attention
  value `A_g^*(H) = sum_{i in H} S_{C,i}^*`:
  `Delta A = A^*(H^*) - A^*(H^(r))` and
  `L_att = Delta A / A^*(H^*)`. A zero reference value returns typed
  `N_A_NOT_DEFINED`, never a zero-filled ratio.
- Stage-I diagnostics are produced on the same candidate cohort: shortlist
  overlap, entered/displaced node identity, total and per-domain F/P/R coverage,
  Kendall tau, Spearman rho, and mean/max rank displacement. Diagnostics are
  explanatory and never substitute for `L_att`.
- Stage-II evaluation uses the fixed reference cohort
  `R_g^* = H_g^{C,*} intersection StageIISupported`. Comparator actions are
  scored only through the supplied reference objective map
  `J_i^*(u)`, so a representation is never evaluated under its own objective.
  `L_rec = sum_i Delta J_i / V_g^*`; `V_g^* = 0` returns typed
  `UNDEFINED_ZERO_RECOVERABLE_VALUE`.
- Stage-II diagnostics include `A_0 = Pr(u^{*(r)} = u^*)`,
  `A_5 = Pr(|u^{*(r)} - u^*| <= 5)`, and the four mutually exclusive
  activation events `MISSED_ACTIVATION`, `FALSE_ACTIVATION`,
  `UNDER_RECOVERY`, `OVER_RECOVERY`.
- Added ratio-of-sums aggregation helpers for multi-cohort evaluation. Attention
  and recovery are aggregated separately; no `L_total`, weighted total, or
  cross-family combination exists.
- The primary evaluator has no monetary dependency. The legacy secondary
  monetary interpretation remains non-primary and is not used here.

## 2. Core files changed/added

- `model/M4/evaluation.py`
- `tests/m4/test_evaluation_v2.py`
- `docs/V2_PHASE4_REPORT.md`

## 3. Scientific interfaces now available

- `evaluate_attention_allocation(...) -> AttentionEvaluation` with
  `reference_attention_value`, `comparator_attention_value`,
  `delta_attention_value`, `L_att`, `overlap_count`,
  `overlap_fraction_of_reference`, `entered`, `displaced`, F/P/R coverage,
  `kendall_tau`, `spearman_rho`, rank-displacement fields, typed `status` and
  reason codes.
- `AttentionEvaluation.contract_record() -> DecisionEvaluation`.
- `evaluate_recovery_loss(...) -> RecoveryEvaluation` with per-node reference
  and comparator actions, reference objective values, `Delta J`, per-node `V*`,
  aggregate `V_g*`, `L_rec`, `A0`, `A5`, activation-event counts and intensity
  diagnostics.
- `RecoveryEvaluation.contract_record() -> DecisionEvaluation`.
- `aggregate_attention_evaluations(...)` and
  `aggregate_recovery_evaluations(...)`, both ratio-of-sums aggregators.

## 4. Legacy assets reused

- The Phase-1 `DecisionEvaluation`, `AttentionDecision`,
  `RecoveryDecision`, `EvaluationFamily` and `TypedStatus` contracts.
- M2 reference attention values (`P^C`) and M3 shortlist/recovery outputs are
  consumed as inputs; M4 does not recompute them.
- The 2026-09-16 uncommitted M4 screening/alignment WIP remains in place and is
  not reused on the paper-primary path (Stage-I selection belongs to M3 in V2).
  No WIP file was modified or staged.

## 5. Scientific blockers / new assumptions

- **No new scientific assumption was introduced.** `L_att`, `L_rec`, `R_g^*`,
  `A_0`, `A_5` and the activation events follow the manuscript and instruction
  rev2.
- Supporting-diagnostic operationalization recorded for audit: "coverage" is
  the shortlist share of the cohort's reference domain burden,
  `sum_{i in H} S_{d,i}^* / sum_{i in cohort} S_{d,i}^*`, for
  `d in {F,P,R}`. It is an explanatory diagnostic, not a primary estimand.
- Zero-denominator policy is explicit: zero reference attention value ->
  `N_A_NOT_DEFINED`; zero aggregate reference recoverable value ->
  `UNDEFINED_ZERO_RECOVERABLE_VALUE`.
- Monetary interpretation remains secondary and outside the primary evaluator;
  no new monetary mapping was introduced.

## 6. Artifacts created

- `tests/m4/test_evaluation_v2.py` (11 focused tests).
- This report.
- No Final-Test artifact was read or written.

## 7. Verification and next dependency unlocked

- `python -m pytest tests/m4/test_evaluation_v2.py -q` -> 11 passed.
- `python -m pytest tests/m4 -q` -> 58 passed.
- `python -m py_compile model/M4/evaluation.py` -> clean.
- `FINAL_TEST_ACCESS_COUNT` remains 1; no Final-Test path was touched.
- Phase 5 (Section 4 Development families + Train-support materialization and
  freeze draft) is unlocked.
