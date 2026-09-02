# M4 V2 boundary

M4 V2 consumes only `M4ActionEnvelopeInput`, the validated serialization of
M3 `ActionEvaluationEnvelope`. Operational state, raw delays, weather, PRE/M1
features, M2 native quantities and action-response generation are outside M4.

M2 owns the fixed seven-component ontology `K`. M4 requires a frozen explicit
`ConsequenceComparisonScope` defining `K_cmp subset K`, support requirements,
measurement registry ID, version, and provenance. No seven- or five-component
comparison default exists: absent or unfrozen scope returns
`chi_num=UNDEFINED` with `COMPARISON_SCOPE_NOT_FROZEN`.

`model.M4.residual_risk` maps immutable `C_k^{a,CU}(s)` through a versioned
`MonetaryMappingRegistry` to `L_k^{a,m}(s)`, then preserves scenario weights
when calculating expected loss, variance, upper-loss VaR and weighted CVaR.
Every result retains the M2 reference-lineage hashes and M3 response
provenance. `chi_num` is defined only by complete finite consequence, mapping,
and risk inputs. A response-support label, factual state, or opportunity state
does not by itself change `chi_num`; those states remain metadata on the same
evaluation. Complete but not fully supported inputs are labelled
`CONDITIONAL_INPUTS`; incomplete numerical inputs are `NOT_COMPARABLE`.

M4 also preserves M3 factual eligibility and opportunity state without
collapsing either into numerical evaluability. A missing execution opportunity
is not defaulted open. The output collections are numerical comparisons, not
operational recommendations, and A00 is an identity comparator only. The
current six-state qualification boundary is in `docs/ACTION_DECISION_CONTRACT.md`.

The active model-owned mapping is `M4_RMB_BASE_MAPPING_V2`: all seven
components use the constructed measurement convention `1 CU = 1 RMB`.
`P_itinerary` and `P_service` are included in RMB BASE after the passenger
reference refactor. V1 remains immutable superseded provenance. This convention is not a currency conversion,
accounting cost, or empirical airline-loss estimate. A comparison still
requires an explicitly frozen `ConsequenceComparisonScope`; the monetary
registry does not create a default `K_cmp`.

The old `contracts.py`, `post_action.py`, `risk.py`, and `ranking.py` modules
remain compatibility-only pre-V2 code and are excluded from the package's
public V2 API.
