# AIR_SLOT_AUTONOMOUS_OVERNIGHT_CHAIN_20260826

Status: EXECUTABLE SUPPLEMENT. Dispatching this file to the VS session = user
authorization for (a) V1/V2 gap closure, (b) T-cal and T-tex tasks, (c) the
autonomous failure-recovery policy, and (d) AUTOMATIC Final Test per the
pre-approved D6 scope, including `paper_result=true` outputs.
The user does not want per-step checks; the only human review point is the
morning report.

## 0. Context and merge points

- V1 `AIR_SLOT_EXP_DEV_GAP_CLOSURE_20260826` is running (T0 PASS, T1 done,
  T2 materialization in progress, T3/T4/T5 pending). Do not restart completed
  work.
- V2 merge instructions were received without the T-cal/T-tex full texts;
  they are now fully specified below (Sections 1-2) and supersede any
  truncated references.
- Frozen sources of truth (must not be edited): `PAPER_OUTPUT_SPEC_V1.json`,
  `registries/m4_eur_mapping_assumption_grounded_v2.json`,
  `AIR_SLOT_EXP23_G2_FREEZE_DECISIONS_20260825.md` (F1-F8),
  `AIR_SLOT_HUMAN_GATE_DECISION_MEMO_20260826.md` (D1-D7, C1-C3).

## 1. T-cal — calibration artifact (D7=B, D7a-D7d=A)

- Scope: fit only the two pieces already declared in
  `M1_CALIBRATION_CONTRACT_V1` (configs/scientific/foundation.yaml L234-245):
  (i) predecessor probability calibration `DISCRETE_HAZARD_EVENT_TIME_NLL`;
  (ii) successor zero-mass calibration `HURDLE_ZERO_BINARY_CE_TEMPERATURE`.
  Positive-quantile stays `QUANTILE_CALIBRATION_NOT_APPLIED`. Contract V1 and
  `configs/**` are NOT edited; foundation.yaml's stale note is superseded by
  the new artifact manifest + decision-log entry (record this, do not edit
  the config).
- Fit rule (D7b): one-shot fit on the calibration split only
  (2019-07-01..2019-07-31, 64 episodes, `configs/evaluation/common.yaml`);
  no selection loop, no hyperparameter search loop; Train / Development /
  Final Test splits are not read and not written; before/after calibration-
  split metrics are recorded as provenance only, never used to choose the
  artifact.
- Application (D7c): ONE shared artifact, applied IDENTICALLY to the frozen
  STATE_AWARE H32 checkpoint and the CURRENT-only comparator checkpoint
  (`exp1_full_development/exp1_closure_20260825/EXP1B_CURRENT_ONLY_H32/`).
  Inference with frozen checkpoints only; retraining forbidden. The
  "calibration path identical" claim remains valid.
- Artifact outputs: `artifacts/calibration/m1_v2_calibration_20260826/`
  with manifest containing: input checkpoint hashes (before and after
  unchanged), calibration split interval, fitting procedure, parameters,
  before/after metrics, `shared_by=[STATE_AWARE_H32, CURRENT_ONLY]`,
  `quantile_calibration=NOT_APPLIED`, `FINAL_TEST_ACCESS_COUNT=0`, safety
  counters all zero.
- Tests: `tests/experiments/exp1/test_calibration_artifact_contract.py`
  asserting: checkpoint hashes unchanged (no weights touched); only the
  calibration split was read; both models apply the SAME artifact; quantile
  calibration not applied; no Development split usage.
- Effect on existing records (D7d): Exp1 dev records stay untouched; T1-T4
  continue on the uncalibrated frozen dev records; ONLY Final Test applies
  the shared artifact and reruns materialization.

## 2. T-tex — the eight Section 4/5 text fixes (D4=A; TeX text-only)

Locate each passage by pattern, patch minimally, record file:line diffs in
`docs/HUMAN_DECISION_LOG.md`. No numbers are filled anywhere; no other
paragraphs, labels, citations, or the .bib are changed.

