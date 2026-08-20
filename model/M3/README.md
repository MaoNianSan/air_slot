# M3 boundary

M3 is an atomic recovery-action library plus response contract. It loads the 23-template action
registry and instantiates `CandidateAction` objects from PRE facts and declared parameters.

Each candidate preserves mitigation, induced consequence, response parameters, response provenance,
material coverage, preconditions, and authority. Known FALSE preconditions remove a candidate;
UNKNOWN is retained and never guessed. `PURE_SCENARIO` and `STRUCTURAL_BOUNDED_SCENARIO` describe
response provenance, not automatically a real-world treatment effect. A00 is the current decision-
time framework baseline; this does not claim that no historical intervention ever occurred.

The registry loader exposes a stable `registry_hash` over `registry_id`, schema version, and all
23 templates, plus the raw YAML `source_sha256`. A00 is `NOT_REQUIRED`. The separate legacy
response registry freezes the other 22 as reproducible `PURE_SCENARIO` specifications with
`formal_support_upgrade=false`; this is not empirical-effectiveness support. `python -m model.M3.cli`
can validate the structural registry or write an atomic manifest under `artifacts/diagnostics/overnight`.

`model.M3.m2_action_interface` is the contract-only bridge from immutable M2
baseline `C^{0,CU}(s)` to an action-conditioned `C^{a,CU}(s)` result. The V2
contracts in `model.M3.action_response` separate eligibility `I(a)` from the
response mechanism `P(a)`, preserve all scenario weights, require provenance,
and expose a no-money `ActionEvaluationEnvelope` for M4. Only the A00 identity
is executable in V2; non-A00 component response mappings remain gated.
