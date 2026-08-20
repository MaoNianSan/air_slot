# AIR SLOT --- Information Sufficiency and Representation Resolution Experimental Framework

## 1. Purpose

This document defines the revised experimental logic after introducing
the concept of **information sufficiency**.

The central question is:

> In a rolling airline recovery decision chain, how much information
> should be preserved before additional information becomes redundant,
> unstable, or decision-irrelevant?

The objective is not to prove that "more complex models are better", but
to verify that the selected representation preserves **decision-relevant
information** while avoiding unnecessary representation expansion.

The current M1 design provides: - decision-time operational
information; - history-conditioned state through lightweight GRU; -
probabilistic outputs for predecessor and successor operations; - joint
scenario representation for downstream consequence evaluation.

The M1 contract remains: - inputs: current state, predecessor flight,
successor schedule/turnaround information, airport weather and flow
conditions; - outputs: predecessor A00 in-block distribution, successor
off-block delay distribution, taxi delay distribution, and derived total
takeoff delay distribution. The total takeoff delay is maintained
samplewise as the sum of off-block and taxi components.
fileciteturn1file0

------------------------------------------------------------------------

# 2. Revised Experiment Logic

The paper experiments should answer four sequential questions:

    Exp1 — Necessity
    Why must cross-stage information sharing and state dependence exist?

    Exp2 — Representation sufficiency
    How much information should be retained?

    Exp3 — Dynamic process
    How should the retained information evolve during rolling decisions?

    Exp4 — Adequacy
    Is the complete decision chain operationally credible?

The key revision is that Exp2 is expanded from a pure representation
comparison into an **information resolution analysis**.

------------------------------------------------------------------------

# 3. Exp2 Main Scientific Claim

## Research question

> Is the selected information representation sufficiently rich for
> recovery decisions, but not unnecessarily expanded with redundant
> information?

The hypothesis is not:

    more information always improves decisions

but:

    too little information causes under-representation;
    structured information improves decision consistency;
    excessive information may add redundancy without improving decisions.

------------------------------------------------------------------------

# 4. Exp2A --- Uncertainty Representation Resolution

## Scientific question

> How much uncertainty structure should be retained in the operating
> state?

Variants:

  Variant     Representation
  ----------- ---------------------------------------------------
  COLLAPSED   point estimate / scalar uncertainty summary
  MARGINAL    individual distributions without dependence
  JOINT       aligned joint scenario representation
  EXPANDED    additional uncertainty variables directly exposed

------------------------------------------------------------------------

## 4.1 COLLAPSED

Purpose:

Test insufficient uncertainty representation.

Representation:

-   expected delay;
-   median delay;
-   threshold probability only.

Expected limitation:

-   loses tail behavior;
-   loses scenario variability;
-   cannot distinguish similar means with different uncertainty
    structures.

------------------------------------------------------------------------

## 4.2 MARGINAL

Purpose:

Test whether preserving individual uncertainty is sufficient.

Preserves:

-   distribution of each stochastic quantity.

Removes:

-   dependency structure between quantities.

Example:

    D_OB
    D_TX
    D_TO

have correct marginal distributions but lose aligned scenario identity.

------------------------------------------------------------------------

## 4.3 JOINT

Formal model representation.

Preserves:

-   scenario identity;
-   dependence;
-   tail association;
-   samplewise derived quantities.

This is the expected sufficient representation.

------------------------------------------------------------------------

## 4.4 EXPANDED

Purpose:

Test information redundancy.

Instead of compressing information into decision-relevant state
variables, expose additional uncertainty dimensions directly.

Example:

-   raw weather uncertainty;
-   trajectory uncertainty;
-   intermediate operational variables;
-   auxiliary evidence variables.

The objective is not to create a better predictor, but to test whether
additional variables improve downstream decisions.

------------------------------------------------------------------------

# 5. Exp2A Evaluation

Evaluation must contain three layers.

## 5.1 Predictive layer

Measures information preservation.

Metrics:

-   CRPS;
-   calibration;
-   prediction interval coverage;
-   Brier score.

------------------------------------------------------------------------

## 5.2 Decision layer

Measures whether representations change recovery choices.

Metrics:

-   selected Top-1 action;
-   action disagreement rate;
-   action-family change.

