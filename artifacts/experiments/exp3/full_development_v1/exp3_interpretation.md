# EXP3 interpretation (Development-only)

## Claim scope
CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL

## Development-only interpretation
Exp3 evaluates the conditional 5-anchor constructed-EUR diagnostic on the frozen Data2 Development cohort (128 episodes, 1769 nodes, 23 actions, 250 scenarios per node). The main table reports finite-support coverage, top-1 response agreement across sensitivity bands, ranking invariance under a common positive scale, and the per-action conditional-risk mean. The complete seven-component monetary ranking and all ablation variants stay NOT_RUN/DEFERRED_OPTIONAL and occupy no main-table row; their reasons are preserved in the metrics CSV and summary.

## Boundary statement
- formal_authoritative_ranking stays NOT_RUN at the human monetary-anchor gate.
- Exp3 variants/ablations (MODULE_REMOVAL_*, ROLLING, ONE_SHOT, SYNC, LAG_*) are DEFERRED_OPTIONAL by user decision 2026-08-24 and are not in the paper.
- constructed monetary scale, not empirical cost; ranking is not optimal/not regret; P_itinerary/P_service are event counts only (monetary NOT_ANCHORED).
- Per-action conditional risk detail lives in EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet.

## Omega managerial insight
The conditional diagnostic is stable under a common positive scale with high finite-support coverage, but operational action value requires the frozen seven-component monetary anchors.

> Development evidence only. NOT_RUN/BLOCKED/ABSTAIN metrics carry their
> reason text; no zero-fill, no silent renormalization, no causal claim,
> no authoritative ranking.
