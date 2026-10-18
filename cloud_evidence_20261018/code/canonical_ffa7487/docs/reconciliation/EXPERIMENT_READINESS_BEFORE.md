# Experiment Readiness Before Reconciliation

Audit SHA: `8aa01f9866d12fd7cdf01148087db7e5fb688b8b`.

| Requirement | Producer | Consumer | Status | Evidence | Blocking |
| --- | --- | --- | --- | --- | --- |
| decision-time cutoff | PRE | Exp1 | PARTIAL | `DecisionNodeRecord.information_cutoff`, admissibility tests | No end-to-end cohort contract |
| rolling history | PRE/M1 | Exp1 | PARTIAL | five-minute prefix guard in `model/M1/data.py` | Formal horizon/config mismatch |
| aligned scenarios | M1 | Exp2 | PASS (contract) | `AlignedScenario`, M1 scenario tests | No real frozen-artifact runner |
| point-collapse source | M1 | Exp2 | MISSING | no evaluation config or point wrapper | Blocking |
| scenario lineage | M1/M2/M4 | Exp2 | PARTIAL | typed IDs and M4 pair check | Duplicate/empty edge cases unguarded |
| consequence scope | M2 | Exp2/3 | PASS (contract) | `ConsequenceScope`, `FormalEstimandValue` | Valuation remains development-only in smoke |
| evidence class | PRE/M2/M3 | Exp3 | PASS (contract) | support/evidence enums and M3 provenance | No ablation wrapper |
| material coverage | M3 | Exp3 | PASS (contract) | hashed coverage contract | No evaluation-only transformed copy |
| induced consequence | M3 | Exp3 | PASS (contract) | separate `mitigation`/`induced` fields | Runner is placeholder |
| formal candidate lanes | M4 | Exp3 | PASS (contract) | lane assignment and ranking gate | Formal artifacts not loaded by experiments |
| risk score | M4 | Exp3/4 | PASS (contract) | mean-CVaR implementation | No paired evaluation metrics |
| operational strata | PRE/eval | Exp4 | MISSING | no strata module/config | Blocking |
| paper promotion | exp | reporting | PARTIAL | `exp/promotion.py` checks role/smoke/paper flag | Manifest lacks required hashes and immutability guard |

## Baseline engineering checks

- `python -m compileall -q model exp validation tests`: PASS.
- `pytest -q`: 329 passed, 1 skipped, 1 failed in the pre-existing code-size
  audit (`REFACTOR_REQUIRED` for three files).
- `validation/dependency_rules.py`: subset scanner present; required global
  rules not yet complete.

This document is an audit snapshot, not evidence of scientific or paper
readiness.
