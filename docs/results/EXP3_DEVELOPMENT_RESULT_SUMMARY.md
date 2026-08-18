# Exp3 Development Result Summary

## Status

- `DEVELOPMENT_ONLY = TRUE`
- `TEMPORARY_REPORT = TRUE`
- `NOT_FINAL_PAPER_RESULT = TRUE`
- `FINAL_TEST_ACCESS_COUNT = 0`
- `PAPER_FULL_RUN = FALSE`
- Exp3 Development execution: `COMPLETED_TEMPORARY` (support-boundary evidence)
- Authoritative multi-action coverage: `BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN`

## Scientific Question

When is a recovery recommendation sufficiently supported?

## Frozen Inputs

- PRE reused; M1 frozen signed model; frozen M1 scenario artifact `sha256:ca3370a3…1dfec`
- M2 `M2_DATA2_FORMAL_CU_V1`; M3 `M3_RESPONSE_SCENARIO_V1` (23 actions; A00 `NOT_REQUIRED`; 22 non-A00 templates `NOT_FROZEN`)
- Source Exp2 development: `sha256:1cf8a7ac…666d`

## Cohort

| Level | N |
|---|---|
| Episode | 128 |
| Decision node | 1824 |
| Scenario per node | 250 |

## Current Decision-Support Coverage State

All 1,824 nodes are numerically scenario-evaluable (23 actions each: A00 + 22 non-A00).

| State | N | Percentage |
|---|---|---|
| Numerically evaluable | 1824 | 100.0% |
| FORMAL lane (A00 only formal; formal_action_count=23) | 1824 | 100.0% |
| CONDITIONAL lane (22 non-null actions) | 1824 | 100.0% |
| SCENARIO lane (all 23 actions) | 1824 | 100.0% |
| Authoritative decision available | 0 | 0.0% |
| Authoritative abstain (blocker M4_MATERIAL_COVERAGE_UNFROZEN) | 1824 | 100.0% |
| Relaxed top1 full lane = FORMAL | 1824 | 100.0% |

Frozen lane rates: `FormalA00Rate=1.0`, `ConditionalRate=1.0`, `ScenarioOnlyRate=1.0`, `AbstainRate=1.0` (authoritative abstain), `BaselineOnlyFormalRate=0.0`.
Formal feasibility audit: candidate cohort 1824, formal multi-action cohort 1824, numerically evaluable 1824, no-authoritative-decision cohort 1824, baseline-only formal 0.
`InvalidatedTop1Rate=0.0`, `InvalidatedTopKShare=0.0`, coverage inflation (full−relaxed) `0.0`.

## Scenario vs Authoritative Distinction

Numerical M3 scenario response is a scenario-conditioned numerical representation, not an empirical causal effect, and does not by itself create FORMAL authority. `FORMAL`/`CONDITIONAL`/`SCENARIO`/`EXCLUDED` lanes and the authoritative decision are M4-gated; with no frozen material-coverage contract, every node abstains from an authoritative decision (`authoritative_decision_blocker = M4_MATERIAL_COVERAGE_UNFROZEN` on all 1,824 nodes).

## Unresolved M4 Boundary

- `M4_MATERIAL_COVERAGE_UNFROZEN` remains the current scientific boundary; M4-gated fields and all three ablations are `NOT_RUN_M4_BLOCKED`.
- The current Development evidence is sufficient to characterize the support boundary but not yet to report final authoritative multi-action coverage estimates.
- DeepSeek V2 operational audit: see `EXP3_DEEPSEEK_V2_AUDIT_SUMMARY.md` (auxiliary only).

