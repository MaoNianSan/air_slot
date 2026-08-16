# M3 boundary

M3 is an atomic recovery-action library plus response contract. It loads the 23-template action
registry and instantiates `CandidateAction` objects from PRE facts and declared parameters.

Each candidate preserves mitigation, induced consequence, response parameters, response provenance,
material coverage, preconditions, and authority. Known FALSE preconditions remove a candidate;
UNKNOWN is retained and never guessed. `PURE_SCENARIO` and `STRUCTURAL_BOUNDED_SCENARIO` describe
response provenance, not automatically a real-world treatment effect. A00 is the current decision-
time framework baseline; this does not claim that no historical intervention ever occurred.
