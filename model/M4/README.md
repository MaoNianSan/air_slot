# M4 V2 boundary

M4 V2 consumes only `M4ActionEnvelopeInput`, the validated serialization of
M3 `ActionEvaluationEnvelope`. Operational state, raw delays, weather, PRE/M1
features, M2 native quantities and action-response generation are outside M4.

`model.M4.residual_risk` maps immutable `C_k^{a,CU}(s)` through a versioned
`MonetaryMappingRegistry` to `L_k^{a,m}(s)`, then preserves scenario weights
when calculating expected loss, variance, upper-loss VaR and weighted CVaR.
Every result retains the M2 reference-lineage hashes and M3 response
provenance. Unsupported action responses or incomplete consequence/mapping
coverage abstain and are not ranked. Scenario assumptions and test-only
configuration receive conditional rankings; only supported M3 responses with
scientifically frozen mapping and risk policies may be authoritative.

No production monetary mapping is currently frozen. The design registry
`registries/m4_v2_monetary_mapping_design.json` therefore abstains for all
seven components. Synthetic mappings use `TEST_ONLY` and cannot establish a
real RMB claim.

The old `contracts.py`, `post_action.py`, `risk.py`, and `ranking.py` modules
remain compatibility-only pre-V2 code and are excluded from the package's
public V2 API.