------------------------------------------------------------------------

## 5.3 Outcome layer

All selected actions are evaluated using the same frozen replay basis.

Procedure:

    representation selects action
            ↓
    common replay evaluator
            ↓
    J_post(action)

The objective is not to use the representation's own objective as proof.

------------------------------------------------------------------------

# 6. Expected Interpretation Pattern

The desired scientific pattern is:

  -----------------------------------------------------------------------
  Representation          Prediction              Decision
  ----------------------- ----------------------- -----------------------
  COLLAPSED               weak                    unstable

  MARGINAL                improved                limited

  JOINT                   strong                  consistent

  EXPANDED                similar/improved        limited additional
                          prediction              decision value
  -----------------------------------------------------------------------

Possible conclusion:

> Preserving decision-relevant uncertainty structure is more important
> than maximizing information volume.

------------------------------------------------------------------------

# 7. Exp2B --- Consequence Representation Resolution

The same logic applies to M2.

Question:

> How much consequence decomposition is necessary before action
> evaluation?

Variants:

  Variant          Consequence representation
  ---------------- ----------------------------------------------------
  SCALAR           total recovery consequence
  CHANNEL          flight/passenger/resource channels
  COMPONENT        seven-component hierarchy
  OVER-COMPONENT   excessive fine decomposition (optional diagnostic)

------------------------------------------------------------------------

## 7.1 SCALAR

Information:

    total loss only

Limitation:

-   different operational mechanisms may have identical total costs.

------------------------------------------------------------------------

## 7.2 CHANNEL

Preserves:

-   flight consequence;
-   passenger consequence;
-   resource consequence.

------------------------------------------------------------------------

## 7.3 COMPONENT

Formal representation:

    Flight:
    - continuity
    - execution
    - propagation

    Passenger:
    - time
    - itinerary
    - service

    Resource:
    - operating

Purpose:

Maintain mechanism-action alignment.

------------------------------------------------------------------------

## 7.4 OVER-COMPONENT

Optional diagnostic.

Question:

Does unlimited decomposition improve decisions?

Possible issue:

-   excessive parameters;
-   unstable ranking;
-   difficult interpretation.

------------------------------------------------------------------------

# 8. Evaluation Principle Across Modules

The same framework applies:

## M1

Information resolution:

    point
    → marginal
    → joint
    → expanded

## M2

Consequence resolution:

    scalar
    → channel
    → component
    → over-component

## M3

Action resolution:

Potential future diagnostic only.

Avoid making action-space richness the main experiment because it
overlaps with existing recovery optimization literature.

------------------------------------------------------------------------

# 9. Metrics Required

Do not create composite scores.

Use recognized metrics.

## Prediction

-   MAE;
-   CRPS;
-   Brier score;
-   calibration.

## Decision

-   selected action;
-   Top-1 agreement;
-   action-family distribution.

## Outcome

-   common replay residual risk;
-   common replay recovery consequence.

------------------------------------------------------------------------

# 10. Journal Positioning

## Transportation Research Part E

Main contribution:

    decision-relevant information representation
    rather than prediction accuracy alone

The key message:

> More operational information is not automatically better unless its
> structure matches the decision process.

------------------------------------------------------------------------

## JORS

Emphasize:

-   representation design;
-   stochastic decision modeling;
-   information preservation;
-   computational practicality.

------------------------------------------------------------------------

## Omega

Elevate managerial insight:

> Decision systems should preserve sufficient uncertainty and
> consequence mechanisms while filtering redundant information.

------------------------------------------------------------------------

# 11. Implementation Guidance for Codex

Each experiment implementation should:

1.  freeze the formal model;
2.  create representation transformations only;
3.  avoid retraining weaker baselines;
4.  keep identical data splits;
5.  use common replay evaluation;
6.  record transformation provenance;
7.  prohibit test-driven selection.

------------------------------------------------------------------------

# 12. Final Experimental Narrative

The final paper logic becomes:

    Observed information
            |
            v
    Information sufficiency
            |
            v
    History-conditioned state
            |
            v
    Mechanism-preserving consequence
            |
            v
    Recovery intervention
            |
            v
    Operationally adequate decision chain

The experiments therefore justify not only that the framework works, but
why this specific information structure is necessary.
