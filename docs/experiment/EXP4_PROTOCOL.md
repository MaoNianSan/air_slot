# Exp4 Protocol

## Question

Does the complete frozen decision chain achieve adequate predictive,
operational, portability, and computational performance?

## Active Protocols

| Area | Protocol |
| --- | --- |
| Predictive adequacy | EXP4A_PREDICTIVE_ADEQUACY |
| Decision-output validity | EXP4B_DECISION_OUTPUT_VALIDITY |
| Auxiliary LLM audit | EXP4B_LLM_AUXILIARY_AUDIT |
| Evidence-environment portability | EXP4C_DATA1_DATA2_PORTABILITY |
| End-to-end runtime | EXP4D_END_TO_END_RUNTIME |
| Appendix parity diagnostic | EXP4D_SHARED_STATE, EXP4D_RECOMPUTED_STATE |

## Metrics And Claims

Exp4A uses MAE and CRPS across the frozen evaluation lead-time grid
`0, 30, 60, 120, 180, 240, 300, 360, 420, 480`, with Historical, LightGBM
FAST, Random Forest, and state-aware Full paths. These are distinct from the
M1 model-horizon contract `0, 15, 60`. Exp4B
audits formal availability, execution/structural feasibility, factual
consistency, evidence support, and leakage. The LLM audit is auxiliary only.

Exp4C interprets portability through the within-environment FULL - LIGHTGBM
pattern and explicit support degradation, never raw Data1-vs-Data2 error
differences. Exp4D reports E2E p50/p95/p99 and 60/120/300 second budgets;
the 300-second p95 threshold is the rolling hard budget. Shared-state reuse is
appendix-only and requires output parity before runtime is interpretable.

## Gates

`CONTRACT_FAST` is fixture-only. `REAL_DATA_FAST` measures real Data2 PRE/replay
binding latency and records p50/p95/p99 plus 60/120/300-second budgets; it does
not mislabel this partial timing as complete-chain latency while predictive
artifacts remain unavailable. No Final Test, paper-full execution, parameter
selection, or scientific mapping is enabled by this protocol.

## Development Per-Node Records (2026-08-25)

`exp/exp4/per_node_records.py` materializes per-node prediction records for
the four baselines at paper-statistic granularity
(`artifacts/experiment/exp4/exp4_per_node_records_20260825/`).  Schema:
`episode_id | decision_node_id | method | target | observed_minutes |
point_prediction | absolute_error | crps | crps_supported |
lead_time_minutes | lead_time_source | lead_time_bin_minutes` (the `method`
column is a documented extension of the instructed schema so HISTORICAL /
LIGHTGBM / RANDOM_FOREST / STATE_AWARE_H32 can be distinguished).

Lead-time rule follows Exp1B: T_IB_A00 = realized remaining minutes; D_OB =
planned schedule horizon; D_TX = NA (no planned wheels-off reference); NA is
never interpolated.  Lead bins use the frozen grid
`0, 30, 60, 120, 180, 240, 300, 360, 420, 480` with floor-to-edge semantics.
CRPS: ML baselines use sample CRPS for all targets; STATE_AWARE_H32 uses the
frozen M1 finite-support T_IB scope only (D_OB/D_TX are not saved by M1:
`crps=None, crps_supported=False`).  Grid cells are summarized with
episode-cluster bootstrap (episode is the resampling unit, 2000 replicates,
seed 20260825), output as `EXP4_LEAD_TIME_GRID_DEVELOPMENT_ONLY.csv`.
