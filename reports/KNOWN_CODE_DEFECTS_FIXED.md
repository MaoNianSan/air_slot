# Known Code Defects Fixed

Audit date: 2026-08-02

KNOWN_CODE_DEFECTS_FIXED=YES
RECOVERY_020_GATE_DELETED=YES
STATIC_DIFF_CHECK=PASS
TARGETED_FAULT_PROBES=5/5_PASS
TARGETED_TESTS=64/64_PASS
FULL_FAST_CHAIN_RERUN=NO
MIDDLE_FULL_EXECUTED=NO

| Known defect | Minimal verification | Result | Evidence |
|---|---|---|---|
| M1 overlapping leg masks an older valid predecessor | Matcher fault probe plus targeted matcher tests | PASS | Selected `valid_old` at search depth 2; `pre/tests/test_predecessor_matching.py`: 11 passed |
| M3 string `"false"` is treated as true | Boolean fault probe plus M3 schema tests | PASS | Rejected with `M3_BOOLEAN_FIELD_INVALID:A11:capacity_required` |
| Expanded actions have zero scored reachability | Synthetic positive/negative reachability tests | PASS | `overall_run/tests/test_m3_v3_expanded.py`: 11 passed, including fail-closed classification and scored synthetic cases |
| M4 tie-break uses the wrong secondary field | Equal-score counterexample | PASS | Expected-residual ordering returned `A12,A11` |
| Zero-candidate ranking padding fails | Zero-candidate probe plus ranking boundary tests | PASS | Emitted 11 null padding rows for K=1/2/3/5 |
| overall_adv accepts mismatched Global/Local candidates | Candidate mismatch fault probe and contract tests | PASS | Raised `CandidateSetContractError`; `overall_adv/tests/test_ranking_1235.py`: 4 passed |
| Dev clean cannot isolate registered outputs | Dry-run isolation tests only | PASS | `tests/test_dev_clean_isolation.py`: 16 passed; no clean was executed in this verification stage |

## Targeted Regression

- M1 predecessor matcher: 11 passed.
- M3 boolean and reachability: 11 passed.
- M4 ranking, PNB, publication schema, and 0.20 gate deletion: 22 passed.
- overall_adv candidate/ranking contract: 4 passed.
- Dev clean dry-run isolation: 16 passed.

## Static Findings

- No source references remain for `recovery_ratio_min`.
- No source references remain for `RECOVERY_RATIO_BELOW_MIN`.
- No source references remain for `gate_recovery_ratio`.
- `recovery_ratio` remains only as a diagnostic metric; it is not an admission gate.
- The seven defect implementations and their corresponding tests are present in the code tree.

## Run Boundary

- The complete fast development chain was not rerun after code freeze.
- A PRE development run that had already started was stopped at PID 7456 after the new instruction arrived.
- `pre/output/fast_three_change_dev` contains partial interrupted files and must not be treated as a PASS output.
- No formal fast, middle, or full run was executed in this verification stage.
- R3 parameter approval and M3 scientific parameter approval remain separate pending decisions.

