# ROUND2_TRANCHE3_FULL_AFTER

- Closure date: 2026-08-20
- Repository HEAD: `66002114d85e575f5b6a89bac545843949c08e59`
- Validation boundary: engineering tests only; no Final Test read, paper experiment,
  M2 implementation, commit, or push.

## Closure result

The production code path now implements the typed chain

```text
legal E_{<=t}
  -> PRE factual/static publication
  -> PREState
  -> M1 adapter
  -> chi=(h_history,r_fast,c_static)
  -> hazard/hurdle heads and calibration
  -> forecast and ancestral scenarios
```

Forecast and scenario generation share `_information_state`. The forecast path
auto-derives `r_fast`; PRE-published train-frozen turnaround/taxi values form the
numeric `c_static` block, while route/carrier/aircraft/schedule identities retain
typed lineage without ordinal encoding.

Factual replay is role-aware and cutoff-gated. `M1Service.generate_scenarios`
derives observed primitives from PRE and rejects caller-injected future truth.
The event and availability timestamps must both be no later than the information
cutoff. State contraction fixes `T_IB_A00`, then `D_OB`, then `D_TX` as legal facts
appear, while preserving absolute event time and scenario lineage.

Hazard calibration uses active-row discrete event-time likelihood. D_OB and D_TX
zero logits receive separate binary-CE temperatures. Positive quantiles remain
`QUANTILE_CALIBRATION_NOT_APPLIED`; calibration-split coverage diagnostics are
computed and saved together with calibration version, split, policy, and fitted
temperatures.

## Validation evidence

- Focused tranche3: `43 passed`.
- M1 tests represented in the complete suite: `124`.
- PRE tests represented in the complete suite: `34`.
- Integration tests represented in the complete suite: `34`.
- Complete repository engineering suite: `647 passed, 1 skipped` in 58.84 s.
- `python -m compileall -q model/M1 model/PRE`: PASS.
- `git diff --check`: PASS (Git emitted only CRLF normalization warnings for
  two registry files).

The skipped test and warning volume are pre-existing/non-failing test behavior;
no test failure remains.

## Required final report

```text
AIR_SLOT_ROUND2_TRANCHE3_FULL_CLOSURE

REPOSITORY_HEAD=66002114d85e575f5b6a89bac545843949c08e59
WORKTREE_STATUS=DIRTY_EXPECTED_UNCOMMITTED_SCOPED_CHANGES

M1_EXECUTION_CLOSED=PASS
R_FAST_CONSISTENCY=PASS
CALIBRATION_CLOSED=PASS
HAZARD_CALIBRATION=PASS_ACTIVE_ONLY_EVENT_TIME_LIKELIHOOD
HURDLE_ZERO_CALIBRATION=PASS_D_OB_AND_D_TX
QUANTILE_STATUS=QUANTILE_CALIBRATION_NOT_APPLIED_WITH_CALIBRATION_SPLIT_COVERAGE_DIAGNOSTIC

PRE_FACTUAL_ARCHITECTURE=PASS
FACTUAL_AVAILABILITY_POLICY=UNRESOLVED_HUMAN_DECISION_REQUIRED_ARCHITECTURE_READY_FOR_DECLARED_RULE
STATE_CONTRACTION=PASS_IB_OB_COMPLETED

STATIC_REFERENCE=PASS_TYPED_PUBLICATION
ROUTE=PASS_PUBLISHED_MODEL_FEATURE_PENDING
CARRIER=PASS_PUBLISHED_MODEL_FEATURE_PENDING
AIRCRAFT=PASS_RETAINED_IDENTITY_NO_ORDINAL_ENCODING
SCHEDULE_REFERENCE=PASS_RETAINED_TYPED_REFERENCE
TURNAROUND_REFERENCE=PASS_TRAIN_FROZEN_CONNECTION_AIRPORT_LINEAGE
TAXI_REFERENCE=PASS_TRAIN_FROZEN_LABEL_INPUT_SCENARIO_LINEAGE

M1_STATIC_WIRING=PASS_STATE_AWARE_AND_FAST_ARCHITECTURE

INFORMATION_UPDATE_TEST=PASS

TAIL_STATUS=M1_POSITIVE_TAIL_DECISION_REQUIRED
HORIZON_STATUS=MANUSCRIPT_REQUIREMENT_CLEAR_CODE_LABEL_EXECUTION_CONTRACT_INCOMPLETE

FOCUSED_TESTS=43_PASSED
M1_TESTS=124_PASSED_WITHIN_FULL_SUITE
PRE_TESTS=34_PASSED_WITHIN_FULL_SUITE
INTEGRATION_TESTS=34_PASSED_WITHIN_FULL_SUITE
FULL_TESTS=647_PASSED_1_SKIPPED

FINAL_TEST_ACCESS_COUNT=0
FULL_PAPER_EXPERIMENTS_RUN=FALSE

HUMAN_DECISIONS_REQUIRED=DATA2_FACTUAL_REPLAY_AVAILABILITY_RULE;M1_POSITIVE_TAIL_POLICY;M1_QUANTILE_GRID_FREEZE;ROUTE_CARRIER_NUMERIC_ENCODING;FORMAL_FAST_ARTIFACT;HORIZON_LABEL_EXECUTION_CONTRACT

FINAL_STATUS=PASS_WITH_SCIENTIFIC_GATES_PENDING
```

M1 structural implementation is freeze-ready at this boundary. This is an
engineering closure, not evidence that formal training/calibration, scientific
evaluation, Final Test, or paper experiments have run. The next implementation
stage may begin with M2 seven-component V2 only after a separate instruction.
