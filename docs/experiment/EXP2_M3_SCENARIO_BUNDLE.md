# Exp2 M3 Scenario Bundle

Artifact: `artifacts/experiment/exp2/DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json`

The typed bundle has ID `DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE_V1` and hash
`sha256:e80c77261101231760be90cfbe603aec36e8f6c386badabb9d6acecf881baf02`.
It contains mandatory baseline `A00` plus 22 frozen non-baseline response
rules from `M3_RESPONSE_SCENARIO_V1` at `BASE` sensitivity.

For every non-`A00` rule, the bundle retains its response-rule ID, rule hash,
parameters, parameter version, freeze ID, and provenance. Its support state is
`SCENARIO_ASSUMPTION` with `source_type=PURE_SCENARIO` and
`formal_support_upgrade=false`. The bundle is therefore executable only in the
conditional Exp2 scenario lane; it does not claim supported treatment effects
or authoritative action ranking.

`FINAL_TEST_ACCESS_COUNT=0` and `PAPER_FULL_RUN=false`.
