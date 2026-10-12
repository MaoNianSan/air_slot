# M4 Priority and Screening

## CURRENT PUBLIC CONTRACT

M4 owns the two Section 3.5 priority representations:

- `DELAY`: common-support conditional successor take-off delay.
- `CONSEQUENCE`: the seven-component CU consequence aggregate
  `S_C = mean(S_F, S_P, S_R)`.

The public service performs node summarization, population construction,
stable ordering, fixed-capacity screening, and paired priority alignment.
The seven components are preserved in native, CU, domain, and aggregate
layers. CU is a frozen constructed comparison unit, not money.

`ScreeningCapacity` means attention or assessment capacity only.
`ScreeningShortlist` is not an action set and does not imply that a selected
object receives an intervention.

## LEGACY / APPENDIX-ONLY IMPLEMENTATION

The former monetary residual-risk evaluator and action-envelope comparison
remain available through explicit modules such as
`model.M4.legacy_service`, `model.M4.residual_risk`, and
`model.M4.m3_action_interface`. They are not imported by the package-level
current service.

## NOT PART OF CURRENT EMPIRICAL MAINLINE

M4 does not calculate monetary residual risk, use VaR/CVaR to select actions,
rank candidate actions, or emit `recommended_action`, `best_action`, or
`optimal_action`. Priority changes the relative recovery-attention ordering
only. The current empirical path is PRE -> M1 -> M2 -> M4; a later extension
may pass a shortlist node to the M3 downstream interface.

For retrospective populations, the caller must provide the complete candidate
rolling records for the declared cohort. M4 cannot prove that an omitted
earlier node did not exist.
