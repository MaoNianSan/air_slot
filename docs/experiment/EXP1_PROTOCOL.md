# Exp1 Protocol

## Question

Why are direct cross-stage information reuse and admissible history needed in
the rolling recovery state?

## Active Variants

| Subexperiment | Variants | Only Changed Factor |
| --- | --- | --- |
| Exp1A | EXP1A_NO_DIRECT_REUSE, EXP1A_FULL | Whether current information remains directly reusable after state/consequence formation |
| Exp1B | EXP1B_CURRENT, EXP1B_FIXED_HISTORY_30, EXP1B_ADAPTIVE_HISTORY | Legal history available to the same state-aware architecture |

Both Exp1A variants preserve PRE, M1, M2, M3, M4, the action library, and
support/provenance rules. NO_DIRECT_REUSE keeps minimal actionability,
execution-window, and qualification facts, while blocking hidden-history and
raw-weather rereads.

## Metrics And Claims

Primary outputs are selected Top-1 action/disagreement, primitive-target CRPS,
principal-event Brier/calibration, and ex-post model-implied residual-risk
replay when the shared M4/replay gates are available. Replay is not an observed
causal treatment effect.

Warning/FPR/recall/DecisionWindowGain, context neutralization, and
shared-state efficiency are legacy or appendix-only and are not headline Exp1
evidence.

## Gates

Current FAST validates the information mask, history isolation, split/lineage,
and result schema without raw data. FINAL_TEST_ACCESS_COUNT = 0 and
PAPER_FULL_RUN = FALSE.
