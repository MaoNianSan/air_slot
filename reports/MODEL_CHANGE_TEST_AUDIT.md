# Model Change Test Audit

Audit date: 2026-08-02

## Existing suite

| Group | Passed | Failed |
|---|---:|---:|
| PRE | 22 | 0 |
| overall_run | 97 | 0 |
| overall_adv | 13 | 0 |
| part_adv | 13 | 0 |
| root profiles | 64 | 0 |
| P1 reconstruction | 18 | 0 |
| Total | 227 | 0 |

## Active fault injection

- PASS: R3 seconds/minutes corruption, action count 25, duplicate A00, padding A00, missing typed gate, future M1 field, action-order seed stability, t1/t2/t3 availability.
- FAIL: unknown PRE override, overlap masking earlier valid predecessor, string boolean parsing, feature-order contract mutation, Global/Local candidate mismatch, expected-residual tie-break, zero-candidate padding.

MODEL_CHANGE_TEST_AUDIT=FAIL because the normal-path suite passes while seven required erroneous states remain uncaught or unsupported.
