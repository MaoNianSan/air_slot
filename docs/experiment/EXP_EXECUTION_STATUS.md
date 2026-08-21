# Experiment Execution Status

## Current Status

AIR_SLOT_REAL_FAST_BINDING_SUPPLEMENT = REAL_FAST_PARTIAL_SHARED_GATES_REMAIN

| Experiment | CONTRACT_FAST | REAL_DATA_FAST | Current executable evidence |
| --- | --- | --- | --- |
| Exp1 | PASS | PARTIAL | Shared real Data2 cohort binding; state and decision metrics await M1 V2/M4 artifacts |
| Exp2 | PASS | PARTIAL | Canonical representation transforms and shared real cohort binding; representation metrics await M1/M2 artifacts |
| Exp3 | PASS | PARTIAL | Real common replay and state-vintage selection execute on all frozen nodes; action anchor/ranking remains blocked |
| Exp4 | PASS | PARTIAL | Real PRE/replay latency p50/p95/p99 and budgets execute; predictive baselines await frozen M1 V2 artifacts |

`CONTRACT_FAST` is source-free fixture coverage for schema, variants, and
contracts. `REAL_DATA_FAST` uses the frozen Data2 Development pilot cohort:
`COHORT_HASH = sha256:cc224488e1b6fecfd865dcc494b0004af9ca752dc609eb901d46ad88b82edb63`,
five episodes, 69 five-minute decision nodes, selected pre-outcome by
`FIRST_N_ELIGIBLE_BY_STABLE_EPISODE_ID`. All four runners receive the same
`ExperimentContext`; no per-experiment cohort selection occurs.

## Shared Gates

| Gate | Current Status | Effect |
| --- | --- | --- |
| M1 V2 checkpoint/scenarios | `BLOCKED_M1_V2_ARTIFACT_NOT_FROZEN` | No real predictive/state scenario metrics or M2 materialization. Legacy V1 heads are not rebound as V2. |
| M1 positive tail | `UNRESOLVED` | Tail extrapolation, CVaR, and full ancestral tail scenarios remain blocked; it does not invalidate otherwise legal predictive metrics once a V2 artifact exists. |
| M2 seven components | `NOT_RUN_DEPENDS_ON_M1_V2_ARTIFACT` | No zero filling; Exp2B and M3/M4 inputs remain unavailable. |
| M3 A00 | `READY_IDENTITY` | Baseline identity is preserved. |
| M3 non-A00 | `SCENARIO_ASSUMPTION_CONDITIONAL` | May only be interpreted as conditional, non-causal, and non-authoritative. |
| M4 formula | `READY` | Code is available. |
| M4 risk policy | `FROZEN` | Policy is frozen separately from mapping. |
| M4 tail/mapping/ranking | `UNRESOLVED` / `MONETARY_MAPPING_BLOCKED` / `NOT_RUN` | No authoritative residual-risk or monetary ranking; experiment outputs use `CONSTRUCTED_LOSS_UNIT`, never RMB. |

Run commands: `python -m exp.cli smoke-all` remains fixture-only, while
`python -m exp.cli real-fast-all` emits
`REAL_FAST_PARTIAL_SHARED_GATES_REMAIN` until the named artifacts are frozen.
Neither command accesses Final Test or enables paper-full execution.

## Safety

FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
FULL = DEFERRED