1. Checkpoint wording: in `sections/05_experiment.tex` (Exp1B passage, near
   L100-113, "reuse the same train-frozen state-aware architecture and
   checkpoint") replace the same-checkpoint claim with: same architecture,
   identical training budget and identical calibration path, separate
   checkpoints.
2. R_IB coordinate: in the `z=(R^IB, Delta^OB, T^TX)` definition (L121-127),
   keep `R^IB` as a coordinate of the operating state and state explicitly
   that its scenario mapping is `T_IB_A00` (not a new measured variable).
3. Principal event: wherever the principal delay-event endpoint is described
   in Exp1, state it uniformly as `D^TO>30` (grep `D^TO` / `delay-event` /
   `Brier`); no other threshold wording.
4. Baseline naming: in Exp4 (L255-263 region), name the historical reference
   baseline `HISTORICAL` consistently (grep `historical reference`); do not
   introduce new baseline names.
5. D_TX caveat: at the Exp4 lead-time / Table 1 passage, add the caveat that
   D_TX has no planned wheels-off reference, so its lead-time bins are NA and
   only OVERALL rows are reported; never interpolated.
6. Top-1 support conditions: at the Top-1 disagreement passages
   (e.g. L195-197), add that comparisons are made only on common supported
   observations, and unsupported components/actions are typed-excluded, not
   zero-filled.
7. Section 4 grammar/dedup: in `sections/04_implement.tex`, fix "the
   datasets" (singular intended) and the duplicated "the" (see
   `docs/reconciliation/ROUND2_SECTION4_ALIGNMENT.md` publication-quality
   defects); text-only.
8. Calibration wording: wherever Section 4 claims no fitted calibration
   artifact exists, update to: a shared calibration artifact is fitted on the
   calibration split (discrete-hazard NLL and hurdle zero-mass temperature);
   positive-quantile calibration is not applied. Align with T-cal outputs
   (if T-cal failed, keep item 8 in the failure list and do not claim the
   artifact in TeX).

## 3. Continuation notes for the running T1-T5

- T1 (D5 pre-approved): after T1 output hash verification, freeze the
  addendum directly as
  `codex_framework/PAPER_OUTPUT_SPEC_V1_ADDENDUM_EXP1_20260826.json`; no
  second review.
