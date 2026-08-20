# Exp2 M4 Policy Binding

Artifact: `artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json`

The residual-risk policy is frozen from the current manuscript configuration:

- `alpha=0.90`;
- expected-loss coefficient `0.75`;
- CVaR coefficient `0.25`;
- policy hash `sha256:158a09bb47d4b715e0a97a1da74d6b64b2dd4ab5c99eb1cba1f00475f016a2dc`.

No parameter search was performed. The policy's tail support remains
`UNRESOLVED`, so residual-risk execution is blocked by
`M1_POSITIVE_TAIL_DECISION_REQUIRED`. The seven-component monetary registry is
not frozen, so the mapping state is `MONETARY_MAPPING_BLOCKED`. No internal or
monetary risk score, ranking, or pilot metric was calculated.

`FINAL_TEST_ACCESS_COUNT=0` and `PAPER_FULL_RUN=false`.
