# Phase 5 Report - Development families, Train support, and draft freeze

Branch `v2/paper-primary`; instruction `docs/AirSlot_V2_Instruction_rev2_20260918.md`.
Phase 4 checkpoint: `a70b805 v2(phase4): M4 common-basis attention and recovery evaluation`.

## 1. Completed scope

- Materialized the canonical 2019-H1 Train support used by Stage II:
  `2,668,531` legal rotations, median `57.0` minutes, `T^{turn,lb}=Q20=41.0`,
  and `U_max=floor5(Q90(H^{+,fact}|H^{+,fact}>0))=45.0` minutes. The resulting
  action grid is `{0,5,...,45}`. Q10/Q30 and Q80/Q95 sensitivities are
  materialized alongside the nominal values.
- Reused the corrected A2 turnaround diagnostic as the Train median and
  signed-delay semantic authority. The full-H1 build differs from the
  month-streaming A2 scan by exactly two January-to-February boundary episodes;
  no streamed-only episode exists. The superseded uncorrected reference is
  recorded, not used.
- Materialized Development Family A for the frozen `HISTORY_H16_PRIMARY`,
  `CURRENT_H16_COMPARATOR`, and matched `HISTORY_H8_SENSITIVITY`:
  coordinate CRPS/MAE/coverage/interval width, expected CU transmission, and
  paired metric distances. No ranking or directional claim is emitted.
- Materialized Development Family B from the frozen H16 Joint source for
  `JOINT`, `POINT`, and `MARGINAL`: coordinate metrics, vector Energy Score,
  Variogram Score at `p=0.5`, representation-specific variogram rows, and
  consequence distortion versus the Joint source. Marginal remains a
  deterministic coordinate permutation, not a physical-independence claim.
- Materialized the Phase-5 matched H8 sensitivity from the exact H16 cache and
  training contract. The only changed factor is hidden width
  (`16 -> 8`); the matched-contract audit is `PASS`.
- Built the draft scientific freeze:
  `registries/v2_scientific_freeze_draft.json` and
  `docs/V2_SCIENTIFIC_FREEZE_SUMMARY.md`, both marked
  `DRAFT_NOT_ACTIVATED`, with `freeze_commit=PENDING`.
- Fixed the integration boundary for the four Development nodes that resolve to
  `UNSUPPORTED_REFERENCE`: they now remain typed unsupported with no M2 call and
  no zero-filled consequence. A regression test was added.

## 2. Core files changed/added

- `validation/v2_phase5/__init__.py`
- `validation/v2_phase5/common.py`
- `validation/v2_phase5/families.py`
- `validation/v2_phase5/freeze.py`
- `validation/v2_phase5/h8.py`
- `validation/v2_phase5/run_phase5.py`
- `validation/v2_phase5/train_support.py`
- `tests/phase5/test_artifact_contracts.py`
- `tests/phase5/test_family_support_semantics.py`
- `tests/phase5/test_guardrails.py`
- `tests/phase5/test_train_support_contracts.py`
- `model/M1/state_representation.py`
- `model/common/decision_contracts.py`
- `model/M3/transition.py`
- `tests/decision/test_decision_contracts_v2.py`
- `tests/m1/test_state_representation_v2.py`
- `docs/V2_PHASE5_REPORT.md`

## 3. Scientific interfaces now available

- `materialize_train_support()` returns the canonical Train population gates,
  turnaround quantiles, factual headroom summary, `U_max`, action grid, and
  representation-independent sample artifact.
- `materialize_family_a()` emits per-model Development metrics without using
  `L_att`, `L_rec`, or any total loss for selection.
- `materialize_family_b()` emits representation-specific metrics and
  `FAMILY_B_VARIogram_ROWS.npz`; rows are never shared across representations.
- `materialize_h8_sensitivity()` reuses the matched H8 artifact only after
  source-cache, training-contract, and checkpoint-hash checks pass.
- `build_freeze_draft()` writes the compact draft registry and human-readable
  summary with all Section-15 fields, the V4-to-V5 CU supersession record,
  nominal `m^CS=0.90`, and no manuscript-predefined sensitivity grid.
- Unsupported reference bindings remain explicit typed states rather than
  triggering a consequence service call or an implicit zero.

## 4. Legacy assets reused

- Frozen H16 History+Joint and Current H16 Development artifacts.
- The exact H16 source cache, formal cohort, and PRE Development bridge
  (`1,769` decision nodes from `128` episodes).
