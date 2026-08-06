# M3 Code Audit

Audit date: 2026-08-02

M3_CODE_AUDIT=FAIL
M3_TYPED_GATE_AUDIT=PASS
M3_RANDOMNESS_AUDIT=PASS
M3_ACTION_REACHABILITY=FAIL

## Passing evidence

- The merged formal configuration contains exactly 26 ordered actions and complete response-parameter fields; removing one action and duplicating A00 are rejected.
- S01/S02 are excluded from the formal library.
- Response means, costs, concentration, cost CV, and failure probability are range-validated in `overall_run/src/m3.py:106-190`.
- Required typed gates fail closed when the value or evidence column is missing/unsupported.
- M3 draws use stable per-action seed namespaces (`overall_run/src/m3.py:213-223`); reversing action iteration order produced identical success, recovery, and cost arrays.
- The current candidate-screen output contains all 26 formal action IDs.

## Blocking defects

- The action inventory has multiple independent authorities instead of one source.
- Boolean fields are not type-checked. Injected `capacity_required: "false"` is stored as the string `"false"`, and `bool("false")` is true.
- Thirteen formal actions have `scored_count=0` in the current fast output: `A11, A21, A33, A43, A55, A61, A62, A71, A72, A73, A81, A82, A83`. Their zero reachability is explained by trigger/value/gate failures, but the workflow requires every zero-scored formal action to be explicitly resolved before approval.
- Extreme provisional actions A61/A62, A71-A73, and A81-A83 never reach scoring in this development output; this blocks action-reachability confirmation even though fail-closed gating itself is correct.

Detailed counts are in `reports/M3_ACTION_REACHABILITY.csv`.
