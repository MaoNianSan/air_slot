# AIR_SLOT_HUMAN_GATE_DECISION_MEMO_20260826

Status: DRAFT DECISION MEMO for interactive human approval.
Purpose: close every remaining human gate needed before results can be filled
into the manuscript. All experiments stay DEVELOPMENT_ONLY until Final Test is
authorized; this memo does NOT authorize Final Test by itself.
Read-only facts below were re-verified on 2026-08-26 against current files.

## Verified current state (read-only, 2026-08-26)

- G2/G3 closed: `registries/m4_eur_mapping_assumption_grounded_v2.json` (F7
  P_itin/P_serv ABSTAIN; F8 RMB system-level ABSTAIN) and
  `codex_framework/PAPER_OUTPUT_SPEC_V1.json` (frozen).
- Calibration: `configs/scientific/foundation.yaml` m1_v2_calibration_contract
  is FROZEN policy with `positive_quantile_calibration:
  QUANTILE_CALIBRATION_NOT_APPLIED`, note "no fitted calibration artifact yet;
  shared by STATE_AWARE and FAST; Final Test forbidden".
- Data2 factual replay: `docs/reconciliation/ROUND2_SECTION4_ALIGNMENT.md`
  still records "Data2 factual replay availability is unresolved" (human
  decision pending).
- Exp1B comparator exists: H32 CURRENT-only checkpoint, budget/calibration
  policy identical to reference (dev closure manifest).

## Decisions requested

### D1 Exp2B matched-case rule (recommend Option A)

- Option A (RECOMMENDED): pair episodes whose seven-component total J is in
  the same episode-level decile band (computed on the r=7 supported
  components), and define "different composition" as a top-3 channel share
  flip between at least two channels (F/P/R). Both directions reported; ties
  deterministic. This is declared in the protocol, not tuned.
- Option B: only require total-J proximity (same decile band), no composition
  flip requirement (weaker test).
- Option C: user supplies another rule.

### D2 Data2 factual replay / message-arrival availability (recommend Option A)

- Option A (RECOMMENDED, safe): keep UNRESOLVED + ABSTAIN. Any paper claim
  requiring availability_time <= information_cutoff for Data2 realized events
  stays abstained; weather 5-min lag rule remains as is.
- Option B: user provides the factual availability rule (e.g., a data vendor
  timestamp column meaning) with provenance; then I codify it.
- Option C: treat realized events as available at observation time + 5 min.
  This is an assumption, not a verified fact; would need explicit assumption
  labeling.

### D3 Table 1 STATE_AWARE_H32 D_OB/D_TX CRPS cells (recommend Option A)

- Option A (RECOMMENDED): keep blank per frozen spec; add caption caveat "not
  saved by M1; never inferred". No Final Test scope expansion.
- Option B: additionally save these two CRPS metrics before Final Test
  (expands M1 inference scope; needs new derivation + tests).

### D4 Section 4/5 text fixes (recommend Option A)

- Option A (RECOMMENDED): approve all eight pending text fixes: (1)
  same-checkpoint -> same architecture/budget/calibration-path with separate
  checkpoints; (2) R_IB described as coordinate of z, T_IB_A00 its scenario
  mapping; (3) principal event D_TO>30 wording; (4) historical-reference
  baseline naming (HISTORICAL); (5) D_TX lead-time caveat (no planned
  wheels-off reference); (6) Top-1 support conditions; (7) dedup duplication;
  (8) calibration wording aligned with D7 (policy/path identical, no fitted
  artifact claim).
- Option B: approve only items 1-4 now.
- Option C: defer all; numbers cannot be filled consistently until fixed.

### D5 Exp1 spec addendum (recommend Option A)

- Option A (RECOMMENDED): pre-approve the addendum template I specified for
  T1 (panels, bootstrap 2000/seed 20260825, common-supported-observations
  rule); after T1 outputs land and input hashes are verified, freeze the
  addendum without another full review round.
- Option B: wait for T1 outputs, then review the draft addendum before
  freezing.

### D6 Final Test scope, seeds, roots, naming (recommend Option A)

- Option A (RECOMMENDED): no retraining; reuse frozen checkpoints
  (state-aware H32, CURRENT-only comparator, tabular baselines). Final Test =
  rerun all record materialization + figures + Table 1 under the frozen spec
  with `paper_result=true`, new output root
  `artifacts/paper_results_v1/` and
  `outputs/manuscript_values/section5_secondary_analysis/paper/`, seeds
  unchanged (20260813 CRN scenarios; 20260821 training; 20260825 bootstrap),
  DEVELOPMENT_ONLY suffix removed only in the new roots. T1-T5 dev outputs
  remain untouched.
- Option B: also retrain H32/CURRENT (more expensive, needs justification).
- Option C: user supplies another scope.

### D7 Calibration artifact gate (recommend Option A)

