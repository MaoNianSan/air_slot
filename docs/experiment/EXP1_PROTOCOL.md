# Exp1 Protocol

## Question

Why are direct cross-stage information reuse and admissible history needed in
the rolling recovery state?

## Active Variants

| Subexperiment | Variants | Only Changed Factor |
| --- | --- | --- |
| Exp1A | EXP1A_NO_DIRECT_REUSE, EXP1A_FULL | Whether current information remains directly reusable after state/consequence formation |
| Exp1B principal | EXP1B_CURRENT, EXP1B_ADAPTIVE_HISTORY | Legal history available to the same train-frozen state-aware architecture |
| Exp1B sensitivity | EXP1B_FIXED_HISTORY_30 | Fixed 30-minute history; never included in the principal result table without the explicit sensitivity switch |

Both Exp1A variants preserve PRE, M1, M2, M3, M4, the action library, and
support/provenance rules. NO_DIRECT_REUSE keeps minimal actionability,
execution-window, and qualification facts, while blocking hidden-history and
raw-weather rereads.

## Metrics And Claims

Primary outputs are state/representation differences, primitive-target CRPS,
and principal-event Brier/calibration when the train-frozen M1 V2 artifact is
available. Top-1 disagreement and ex-post model-implied residual risk are
secondary downstream diagnostics. The residual-risk unit is
`CONSTRUCTED_LOSS_UNIT` until a complete authoritative mapping freezes; replay
is not an observed causal treatment effect.

Warning/FPR/recall/DecisionWindowGain, context neutralization, and
shared-state efficiency are legacy or appendix-only and are not headline Exp1
evidence.

## Gates

`CONTRACT_FAST` validates the information mask, history isolation,
split/lineage, and result schema without raw data. `REAL_DATA_FAST` binds the
shared Data2 Development cohort but currently leaves M1-state and M4-decision
metrics `NOT_RUN` rather than substituting legacy V1 outputs. FINAL_TEST_ACCESS_COUNT
= 0 and PAPER_FULL_RUN = FALSE.
