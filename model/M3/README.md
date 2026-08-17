# M3 boundary

M3 is an atomic recovery-action library plus response contract. It loads the 23-template action
registry and instantiates `CandidateAction` objects from PRE facts and declared parameters.

Each candidate preserves mitigation, induced consequence, response parameters, response provenance,
material coverage, preconditions, and authority. Known FALSE preconditions remove a candidate;
UNKNOWN is retained and never guessed. `PURE_SCENARIO` and `STRUCTURAL_BOUNDED_SCENARIO` describe
response provenance, not automatically a real-world treatment effect. A00 is the current decision-
time framework baseline; this does not claim that no historical intervention ever occurred.

The registry loader exposes a stable `registry_hash` over `registry_id`, schema version, and all
23 templates, plus the raw YAML `source_sha256`. A00 is `NOT_REQUIRED`; the other 22 templates
remain `NOT_FROZEN` until a scientific response-parameter freeze is approved. `python -m model.M3.cli`
can validate the registry or write an atomic manifest under `artifacts/diagnostics/overnight`.
