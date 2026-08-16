# Experiment Readiness After Reconciliation

Repository HEAD: `8aa01f9866d12fd7cdf01148087db7e5fb688b8b` (uncommitted worktree).

Scientific config hash: `sha256:92ecaba327c5660113fde8e108e39df80dfba4d91ef2ef2cea1a58e4c9b687a3`
Registry manifest hash: `sha256:dbe3da2d8f8b74cf920d2b1bfc75519970ce7e6d71133bba8d19208b90f56aaa`

| Requirement | Producer | Consumer | Status | Evidence | Blocking |
| --- | --- | --- | --- | --- | --- |
| decision-time cutoff | PRE | Exp1 | PASS (contract) | `DecisionNodeRecord.information_cutoff`; PRE fixture and integration tests | No real paper cohort |
| rolling history | PRE/M1 | Exp1 | PASS (engineering) | five-minute prefix guard; bounded smoke history report | Formal training artifact not frozen |
| aligned scenarios | M1 | Exp2 | PASS | `AlignedScenario`; deterministic scenario tests and 64-row bounded smoke | No formal frozen bundle |
| point-collapse source | M1 | Exp2 | PASS (evaluation wrapper) | `point_collapse` carries source artifact hash and derives `D_TO` | Formal Exp2 run deferred |
| scenario lineage | M1/M2/M4 | Exp2 | PASS | scenario seed keys, IDs, M4 pair checks, marginal-preserving shuffle test | None at contract level |
| consequence scope | M2 | Exp2/3 | PASS (contract) | `ConsequenceScope`, `FormalEstimandValue`, typed mapper equivalence | Valuation registry is development-only smoke |
| evidence class | PRE/M2/M3 | Exp3 | PASS | support/evidence enums and M3 provenance contracts | No formal ablation artifact |
| material coverage | M3 | Exp3 | PASS | hashed `ActionMaterialCoverageContract` and M4 eligibility | Formal M3 bundle absent |
| induced consequence | M3 | Exp3 | PASS | separate induced/mitigation fields; copy-only ablation | No Exp3 run |
| formal candidate lanes | M4 | Exp3 | PASS | lane assignment and decomposed ranking facade | No paper candidate manifest |
| risk score | M4 | Exp3/4 | PASS (engineering) | residual-risk tests and M4 behavioral equivalence | Formal valuation inputs unresolved |
| operational strata | PRE/eval | Exp4 | PASS (evaluation contract) | `configs/evaluation/exp4.yaml`, no-retrain strata test | No formal sensitivity run |
| paper promotion | exp | reporting | CONDITIONAL | complete-manifest checks, dataset-role gate, FINAL_TEST guard | No paper-eligible frozen manifest |

## Experiment status

| Experiment | Status | Reason |
| --- | --- | --- |
| Exp1 | CONDITIONAL | protocol scaffolding and copy isolation pass; no frozen formal artifact/cohort |
| Exp2 | CONDITIONAL | point/full representations and deterministic lineage shuffle pass; no paper run |
| Exp3 | CONDITIONAL | copy-only ablations and provenance contracts pass; LLM audit is `NOT_RUN` |
| Exp4 | CONDITIONAL | candidate namespace and frozen strata pass; hidden-size winner and sensitivity run absent |

## Evidence executed in this turn

- `python -m compileall -q model exp validation tests`: PASS.
- `pytest -q`: `342 passed, 1 skipped`.
- `python -m validation.cli all --fixtures-only`: `409 PASS`, no failures or blocks.
- `python -m validation.data2_m1_bounded_smoke_v2`: PASS, 64 deterministic scenarios,
  finite normalized probabilities, and `raw_read_only=true`; `paper_result=false`.
- No full-year validation and no formal Exp1-Exp4 run was executed.

Therefore: `GLOBAL_RECONCILIATION=PASS`; `EXPERIMENT_READINESS=CONDITIONAL`.