- Option A (RECOMMENDED): no fitted calibration artifact before Final Test.
  All Exp1 calibration wording stays "identical calibration policy/path;
  quantile calibration not applied" per frozen contract. No claim of fitted
  calibration.
- Option B: fit the calibration artifact now (expands scope, new decision
  about procedure), then Final Test.

### Confirm-only items (no decision needed unless user objects)

- C1: FAST/CURRENT-only comparator checkpoint remains the registered Exp1B
  comparator under the identical-budget contract (already materialized).
- C2: RMB remains system-level ABSTAIN; no RMB numbers appear in the
  manuscript; monetary reporting is constructed-EUR five-component only.
- C3: G2-P_itin/P_serv remain ABSTAIN event counts (F7); Table/Figure captions
  say event counts are visible but monetary not anchored.

## Approval line

Answer format: "D1=A, D2=A, D3=A, D4=A, D5=A, D6=A, D7=A, C1-C3=OK" (or
per-item overrides). After approval, the copyable instruction for VS will
embed D1-D7 plus T1-T5 and stop at the Final Test boundary; Final Test
execution starts only when D6 is approved AND the user issues the explicit
Final Test instruction (D6 approval alone does not trigger it).

## Safety

FINAL_TEST_ACCESS_COUNT = 0 until the explicit Final Test instruction.
PAPER_FULL_RUN = FALSE. GIT = NO_COMMIT.

## Interaction log 2026-08-26 (round 1)

- D1 = A (approved): Exp2B matched-case = same-decile-band total-J pairing +
  top-3 channel-share flip, declared in protocol.
- D2 = A (confirmed, not new): consistent with frozen
  `DATA2_FACTUAL_REPLAY_POLICY_A1` (2026-08-21): retrospective event-time
  replay assumption only; `observed_availability_claim=false`,
  `production_availability_claim=false`. Replay lag 0 min; weather 5 min.
- D3 = A (approved): Table 1 STATE_AWARE_H32 D_OB/D_TX CRPS cells stay blank
  with caption caveat; no M1 scope expansion for these cells.
- D5 = A (approved): Exp1 spec addendum template pre-approved; freeze after
  T1 output hash verification.
- D6 = A (approved): Final Test = no retraining; reuse frozen checkpoints;
  rerun all materialization + figures + Table 1 under frozen spec with
  paper_result=true into `artifacts/paper_results_v1/` and
  `outputs/manuscript_values/section5_secondary_analysis/paper/`; seeds
  unchanged (20260813/20260821/20260825). Approval alone does not trigger
  Final Test; explicit instruction required.
- D7 = B (approved in principle): fit a calibration artifact before Final
  Test. Sub-decisions D7a-D7d pending.
- D4 = PENDING (user did not answer).
- C1-C3 = PENDING (user did not explicitly confirm).

## Interaction log 2026-08-26 (round 2 — final)

- D7 = B with sub-decisions:
  - D7a = A: fit only the two contracted calibration pieces
    (DISCRETE_HAZARD_EVENT_TIME_NLL; HURDLE_ZERO_BINARY_CE_TEMPERATURE);
    positive-quantile stays QUANTILE_CALIBRATION_NOT_APPLIED;
    M1_CALIBRATION_CONTRACT_V1 is NOT modified.
  - D7b = A: one-shot fit on the calibration split only (2019-07-01..31,
    64 episodes); no selection loop; Train/Development/Final Test untouched;
    before/after metrics are provenance only.
  - D7c = A: one shared artifact applied identically to STATE_AWARE H32 and
    the CURRENT-only comparator; "calibration path identical" remains true.
  - D7d = A: Exp1 dev records (pre-artifact era) stay untouched; Final Test
    applies the shared artifact and reruns materialization; Section 4
    wording changes to "shared calibration artifact fitted on the
    calibration split" (D4 item 8).
- D4 = A: all eight Section 4/5 text fixes approved (TeX text-only patch;
  no numbers filled; no other manuscript edits).
- C1 = OK, C2 = OK, C3 = OK.
- Consequence: configs/scientific/foundation.yaml stays untouched; its stale
  note "no fitted calibration artifact yet" is superseded by the new artifact
  manifest + HUMAN_DECISION_LOG entry, recorded as such.

## Interaction log 2026-08-26 (round 3 — human points)

- HP1 = A: automatic Final Test authorized. Dispatching V3 to VS = full
  authorization; dev chain completes -> Final Test starts without asking.
- HP2 = A: morning report first; the user sends a single "填" message; VS
  then fills numbers/tables/figures into the manuscript TeX. No automatic
  pre-fill.
- HP3 = B with mandatory recording: overnight AUTO_ASSUMED_FIX items are
  accepted by default; no mandatory review. Every fix, quarantine, and
  literature-derived assumption is still recorded in
  docs/AUTONOMOUS_FAILURE_LIST_20260826.md and docs/HUMAN_DECISION_LOG.md
  with citations; anything that changes a frozen contract appears at the top
  of the morning report for an optional quick scan.
