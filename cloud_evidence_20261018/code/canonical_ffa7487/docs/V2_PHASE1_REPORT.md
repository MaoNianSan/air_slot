# Phase 1 Report — Contracts + PRE decision environment

Branch `v2/paper-primary`; instruction `docs/AirSlot_V2_Instruction_rev2_20260918.md`.
Phase 0 checkpoint: `ff74d1e v2(phase0): legacy/data audit, instruction rev2 sync, manuscript correction ledger`.

## 1. Completed scope

- Replaced the ad-hoc Phase-0 contract sketch with the instruction §34/§35 logical
  contracts: `DecisionEvidence`, `StateRepresentationSpec` (temporal x uncertainty),
  `StateScenarioSet`, `ConsequenceProfile` / `ConsequenceScenarioSet`,
  `PrioritySignal`, `AttentionDecision`, `RecoveryDecision`, `DecisionEvaluation`.
- Enforced the ownership boundary: PRE carries evidence/data support only.
  `ComparisonSupport` (`Omega^CS`, `m^CS`, nominal 0.90) is declared as M2-owned and
  cannot be carried by a PRE envelope.
- Encoded the裁定 items that change interfaces: `P^C` is the only
  consequence-based priority authority and `P^D` the parallel delay comparator,
  both consumed by one Stage-I selector contract on a shared common-support
  attestation; Stage-II contract carries `SolverStatus.EXACT_ENUMERATION` as the
  formal path with `HIGHS_PARITY` reserved for development-time parity; the
  manuscript-predefined `m^CS` sensitivity grid is empty
  (`PREDEFINED_COMMON_SUPPORT_SENSITIVITY = ()`).
- Added the PRE canonical-stage rule (choose the canonical node first, then
  evaluate support; never backfill a later supported node), the no-future-evidence
  rule, split isolation, and the stage-class table (`PRE`/`TURN` actionable,
  `TAXI`/`COMP` non-actionable).
- Added `validation/split_isolation.py` as the Phase-1 acceptance entry point.

## 2. Core files changed/added

- `model/common/decision_contracts.py`
- `model/PRE/decision_environment.py`
- `tests/decision/test_decision_contracts_v2.py`
- `tests/pre/test_decision_environment_v2.py`
- `validation/split_isolation.py`

## 3. Scientific interfaces now available

- `DecisionEvidence(episode_id, chain_id, node_id, decision_time, stage, split,
  scheduled_milestones, observed_milestones, dynamic_evidence, static_references,
  availability, support)`; `support` is evidence/data support only.
- `StateRepresentationSpec(temporal, uncertainty, history_capacity, history_scope)`
  with `HISTORY_H16_PRIMARY` primary and `HISTORY_H8` lower-capacity comparator;
  H32 is not constructible (`STATE_SPEC` errors) and Delay is not a representation.
- `StateScenarioSet` with the per-scenario `D_TO == D_OB + D_TX` invariant and the
  realized-milestone collapse rule.
- `ConsequenceScenarioSet` (+ `ConsequenceProfile`) keeping missing, unsupported
  and supported zero distinct.
- `PrioritySignal(signal_type="DELAY"|"CONSEQUENCE", score, support,
  comparison_support_mass, comparison_support_threshold)`.
- `AttentionDecision` for one shared Top-K selector.
- `RecoveryDecision(actionable_status, headroom_summary, action_grid, u_max,
  u_star, j_zero, j_star, recoverable_value, lambda_policy, solver_status)`.
- `DecisionEvaluation(reference_id, comparator_id, delta_attention_value, L_att,
  delta_recovery_objective, L_rec, A0, A5, diagnostics, support_status)`; no
  `L_total` field exists by construction.

## 4. Legacy assets reused

- `model/common/enums.py` (`OperationalStage`, `SupportState`, `EvidenceClass`,
  `DecisionTimeRole`, `weaker_or_equal`) and `model/common/value_objects.py`
  (`FrozenModel`, `TimeContext` semantics) are unchanged and reused.
- `model/M4/comparison/common_basis.py` continues to expose
  `ComparisonSupportRequirement` to the legacy path; the V2 contract does not
  redefine it.
- No legacy M1–M4 runtime module was modified. The 9/16 v3 WIP
  (`model/M3/*`, `model/M4/*`, `docs/ACTION_DECISION_CONTRACT.md`,
  `formal/RUNTIME_PATH.md`) is untouched and unstaged.

## 5. Scientific blockers / new assumptions

- None for Phase 1. `m^CS` remains nominal 0.90 only; the appendix-only
  `{0.50, full-support}` grid is not manuscript-authoritative and is recorded as
  an open manuscript item (`V2_PHASE0_AUDIT.md`).
- `P^D` authority is the manuscript §4 `eq:empirical_delay_score`; the legacy
  `summarize_delay_score` stays classified as a deviating implementation. The
  Stage-I delay adapter is implemented in Phase 3, not here.
- `HISTORY_H32` is intentionally not constructible; restoring it would require a
  manuscript change and is out of scope.

## 6. Artifacts created

- `artifacts/diagnostics/v2_phase1/SPLIT_ISOLATION_REPORT.json`
  (`V2_SPLIT_ISOLATION`, 6 cases, `status = PASS`, `final_test_access_count = 0`).

## 7. Verification and next dependency unlocked

- `python -m pytest tests/pre tests/decision -q` → 66 passed.
- `python validation/split_isolation.py` → PASS (exit 0).
- `python -m compileall -q model/common model/PRE` → clean.
- `FINAL_TEST_ACCESS_COUNT` unchanged (= 1, no new access); `artifacts/experiment/final_test/`
  was not read or written.
- Phase 2 is unlocked: M1 representation ownership (Point joint medoid, Marginal
  coordinate permutation that must not be described as physical independence,
  Joint preserved) and M2 comparison-support + CU V5 registries.
