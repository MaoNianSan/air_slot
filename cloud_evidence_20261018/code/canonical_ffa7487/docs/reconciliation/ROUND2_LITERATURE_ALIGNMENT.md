# Round 2 Literature Alignment

Scope: manuscript Section 2, PDF pages 2–5. No citations are added in this tranche.

## Existing positioning

Section 2 already distinguishes component-level recovery optimization, integrated recovery, cross-stage information sharing, history-dependent state representation, probabilistic consequence representation, and action evaluation. Its final gap statement correctly argues that richer prediction or broader optimization does not by itself guarantee a consistent decision process.

Overall status: `PARTIALLY_ALIGNED`.

## Required category-level gap audit

| Literature category | Present argument | Missing argument required by the current framework | Status |
|---|---|---|---|
| Disruption prediction | Prediction provides richer and more accurate operational information. | Accuracy alone does not define admissible decision-time information, a downstream state contract, consequence semantics, or what happens when support is missing. | `MISSING_EXPLANATION` |
| Recovery optimization | Component and integrated models enlarge the operational scope and action space. | Optimization assumes state, response, feasibility, and objective semantics. It does not by itself establish that upstream information is consistently represented or that response parameters are evidence-supported. | `PARTIALLY_ALIGNED` |
| Cost/risk evaluation | Consequences may be evaluated with cost, risk, or service objectives. | Native operational quantities, cross-component CU, monetary systems, and residual-risk aggregation must be separated. Monetary conclusions are system- and calibration-dependent. | `MISSING_EXPLANATION` |

## Missing literature arguments to identify for the next writing phase

- Prediction-to-decision gap: why calibrated prediction still requires a typed consequence interface rather than direct conversion to a recommendation.
- State sufficiency and information provenance: why history, current observations, and static references have different admissibility and representation roles.
- Consequence representation versus valuation: why passenger minutes, event counts, operating-resource exposure, CU normalization, and money are not interchangeable “costs.”
- Action response versus optimization: why representing an action-conditioned consequence is logically prior to ranking or selecting an action.
- Support and abstention: why structural action availability or numerical scenario evaluability does not imply empirical effectiveness.
- Residual risk: why risk after action response must be distinguished from initial disruption impact.
- Generalization boundary: what cross-data or cross-system portability would require when monetary mappings and action-response evidence change.

## Citation and rhetoric defects

- Multiple citations in the component and integrated recovery discussion render as literal `?` on PDF pages 2–4. The affected claims cannot be considered publication-ready until bibliography resolution is repaired.
- Repeated “substantially improved” statements need claim-specific citation support and a bounded object of improvement.
- “A broader action space does not necessarily guarantee better decisions” is a plausible gap statement but needs either supporting literature or explicitly conceptual wording.
- The literature review should not imply that this study proves global consistency or optimality; it proposes and implements interface discipline under stated support constraints.

No bibliography entry or citation key was changed.
