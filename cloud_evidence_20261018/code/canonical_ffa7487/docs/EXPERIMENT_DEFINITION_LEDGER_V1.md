# Air Slot Experiment Definition Ledger

**Version:** V1  
**Date:** 2026-09-06  
**Scope:** Exp1-Exp4 Development programming  
**Status:** Working ledger; unresolved scientific choices are blocking gates.

This ledger separates approved scientific definitions from implementation
status and decisions that still require human approval. Code must not infer an
unresolved value from historical results, convenience, or sample size.

## Approved Definitions

| Topic | Current definition | Owner | Status |
|---|---|---|---|
| Paper positioning | A is the main empirical question; B is methodological support | Scientific design | APPROVED |
| Exp1 | Rolling-state empirical adequacy | Exp1 | APPROVED |
| Exp2 | Delay-priority divergence, component informativeness, similar-delay heterogeneity | Exp2 | APPROVED |
| Exp3 | Operating-stage variation in agreement and heterogeneity | Exp3 | APPROVED |
| Exp4 | Retrospective fixed-budget recovery triage benchmark | Exp4 | APPROVED |
| Delay object | Decision-time weighted successor total take-off delay, `D_TO` | Shared | APPROVED |
| Node consequence | Scenario-weighted node-level consequence | Shared | APPROVED |
| Consequence ontology | Seven frozen M2 components | M2 | APPROVED |
| Domain aggregation | F/P/R domain-balanced aggregate | Shared | APPROVED |
| Primary Exp2 metric | Kendall tau-b between delay and aggregate consequence score | Exp2 | APPROVED |
| Exp3 metrics | Stage-specific Kendall tau-b and similar-delay heterogeneity | Exp3 | APPROVED |
| Exp4 interpretation | Screening attention reallocation, not action optimization or realized savings | Exp4 | APPROVED |
| Analysis dependence | Episode/node analysis with episode-level dependence preserved | Shared | APPROVED |
| Final Test | Not authorized in this programming phase | Project gate | APPROVED |

## Unresolved Blocking Definitions

| Topic | Source | Current status | Decision required | Blocked experiments |
|---|---|---|---|---|
| Primary support estimand | Master programming spec U1 | UNRESOLVED | Choose `FULL` or `COMMON_SUPPORT_CONDITIONAL_090` as primary; retain other approved sensitivities if applicable | Exp1-Exp4 formal |
| Exp2 component/domain population | Master programming spec I1 | APPROVED_FOR_IMPLEMENTATION | Separate finite/support-applicable sample per component/domain; confirm any minimum sample threshold | Exp2 |
| Exp4 budget comparison set | Master programming spec U2 | UNRESOLVED | Choose stage-stratified, time-window, calendar-day, or another explicitly defined comparison cohort | Exp4 |
| Exp4 unsupported canonical event | Master programming spec U2 | UNRESOLVED | Decide whether unsupported first event is excluded, yields typed abstention, or blocks the cohort; later supported event must not be silently substituted | Exp4 |
| Exp4 K rounding | Master programming spec | UNRESOLVED | Freeze `ceil`, `floor`, or another deterministic rule | Exp4 |
| Exp4 consensus threshold `m` | Master programming spec U4 | UNRESOLVED | Freeze the number of priority specifications required for robust membership | Exp4 |
| Passenger threshold sensitivity | Teacher revision and master spec U3 | UNRESOLVED | Mark `INCLUDED`, `APPENDIX_ONLY`, `DEFERRED_WITH_JUSTIFICATION`, or `OUT_OF_SCOPE` | Exp1-Exp4 reporting |
| Support/filter ordering | Master programming spec U1/U5 | UNRESOLVED | Freeze whether canonical events/cohorts are formed before or after support eligibility filtering | Exp2-Exp4 |
| Canonical stage labels | Master programming spec | APPROVED_FOR_IMPLEMENTATION | Use shared `OperationalStage` labels; no outcome-derived relabelling | Exp2-Exp4 |

## Implementation Rules

1. `UNRESOLVED` values must be represented in machine-readable metadata.
2. A formal runner requiring an unresolved value must return typed `BLOCKED`.
3. A smoke runner may use an explicit diagnostic profile, but must label it
   `NON_PAPER_DIAGNOSTIC` and must not create protocol-freeze evidence.
4. Development results cannot change this ledger automatically.
5. Final Test cannot be used to resolve any ledger item.
6. Historical manuscript numbers are inherited evidence only, never acceptance
   targets.

## Current Work Packages

```text
W0 = this ledger
W1 = formal shared Development input package
W2 = shared support/priority analytical views
W3 = Exp1 and Exp2 integration
W4 = Exp3 and Exp4 implementation
W5 = Development review package
```
