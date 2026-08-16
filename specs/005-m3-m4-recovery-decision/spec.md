# Feature Specification: M3-M4 Recovery Decision

## User Scenarios

1. Instantiate all 23 frozen action templates from PRE facts without attractiveness pruning.
2. Preserve TRUE/FALSE/UNKNOWN preconditions, response provenance, coverage, mitigation and induced footprints.
3. Map PRE+M1+M2+M3 into lanes, opportunity, stable responses, post-action consequence and mean-CVaR risk.
4. Publish authoritative FORMAL-only Ranking@1/@2/@3/@5 and separate user authority projection.

## Requirements

- M3 reads PRE and frozen action registry only. FALSE removes; UNKNOWN retains.
- Registry contains A00,A11,A13,A21,A22,A23,A31,A32,A33,A41,A42,A43,A51-A55,A61-A64,A71,A72.
- No public-data action response may be marked EMPIRICAL; scenario evidence cannot be upgraded.
- Coverage is FULL/HIGH/PARTIAL/INSUFFICIENT; missing consequence is never zero.
- M4 lanes are FORMAL/CONDITIONAL/SCENARIO/EXCLUDED; only FORMAL ranks.
- A00 post-action consequence equals pre-action for every scenario/component.
- Opportunity zero excludes; no arbitrary positive threshold.
- J=(1-lambda)mean+lambda*CVaR_alpha with principal lambda=.25 alpha=.90, lower is better.
- Response streams exclude decision time. Exact ties use fixed action index.
- Ranking@k is null when fewer than k FORMAL actions. User projection affects DIRECT/ESCALATE only, not company ranking.

## Success Criteria

All action IDs load; M3 dependency boundary, A00 identity, lanes, response stability, opportunity, risk, ranking prefixes and authority projection tests pass.
