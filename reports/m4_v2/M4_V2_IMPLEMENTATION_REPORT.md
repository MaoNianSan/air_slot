# M4 V2 Implementation Report

Date: 2026-08-07

## Scope

This local-only change implements `M4_CONTEXTUAL_RESIDUAL_RISK_V2` in
`overall_run/src/m4/`. No branch, commit, push, Fast, Middle, Full,
`overall_adv`, `part_adv`, PRE rebuild, M1 training, M2 formal reconstruction,
M3 parameter freeze, or formal M3 library generation was performed.

## Implemented

- Direct input from `M2InputBundle`, `tuple[M2SampleLoss, ...]`, and `M3Artifact`.
- Exact nine-subitem, F/P/R, total-loss, weight, shape, range, hash, and A00 checks.
- PRE R2 compatibility-only and PRE R3 registry-lineage discrimination.
- Explicit evidence requirements with pressure/resource, occupancy/handler,
  future-chain, proxy/observation, and missing-to-zero prohibitions.
- Explicit stage adapter and unconfigured opportunity contract.
- SHA-256 `STABLE_SHARED_DRAW_INDEX` pairing by episode, sample, and M3 sample hash.
- Nine-subitem post loss plus one F/P/R implementation cost per channel.
- Weighted mean, weighted VaR, exact fractional-tail weighted CVaR, and
  A00-paired improvement metrics.
- FORMAL, CONDITIONAL, SCENARIO, and EXCLUDED lanes.
- One authoritative formal sort and fixed-width Ranking@1/@2/@3/@5 views.
- Formal output schemas, test-only publication guard, and read-only evaluation.

## Current Status

```text
PRE_CHANGED_IN_M4_REPO = NO
M1_CHANGED = NO
M2_CORE_CHANGED = NO
M3_CORE_CHANGED = NO

PRE_R3_REFERENCE_IMPLEMENTATION = PASS_LOCAL_UNCOMMITTED
PRE_R3_FAST_REBUILD = NOT_RUN
M4_REPO_PRE_VERSION = AIR_CHAIN_CORE_V2_R2
M4_REPO_PRE_R3_LINEAGE_AVAILABLE = NO

M2_VALUATION_FREEZE_STATUS = NOT_YET_DONE
M3_PARAMETER_FREEZE_STATUS = NOT_YET_DONE
M3_FORMAL_LIBRARY_STATUS = NOT_YET_RUN

M4_V2_PACKAGE_MIGRATION = PASS
M4_V2_SYNTHETIC_INTEGRATION = PASS_TEST_ONLY
M4_V2_FORMAL_STATUS = BLOCKED_BY_UPSTREAM
```

The PRE R3 implementation exists only in the separate local PRE worktree at
`D:\research\air_slot\code\explore`; it was not copied into this repository and
no R3 bundle was built. The current M2 bundle carrier also lacks bundle-level
PRE revision and registry metadata unless explicit manifest lineage is placed
in context provenance. M4 therefore keeps the formal R3 evidence gate closed.
