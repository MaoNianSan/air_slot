# AIR SLOT --- Exp1--Exp4 Updated Experimental Protocol (Information Sufficiency Revision)

## 1. Updated experimental philosophy

The revised experimental section is organized around one central
question:

> How should operational information be preserved, compressed, and
> propagated through a rolling airline recovery decision chain?

The purpose is not to show that a more complex model is always better.

The purpose is to demonstrate:

1.  insufficient information causes decision distortion;
2.  structured information preserves decision-relevant uncertainty;
3.  excessive information may introduce redundancy without additional
    decision value;
4.  the complete chain remains operationally adequate.

The final experiment logic is:

    Exp1 — Necessity of information sharing
            |
            v
    Exp2 — Information sufficiency and representation resolution
            |
            v
    Exp3 — Temporal propagation of retained information
            |
            v
    Exp4 — Complete-system operational adequacy

------------------------------------------------------------------------

# Exp1 --- Necessity of Information Sharing and State Dependence

## Research question

Why must information be shared across recovery stages, and why must the
current state retain admissible historical information?

Exp1 does not evaluate representation granularity.

Exp1 only verifies that removing essential information pathways damages
decision quality.

------------------------------------------------------------------------

# Exp1A --- Direct information reuse

## Question

After a history-conditioned state and consequence representation are
constructed:

> Is the mediated state sufficient, or does downstream decision
> formation still require direct access to current decision-relevant
> information?

## Variants

  -----------------------------------------------------------------------
  Variant                             Description
  ----------------------------------- -----------------------------------
  NO_DIRECT_REUSE                     downstream receives only declared
                                      mediated state/consequence
                                      information

  FULL                                complete information pathway
  -----------------------------------------------------------------------

Both variants must keep:

-   same model chain;
-   same action library;
-   same consequence model;
-   same support/provenance rules.

Only information access is changed.

## Metrics

Prediction:

-   CRPS;
-   calibration.

Decision:

-   selected action;
-   Top-1 disagreement.

Outcome:

-   common replay residual consequence.

Interpretation:

Evidence supports:

> direct information reuse is decision-relevant.

It does not support:

> all raw information should always be passed downstream.

------------------------------------------------------------------------

# Exp1B --- History dependence

## Question

Is the latest snapshot sufficient, or does the recovery state need
admissible history?

## Variants

  Variant            Description
  ------------------ ----------------------------------
  CURRENT            current admissible snapshot only
  FIXED_HISTORY      fixed historical window
  ADAPTIVE_HISTORY   complete admissible history

Requirements:

-   same architecture;
-   same output heads;
-   same capacity;
-   only history availability changes.

Do not use FAST vs STATE_AWARE here because that mixes architecture and
history effects.

## Metrics

-   CRPS;
-   Brier score;
-   calibration;
-   action disagreement;
-   replay consequence.

------------------------------------------------------------------------

# Exp2 --- Information Sufficiency and Representation Resolution

## Research question

How much information should be retained?

The key hypothesis:

    too little information -> under-representation

    structured information -> decision-relevant representation

    too much information -> redundancy/noise

Exp2 is the main experiment for validating why the proposed
representation is "just enough".

------------------------------------------------------------------------

# Exp2A --- Uncertainty representation resolution

## Question

How much probabilistic structure is required?

## Variants

  Variant     Information level
  ----------- ----------------------------------
  COLLAPSED   point estimate / simple summary
  MARGINAL    individual distributions
  JOINT       coherent joint scenarios
  EXPANDED    additional uncertainty variables

------------------------------------------------------------------------

## Expected interpretation

COLLAPSED:

-   loses uncertainty;
-   unstable decisions.

MARGINAL:

-   preserves uncertainty;
-   loses dependency.

JOINT:

-   preserves decision-relevant dependency.

EXPANDED:

-   tests whether additional information produces real decision value.

------------------------------------------------------------------------

## Metrics

### Prediction

-   CRPS;
-   Brier score;
-   calibration;
-   coverage.

### Decision

-   Top-1 action disagreement;
-   action-family change.

### Outcome

Common replay:

    variant selects action
            |
            v
    same frozen evaluator
            |
            v
    decision consequence

Do not use a representation's own objective as proof.

------------------------------------------------------------------------

# Exp2B --- Consequence representation resolution

## Question

