# Round 2 M3 Manuscript Alignment

## Claims aligned with the V2 interface

The manuscript may describe M3 as an action-response representation layer between M2 consequence construction and M4 valuation. For each scenario, M2 supplies `C^{0,CU}(s)`, M3 separately evaluates eligibility `I(a)` and a provenance-qualified mechanism `P(a)`, and M3 returns the full `C^{a,CU}(s)` distribution. A00 is the decision-time no-additional-recovery identity.

The manuscript may state that the action library contains the current 23 structural templates, while noting that registry membership alone does not establish state-specific feasibility or effectiveness. It may describe the non-A00 response values as frozen scenario assumptions used for reproducibility, provided it also states that `formal_support_upgrade=false` and that component-wise V2 execution remains gated.

## Claims not supported

The current implementation does not support claims that M3 learns, optimizes, searches, ranks, recommends, estimates causal treatment effects, predicts delay, or predicts money. It also does not support claims that the non-A00 Bernoulli-Beta tiers are empirically calibrated, literature-backed, operationally validated, or scientifically accepted.

No manuscript statement should turn a scenario assumption into `SUPPORTED`, collapse the scenario distribution to one point, describe A00 as “no historical intervention,” or attribute M4 monetary/risk objectives to M3.

## Recommended notation boundary

- `C^{0,CU}_k(s)`: M2-owned baseline component.
- `I(a)`: decision-node eligibility based on facts and required named parameters.
- `P(a)`: action-response rule plus support/provenance; not feasibility.
- `C^{a,CU}_k(s)`: M3-owned action-conditioned component.
- `C^{A00,CU}_k(s)=C^{0,CU}_k(s)`: exact identity.
- Any expectation, variance, tail statistic, monetary mapping, or ranking: downstream M4 operation over the preserved distribution.

## Current scientific wording

The strongest accurate status is: “The M3 V2 engineering interface and A00 identity are validated by contract tests; non-A00 action-response mechanisms are classified but remain scenario-assumption designs pending human approval and component-wise implementation.” This is not a scientific-result claim.

No TeX or manuscript source was edited in this tranche.
