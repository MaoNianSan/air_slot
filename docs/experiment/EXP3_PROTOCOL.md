# Exp3 Protocol

## Question

Given a fixed rolling recovery chain, how should newly admissible information
and a time-aligned state be propagated?

## Active Variants

| Subexperiment | Variants | Only Changed Factor |
| --- | --- | --- |
| Exp3A | EXP3A_ONE_SHOT, EXP3A_ROLLING | Whether a valid first recommendation is refreshed |
| Exp3B | EXP3B_SYNC, EXP3B_STATE_LAG_5, EXP3B_STATE_LAG_10 | State vintage supplied to the current downstream comparison |

The anchor is the first node with at least two formally comparable actions,
including at least one non-A00 action. Exp3B fixes current direct information,
current action set, support/provenance, consequence function, and evaluator;
only state vintage changes.

## Metrics And Claims

Exp3A headlines recommendation executability/comparability as it ages.
Common-support ex-post model-implied replay, action agreement, flight-delay,
and passenger-delay outputs are reported only when the underlying frozen
interfaces support them. Exp3B compares synchronized and lagged-state choices
on the same current action domain.

Exp3 does not claim that rolling recovery is novel, that replay is a causal
saving, or that Exp4B issuance-time admissibility is an aging result.

## Gates

FAST validates temporal variant identity and guards. Formal multi-action,
M4, and replay outputs remain NOT_RUN until their shared contracts freeze.
FINAL_TEST_ACCESS_COUNT = 0 and PAPER_FULL_RUN = FALSE.