How much consequence decomposition is necessary?

## Variants

  Variant          Representation
  ---------------- ------------------------------------
  SCALAR           total consequence only
  CHANNEL          flight/passenger/resource channels
  COMPONENT        mechanism-level decomposition
  OVER_COMPONENT   excessive decomposition diagnostic

------------------------------------------------------------------------

## Expected interpretation

Scalar:

-   simple;
-   loses mechanisms.

Component:

-   aligns consequence mechanisms with recovery actions.

Over-component:

-   tests whether additional decomposition creates instability.

------------------------------------------------------------------------

# Exp3 --- Information Evolution and Temporal Propagation

## Research question

Once the appropriate information representation exists:

> How should it evolve when new information arrives?

Exp3 does not claim rolling recovery itself is novel.

It evaluates information propagation within an already rolling
environment.

------------------------------------------------------------------------

# Exp3A --- Recommendation refresh

## Question

Does a recommendation remain valid as information evolves?

## Variants

  Variant    Description
  ---------- --------------------------------------
  ONE_SHOT   recommendation fixed at initial time
  ROLLING    recommendation refreshed

Metrics:

-   recommendation executability;
-   replay consequence;
-   recommendation change.

------------------------------------------------------------------------

# Exp3B --- State synchronization

## Question

Should downstream decisions use a state synchronized with current
decision time?

## Variants

  Variant
  ---------
  SYNC
  LAG_5
  LAG_10

Metrics:

-   decision disagreement;
-   replay consequence;
-   operational strata analysis.

------------------------------------------------------------------------

# Exp4 --- Complete-System Operational Adequacy

## Research question

Does the complete frozen decision chain achieve sufficient predictive,
operational, and computational quality?

Exp4 does not introduce new methodological claims.

------------------------------------------------------------------------

# Exp4A --- Predictive adequacy

## Question

Is the final state-aware model empirically competitive?

Compare:

-   Historical baseline;
-   FAST model;
-   Random Forest;
-   STATE_AWARE_FULL.

Across:

-   0--480 minute lead-time window.

Metrics:

-   MAE;
-   CRPS;
-   calibration.

------------------------------------------------------------------------

# Exp4B --- Decision-output validity

## Question

Are generated recommendations operationally admissible?

Audit:

-   availability;
-   structural feasibility;
-   factual consistency;
-   evidence support;
-   leakage.

LLM audit:

-   auxiliary only;
-   never ground truth.

------------------------------------------------------------------------

# Exp4C --- Evidence-environment portability

## Question

Does the methodology remain useful under different evidence
environments?

Primary comparison:

Within each dataset:

    FULL - strong baseline

not raw Data1 vs Data2 error difference.

Report:

-   predictive difficulty;
-   support limitation;
-   method advantage pattern.

------------------------------------------------------------------------

# Exp4D --- Computational adequacy

## Question

Can the full chain operate within rolling decision requirements?

Metrics:

-   p50 runtime;
-   p95 runtime;
-   p99 runtime;
-   stage latency;
-   5-minute rolling budget.

Shared-state reuse:

Appendix diagnostic only.

Requirement:

-   same outputs;
-   same rankings;
-   same decisions.

Only runtime improvement is measured.

------------------------------------------------------------------------

# 2. Final evidence hierarchy

Strongest evidence:

1.  observed prediction outcomes;
2.  hard operational validity rules;
3.  controlled representation/process ablations;
4.  replay under frozen action-response;
5.  internal diagnostic objectives;
6.  auxiliary LLM audit.

------------------------------------------------------------------------

# 3. Final journal positioning

## TRE

Main contribution:

Decision-relevant information representation for rolling recovery.

Key message:

> More information is not always better; structured information is
> required.

## JORS

Main contribution:

Operational decision methodology with controlled stochastic
representation.

## Omega

Potential broader insight:

> Decision systems should optimize information sufficiency, not
> information volume.

------------------------------------------------------------------------

# 4. Implementation rule for Codex

All Exp1--Exp4 implementations must:

-   freeze the scientific model contract;
-   modify only declared experimental factors;
-   maintain identical data splits;
-   record transformation provenance;
-   avoid test-driven representation selection;
-   use common evaluation protocols.

The final experimental story is:

    Why information?
            |
    How much information?
            |
    How does information evolve?
            |
    Does the complete chain work?
