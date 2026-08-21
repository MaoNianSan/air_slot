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
