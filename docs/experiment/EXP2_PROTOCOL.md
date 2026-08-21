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

POINT is a coherent weighted joint scenario, not a component-wise mean.
MARGINAL preserves primitive marginals and recomputes D_TO samplewise as
D_OB + D_TX. Coarse consequence response contracts must be fit on Train only
and cannot read hidden seven-component values at the coarse decision boundary.

## Metric Hierarchy

Exp2A: CRPS, Brier/calibration/coverage where observations exist, Variogram
Score for dependence, and Top-1/action-family sensitivity.

Exp2B: Top-1 agreement/disagreement with the seven-component representation,
action-family composition, and matched mechanism cases. Complete-reference
model-implied J is an internal consistency diagnostic only, not independent
action-effect evidence.

## Gates

FAST validates transform identity, marginal parity, Train-only coarsening,
split/lineage, and result schema. M4-dependent decision/risk quantities remain
NOT_RUN while response/mapping/tail gates are unresolved.

FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