- The V5 CU registry and V4 passenger references:
  T-100 expected passengers, DB1B connection share, downstream exposure, taxi,
  and the five retained principal Train medians. `P_itinerary` uses the
  corrected `N_pax * s_conn * I[D_TO > 45]` formula.
- The corrected A2 turnaround diagnostic is used for the Stage-II Train median
  gate. The old uncorrected V1 reference is recorded as superseded.
- The 2026-09-16 v3 WIP remains untouched, unstaged, and outside the
  paper-primary dependency graph. Its 14 tests were run for status only:
  `14 passed`.

## 5. Scientific blockers / new assumptions

- **No new scientific assumption was introduced in Phase 5.** The Stage-II
  rules, family metrics, freeze fields, and sensitivity ownership follow the
  manuscript body and instruction rev2.
- `m^CS` remains nominal `0.90`; sensitivity is explicitly empty with
  `NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES` because the manuscript body
  predefines no numeric grid.
- Four PGV-to-CLT nodes have no admissible reference binding and remain typed
  `UNSUPPORTED_REFERENCE`; they are excluded, not zero-filled.
- The A2 signed-delay correction is used for the Stage-II Train median and
  population gate. The M2 node-reference bundle remains the V4/V5 frozen
  reference payload specified by the approved Phase-2 carryover; this report
  does not silently reopen that upstream reference lineage.
- No new Final-Test access was made. `FINAL_TEST_ACCESS_COUNT=1` is unchanged,
  and no Final-Test path was read or written.

## 6. Artifacts created

- `artifacts/diagnostics/v2_phase5_development/PHASE5_RUN_SUMMARY.json`
  (`status=PASS`, `node_count=1769`, `final_test_access_count=1`)
- `artifacts/diagnostics/v2_phase5_development/FAMILY_A_STATE_FAMILIES.json`
  (payload hash `sha256:cdbe922ac90aec67f8c917df04b008aa52906b03f3be77fe60e13f2bbb833775`)
- `artifacts/diagnostics/v2_phase5_development/FAMILY_B_REPRESENTATION_FAMILIES.json`
  (payload hash `sha256:9072108a15acc0e04a2675e68c0695bd7106f582352c988e4352d0b7c3408adf`)
- `artifacts/diagnostics/v2_phase5_development/TRAIN_TURNAROUND_HEADROOM_SUMMARY.json`
- `artifacts/diagnostics/v2_phase5_development/REFERENCE_BINDING_AUDIT.json`
- `artifacts/models/m1/M1_V2_PHASE5_H8_SENSITIVITY/`
- `registries/v2_scientific_freeze_draft.json`
  (payload hash `sha256:ee64c5e5295eb85d46a94d2f3abcb76dcfb1e03826acb09710f15135f6ea4e4b`)
- `docs/V2_SCIENTIFIC_FREEZE_SUMMARY.md`

## 7. Verification

- `python -m validation.v2_phase5.run_phase5 --skip-train-support` -> `PASS`
  (all 1,769 Development nodes; train support reused after its own materialization).
- `pytest tests/phase5 tests/decision/test_decision_contracts_v2.py
  tests/m1/test_state_representation_v2.py
  tests/m2/test_comparison_support_v2.py
  tests/m3/test_stage2_v2.py tests/m4/test_evaluation_v2.py
  tests/m2/test_cu_registry_v5.py` -> `90 passed`.
- `python validation/split_isolation.py` -> `PASS`, final-test access `0`.
- `python validation/m3_enumeration_highs_parity.py` -> `PASS`; exact
  enumeration and Pyomo+HiGHS agree on `u*` and `J(u*)` for representative PRE
  and TURN cases; TAXI/COMP return `{0}` and `NOT_ACTIONABLE`.
- `python -m compileall -q model/PRE model/M1 model/M2 model/M3 model/M4
  validation/v2_phase5 tests/phase5` -> clean.
- Freeze guardrails confirm `DRAFT_NOT_ACTIVATED`, `freeze_commit=PENDING`,
  `L_total` never constructed, A00 never a recommendation, and
  representation-specific variogram rows.

## 8. Next dependency

Phase 6 is not entered by this work. Activating the scientific freeze and any
new Final-Test access remain separate human gates. The old Final-Test outputs
are not reusable under the V5 consequence and V2 representation definitions.
