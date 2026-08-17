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

- decision_id: `M2_FORMAL_FREEZE`
- date/time: `2026-08-18`
- status: `PENDING`
- question: Freeze the remaining M2 formal choices required before M2 can be marked fully frozen.
- open items: valuation `V_k` coefficients and registry identity; formal `ConsequenceScope` registry and aggregation rule; Data2 passenger reference variant/artifact; service policy threshold; itinerary disruption evidence policy.
- boundary: no normative valuation or service value is selected from Development performance.

## M3_RESPONSE_PARAMETER_FREEZE

- decision_id: `M3_RESPONSE_PARAMETER_FREEZE`
- date/time: `2026-08-18`
- status: `PENDING`
- question: Freeze non-A00 recovery-action response parameters required for formal multi-action M4 ranking.
- open items: response models/parameters for the 22 non-A00 templates; empirical/operator provenance support; low/base/high sensitivity ranges consumed by Exp4.
- current contract: A00 is `NOT_REQUIRED`; all other templates remain `NOT_FROZEN` and are forced out of M4 formal ranking.
- boundary: no response utility weight or action parameter is selected from Development performance.
