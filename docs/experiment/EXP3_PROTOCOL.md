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
including at least one non-A00 action. If no such node is bound, ONE_SHOT is
`BLOCKED_ANCHOR_ACTION_COVERAGE`; it never falls back to the first episode
node. Exp3B fixes current direct information, current action set,
support/provenance, consequence function, and evaluator; only state vintage
changes. LAG_5 and LAG_10 select only prior frozen state identities and do not
read the current state.

## Metrics And Claims

Exp3A headlines recommendation executability/comparability as it ages.
Common-support ex-post model-implied replay, action agreement, flight-delay,
and passenger-delay outputs are reported only when the underlying frozen
interfaces support them. Exp3B compares synchronized and lagged-state choices
on the same current action domain.

Exp3 does not claim that rolling recovery is novel, that replay is a causal
saving, or that Exp4B issuance-time admissibility is an aging result.

## G2 Freeze Node F3: State Vintage (2026-08-25, human-approved)

`delta in {0, 5, 10}` minutes.  `S_{t-delta}` is the frozen state identity of
the decision node whose `decision_time` is exactly `t - delta` (exact vintage
match; no nearest-past selection); it is never re-evaluated, interpolated, or
re-read from the current state.  A node without a legal vintage is
typed-excluded with `EXP3B_VINTAGE_NOT_AVAILABLE` and never falls back to the
most recent or current state.  Lags 15/20/30 are forbidden.  `E_t`, the action
set, consequences, response, and `J` are fixed.

## Gates

`CONTRACT_FAST` validates temporal variant identity and guards. `REAL_DATA_FAST`
executes `exp.common.replay` against every node in the common Data2 Development
cohort and produces state-vintage coverage diagnostics. Formal multi-action
and M4 ranking remain blocked by the shared M1/M2/M4 assets. FINAL_TEST_ACCESS_COUNT
= 0 and PAPER_FULL_RUN = FALSE.

## G2 Freeze Node F4/F5: Valuation-Only Sensitivity (2026-08-25, human-approved)

F4 freezes the 22 declared non-A00 scenario-response parameters; F5 restricts
the LOW/BASE/HIGH bands to the frozen five-anchor monetary coefficients only
(`registries/m4_eur_mapping_assumption_grounded_v1.json`, EUR 0.5x/1.0x/2.0x
relative to BASE).  The valuation-only materialization
(`exp/exp3/valuation_only.py`) therefore fixes response parameters at the
frozen declared BASE values for every band; no response-only perturbation is
implemented (`EXP3_RESPONSE_ONLY = NOT_AUTHORIZED_PER_F4`).  Every row is
`ASSUMPTION_GROUNDED`, never authoritative, and never a causal claim.
Records: `artifacts/experiment/exp3/exp3_valuation_only_sensitivity_20260825/`
(`EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet`), one row per
node x band x action envelope with five-anchor consequence/monetary
expectations and conditional residual-risk statistics, plus a manifest with
input hashes, all-zero safety, `paper_result=false`, and a BASE-band parity
check against the existing full-development action-risk artifact.
