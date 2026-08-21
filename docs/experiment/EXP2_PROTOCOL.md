# Exp2 Protocol

## Question

How much and what structure of information should be retained so that the
recovery state is sufficient without being needlessly expanded?

## Active Variants

| Subexperiment | Variants | Only Changed Factor |
| --- | --- | --- |
| Exp2A | EXP2A_POINT, EXP2A_MARGINAL, EXP2A_JOINT | Uncertainty/dependence representation of one frozen M1 artifact |
| Exp2B | EXP2B_SCALAR, EXP2B_3CHANNEL, EXP2B_7COMP | Consequence resolution of one frozen seven-component M2 artifact |

Exp2 preserves full/adaptive source state, direct-information permissions,
episodes/nodes, action availability, action library, support/provenance gate,
and random seed. It never changes history length, state vintage, refresh
cadence, action membership, or M1/M2/M3/M4 scientific semantics.

POINT is a coherent weighted joint scenario selected by the explicit
`WEIGHTED_JOINT_SCENARIO_MEDOID` rule, never a component-wise mean. MARGINAL
preserves primitive marginals and recomputes D_TO samplewise as D_OB + D_TX.
For non-equal scenario weights the transform is
`BLOCKED_WEIGHTED_TRANSFORM_NOT_IMPLEMENTED`; no approximate shuffle is
reported as marginal preservation. Coarse consequence response contracts must
be fit on Train only and cannot read hidden seven-component values at the
coarse decision boundary.

## Metric Hierarchy

Stage 1, representation evaluation, computes CRPS, applicable Brier,
calibration, coverage, and Variogram Score without invoking M3/M4. Stage 2,
downstream evaluation, alone computes action disagreement, ranking change,
action-family composition, and residual-risk diagnostics. A successful Stage 1
with blocked Stage 2 is reported as `PARTIAL`, not as a failed representation
experiment.

Exp2B: Top-1 agreement/disagreement with the seven-component representation,
action-family composition, and matched mechanism cases. Complete-reference
model-implied J is an internal consistency diagnostic only, not independent
action-effect evidence.

## Gates

`CONTRACT_FAST` validates transform identity, Train-only coarsening,
split/lineage, and result schema. `REAL_DATA_FAST` uses the common Data2
Development cohort and declares the M1/M2 artifact blocker explicitly; it does
not manufacture scenario weights, observations, or M4 outputs. M4-dependent
decision/risk quantities remain NOT_RUN while response/mapping/tail gates are
unresolved.

FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
