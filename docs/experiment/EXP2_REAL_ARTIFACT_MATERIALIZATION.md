# Exp2 Real Artifact Materialization

Status: `M1_M2_REAL_ARTIFACT_BLOCKED`

The Development-only materializer completed the legal non-M1-dependent stages:

| Artifact | Identity | Status |
| --- | --- | --- |
| Data2 cohort | `DATA2_DEVELOPMENT_PILOT_COHORT.json` | 5 episodes, 69 nodes, content-addressed Development cohort |
| M3 bundle | `DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json` | typed BASE conditional response bundle |
| M4 policy | `DATA2_DEV_PILOT_M4_RISK_POLICY.json` | frozen manuscript parameters; execution blocked by tail/mapping gates |
| Gate audit | `EXP2_PRE_M4_REAL_DATA_PILOT_AUDIT.json` | records the explicit stop condition |

The audit artifact hash is
`sha256:58171ab4880cee8686569889bd7dbeb179565fac4fa09b36815b3ea846657f5c`.
All four artifacts record `FINAL_TEST_ACCESS_COUNT=0` and
`PAPER_FULL_RUN=false`.

No M1 V2 scenario artifact was materialized: no train-frozen executable M1 V2
checkpoint and scenario artifact is registered. Historical `M1_SIGNED_* V1`
files were discovered and explicitly excluded. Consequently M2 V2, all Exp2A
representations, all Exp2B representations, action-set coverage, predictive
metrics, and pilot risk metrics were not run.