- T2 (D1=A): matched-case rule is: episodes paired by episode-level
  decile band of the r=7 supported-component total J ("similar aggregate
  disruption"); "different composition" = a top-3 channel-share flip in at
  least two of the F/P/R channels; both directions reported; deterministic
  tie-break; declared in the protocol, not tuned. If T2 records were already
  materialized under the old wording, re-materialize ONLY the matched-case
  part and note it in the status block.
- T5: figure caption files under
  `outputs/manuscript_values/section5_secondary_analysis/` must be consistent
  with the eight T-tex fixes (HISTORICAL naming, D_TX caveat, Top-1 support
  conditions, checkpoint wording); `PAPER_OUTPUT_SPEC_V1.json` remains the
  only QA baseline; style QA is form/format-level only.

## 4. Autonomous failure-recovery policy (applies everywhere below)

On ANY failure, do NOT stop the chain:
1. Append a failure-list entry (file:line, root cause, affected task) to
   `docs/AUTONOMOUS_FAILURE_LIST_20260826.md`.
2. Consult the manuscript passage to recover the intended semantics.
3. Search the literature (online retrieval allowed, same discipline as the
   Cook & Tanner 2015 pass: official source, page-level citation, local PDF
   copy under `D:\Cache\Python\Temp\` if downloaded) for assumption-based
   solutions used by other studies.
4. Apply the fix as an explicitly labeled declared assumption
   (`AUTO_ASSUMED_FIX`, with source citation). Never fabricate numbers;
   prefer ABSTAIN/null where no literature or manuscript intent exists.
5. Frozen files are never edited in place: any required change is a NEW
   version (registry/decision doc) recorded in `HUMAN_DECISION_LOG.md` with
   `AUTO_ASSUMED_FIX` and the failure-list reference.
6. If a failure cannot be fixed without touching model weights, retraining,
   Final Test data integrity, or frozen artifacts: quarantine that item,
   continue the rest, and report it as `BLOCKED_WITH_LITERATURE_RATIONALE`
   in the morning report.

## 5. Automatic Final Test (pre-approved D6 scope; dispatching this file = authorization)

Trigger: run automatically after the dev chain (T-cal, T-tex, T2-T5) reports
all tests PASS or all failures resolved/quarantined. No further human
instruction is required.

Scope:
- No retraining. Reuse frozen checkpoints only: STATE_AWARE H32 (registered
  checkpoint hash), CURRENT-only comparator (cea56794...), tabular baselines
  (HISTORICAL, LIGHTGBM, RANDOM_FOREST) already registered in the Exp4
  records.
- Apply the shared T-cal calibration artifact to STATE_AWARE H32 and the
  CURRENT-only comparator.
- Rerun under the frozen spec (`PAPER_OUTPUT_SPEC_V1.json` + Exp1 addendum):
  Exp1A per-node records + frozen sorting diagnostic; Exp1B HISTORY/CURRENT
  prediction records (CRN-paired, seed 20260813); Exp2A Point/Marginal/Joint
  variogram; Exp2B r=7/3/1 including D1 matched-case; Exp3 valuation-only
  (F4/F5) and refresh/sync (F3 exact-vintage); Exp4 per-node records and
  10-bin lead-time grid (D_TX NA policy); M3 non-A00 / M4 production
  comparison/ranking (F4/F5 + registry v2; declared-assumption
  model-implied ordering wording only).
- Regenerate Figures 5A-C, 6A, 7A, 7B, 8 and Table 1 from the Final Test
  records; keep Table 1 STATE_AWARE_H32 D_OB/D_TX CRPS cells blank with the
  caption caveat (D3).
- Seeds unchanged: 20260813 (scenarios), 20260821 (training), 20260825
  (bootstrap). Bootstrap: episode-cluster, 2000 reps, percentile 95.
- Output roots: `artifacts/paper_results_v1/` (records/manifests) and
  `outputs/manuscript_values/section5_secondary_analysis/paper/`
  (figures/tables/captions). `paper_result=true`; no `DEVELOPMENT_ONLY`
  suffix in the new roots; dev outputs remain untouched.
- Every Final Test manifest records input hashes, seeds, calibration
  artifact hash, and safety counters.

## 6. Morning deliverable (single human review point)

- `outputs/manuscript_values/PAPER_FILL_READY_20260827.md` (or paper/ root):
  for every manuscript figure/table anchor, the exact value/summary block,
  support/ABSTAIN flags, and a "fillable verbatim / blank / caveated" mark.
- `docs/AUTONOMOUS_FAILURE_LIST_20260826.md`: all failures, fixes, and
  `AUTO_ASSUMED_FIX` labels with literature citations.
- `docs/HUMAN_DECISION_LOG.md`: entries for T-cal, T-tex, any
  `AUTO_ASSUMED_FIX`, and the Final Test run.
- Final status block (V2 template plus Final Test lines):
```makefile
AIR_SLOT_AUTONOMOUS_OVERNIGHT_CHAIN_20260826
DEV_CHAIN = T_CAL/T_TEX/T1/T2/T3/T4/T5 COMPLETE
DEV_TESTS = (数字) passed
FINAL_TEST = AUTO_RUN (D6 SCOPE, CALIBRATION_ARTIFACT_APPLIED)
PAPER_RESULTS = artifacts/paper_results_v1/ + section5_secondary_analysis/paper/
PAPER_FILL_READY = WRITTEN (verbatim/blank/caveated marks per anchor)
FAILURES = (数量) resolved / (数量) quarantined (list file path)
AUTO_ASSUMED_FIXES = (数量) (all cited, all logged)
FROZEN_ARTIFACTS_REWRITTEN = 0
MODEL_RETRAINED = FALSE
FINAL_TEST_ACCESS_COUNT = (实际计数)
PAPER_FULL_RUN = FALSE
GIT = NO_COMMIT
```
- TeX number-filling is NOT performed automatically; the morning report
  contains everything needed to fill directly after the user's one review.

## 7. Boundaries that survive autonomy

- No `model/**` edits, no retraining, no rewriting frozen artifacts, no Git.
- ABSTAIN over fabrication; every adopted assumption must be cited and
  labeled.
- Frozen contracts change only via new versions with decision-log entries.
- If a failure would require breaking any of these, quarantine and report;
  never silently violate.

## 8. Human-point decisions (2026-08-26 final, appended after HP round 3)

- HP1=A: dispatching this file is full authorization for automatic Final
  Test; do not pause to ask.
- HP2=A: after the morning report is written, STOP the fill step. The user
  will send a single "填" message; only then fill numbers/tables/figures into
  the manuscript TeX (fill scope: values, tables, figure file swaps, captions
  already fixed by T-tex; no other text).
- HP3=B with recording: AUTO_ASSUMED_FIX items are accepted by default; no
  mandatory human review. Record everything as specified in Section 4; put
  any frozen-contract change at the top of the morning report for an
  optional quick scan.

## 8. Human-point decisions HP1-HP3 (2026-08-26, interactively confirmed)

- HP1 = A: Final Test auto-run is authorized. Dispatching this file is the
  authorization; no further instruction is needed; do not ask.
- HP2 = A: the chain STOPS at the morning report. TeX number-filling is NOT
  performed automatically. The morning report must additionally include a
  PREVIEW of the exact TeX fill diff (numbers/captions/figure includes only,
  no other changes) so that filling can be applied immediately after the
  user's one-word "填" instruction. Do not apply the diff before that word.
- HP3 = B with mandatory recording: every `AUTO_ASSUMED_FIX` is
  accepted by default (no approval gate), but each one must be fully
  recorded: failure-list entry with root cause; literature source with
  page-level citation (or manuscript-intent reference); explicit
  `AUTO_ASSUMED_FIX` label; decision-log entry with file:line; and a line in
  the morning report listing accepted-by-default fixes. ABSTAIN/null is
  preferred where no source exists.
