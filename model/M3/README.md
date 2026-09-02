# M3 boundary

M3 is an atomic recovery-action library plus response contract. It loads the 23-template action
registry and instantiates `CandidateAction` objects from PRE facts and declared parameters.

`ActionInstantiationRecord` records `chi_inst` for every template at every
node, including source and lineage. Only `FORMED` records carry a
`CandidateAction`; a missing required parameter is explicitly `NOT_FORMED` and
remains auditable with no candidate. `ActionInstantiationEvaluation` is the
internal declared-parameter check used to build the record. Each formed candidate separately
preserves factual `TRUE`/`FALSE`/`UNKNOWN`, response parameters/provenance,
material coverage, and authority capability labels. A factual FALSE does not
erase a formed mathematical instance, and UNKNOWN is retained rather than
guessed. `PURE_SCENARIO` and `STRUCTURAL_BOUNDED_SCENARIO` describe response
provenance, not automatically a real-world treatment effect. A00 is the
current decision-time framework baseline; this does not claim that no
historical intervention ever occurred.

The registry loader exposes a stable `registry_hash` over `registry_id`, schema version, and all
23 templates, plus the raw YAML `source_sha256`. A00 is `NOT_REQUIRED`. The
separate response registry freezes the other 22 as reproducible
assumption-grounded scenario specifications; this is not empirical-effectiveness
or operational response support. `python -m model.M3.cli`
can validate the structural registry or write an atomic manifest under `artifacts/diagnostics/overnight`.

`model.M3.m2_action_interface` is the contract-only bridge from immutable M2
baseline `C^{0,CU}(s)` to an action-conditioned `C^{a,CU}(s)` result. The V2
contracts in `model.M3.action_response` separate eligibility `I(a)` from the
response mechanism `P(a)`, preserve all scenario weights, require provenance,
and expose a no-money `ActionEvaluationEnvelope` for M4. Non-A00 scenario
responses may be numerically materialized only with their assumption label.
Factual state, response support, opportunity, numerical evaluability, and
selection authority remain separate states. See `docs/ACTION_DECISION_CONTRACT.md`.
