# M4 V2 Implementation Report

Date: 2026-08-07

## Scope

This local-only closure integrates the existing `M4_CONTEXTUAL_RESIDUAL_RISK_V2`
package into the repository contract. It did not run Fast, Middle, Full,
`overall_adv`, `part_adv`, PRE reconstruction, M1 training/calibration/sampling,
M2 formal reconstruction, M3 parameter freeze, or M3 formal library generation.

## Integrated implementation

- Strict M4 V2 configuration and retired decision-value rejection.
- Direct M2 V2 / M3 V4 input adaptation with PRE R2/R3 evidence separation.
- Stable shared draw indexing and nine-subitem post-loss calculation.
- Weighted Mean-CVaR and one five-key authoritative ranking order.
- Fixed-width Ranking@1/@2/@3/@5 without a second score sort.
- Explicit VALID, CONDITIONAL_ONLY, SCENARIO_ONLY, A00_ONLY, upstream-blocked,
  abstain, stale, and contract-error status handling.
- A pure multi-condition publication gate with explicit reason codes.
- Bundle-level formal staging, validation, hashing, and directory publication.
- Optional read-only evaluation after formal bundle freeze, with separate formal
  and evaluation statuses.
- Main pipeline M3 gates preserved, followed by M4 V2 and finalization calls.

## Current status

```text
PRE_CORE_CHANGED = NO
M1_CORE_CHANGED = NO
M2_CORE_CHANGED = NO
M3_CORE_CHANGED = NO

M4_V2_CORE_IMPLEMENTATION = PASS
M4_V2_REPOSITORY_INTEGRATION = PASS
M4_V2_SYNTHETIC_INTEGRATION = PASS

TARGET_REPOSITORY_PRE_R3_IMPLEMENTATION = NOT_PRESENT
PRE_R3_FAST_REBUILD = NOT_RUN
M2_VALUATION_FREEZE = NOT_YET_DONE
M3_PARAMETER_FREEZE = NOT_YET_DONE
M3_FORMAL_LIBRARY = NOT_YET_RUN

M4_FORMAL_STATUS = BLOCKED_BY_UPSTREAM
GLOBAL_RERUN_ALLOWED = NO
```

Repository integration PASS is an engineering result. It is not evidence that
formal recovery recommendations have been scientifically validated.
