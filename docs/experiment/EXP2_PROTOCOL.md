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

## G2 Freeze Nodes (2026-08-25, human-approved)

- **F1 Exp2A POINT coordinates**: the weighted joint scenario medoid uses only
  the manuscript primitive triple `(R_IB, D_OB, D_TX)`; `R_IB` is read from the
  frozen scenario target `T_IB_A00` (mapping in
  `exp/workflows/m1_v2_current_stage_scenario_envelope.py`).  `D_TO` is a
  derived identity check only (`D_TO = D_OB + D_TX`) and never enters the
  medoid distance.  Ties break by scenario order; the selected scenario is
  copied as a unit-weight degenerate representation (S=1) with lineage and
  field sources preserved.  MARGINAL permutes the three primitives
  independently within weight strata (D_OB shift 0, D_TX shift 1, T_IB_A00
  shift 2) and recomputes `D_TO` samplewise.
- **F2 partial-q series**: not implemented.  The manuscript defines no
  partial-q (0.25/0.50/0.75/1.00) dependency-disruption series; it is neither
  in the main text nor in an appendix.  Recorded as "partial-q 未采用（原稿未定义）"
  in `docs/HUMAN_DECISION_LOG.md`.
- **F5 G2-M4 monetary reporting**: the paper reporting system is the
  constructed-EUR reference-basis five-component aggregate
  `(F_cont, F_exec, F_prop, P_time, R_oper)` with BASE principal and
  LOW/HIGH = 0.5x/2.0x sensitivity; status
  `ASSUMPTION_GROUNDED/REFERENCE_BASED`.  `P_itin`/`P_serv` stay ABSTAIN
  (event counts only, `monetary=NOT_ANCHORED`); no fabricated RMB `beta_k^m`
  values.
- **F6 G2 positive tail**: `alpha = 0.90`, empirical weighted VaR/CVaR over the
  frozen S=250 aligned ensemble; `OVERFLOW_TAIL` retains raw values (no clamp,
  truncation, extrapolation, or zero-fill).  `model/M4/residual_risk.py` is
  already compliant; documentation only, no model change.

## Gates

`CONTRACT_FAST` validates transform identity, Train-only coarsening,
split/lineage, and result schema. `REAL_DATA_FAST` uses the common Data2
Development cohort and declares the M1/M2 artifact blocker explicitly; it does
not manufacture scenario weights, observations, or M4 outputs. M4-dependent
decision/risk quantities remain NOT_RUN while response/mapping/tail gates are
unresolved.

FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
