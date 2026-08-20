# Experiment Legacy Risk Report

## Critical risks

| Priority | Risk | Evidence | Required containment |
| --- | --- | --- | --- |
| P0 | old scenario identity and fields | Exp1 warning artifacts and `exp/exp2/representations.py` use V1 fields; stored Exp234 scenarios predate current D_TO identity | reject V1 artifacts in new runners; preserve as historical-only |
| P0 | manual M2 reconstruction | `exp/exp234/development_execution.py::_fast_pre_rows` reconstructs five-component CU and old takeoff delay | remove from active path; consume typed M2 outputs only |
| P0 | legacy M3 response bypass | Exp234 calls `model.M3.response` and uses scenario-only registry parameters | remove from active path; require `ActionEvaluationEnvelope` |
| P0 | hard-coded induced conversion | `_post_scope(... induced_score_to_cu=0.10)` | prohibit experiment-owned consequence/action mappings |
| P0 | raw-CU ranking as decision value | Exp234 sums post-action CU and sorts actions | require M4 risk envelopes; no raw-CU fallback |
| P0 | false readiness from old status | dynamic old V5 status reports `paper_full_eligible=true` and Exp1-4 PASS | namespace/supersede old status; new readiness must depend on new protocol implementations and scientific gates |
| P1 | generic metric injection | `BaseRunner` trusts caller-provided `variant_metrics` | runner must compute metrics from validated artifacts |
| P1 | dictionary formal wrapper | `formal/pipeline.py` hashes arbitrary mappings | validate typed serialized stage schemas and chain hashes |
| P1 | missing result lineage | no dedicated model version, scenario hash, metric schema or support authority | implement new result schema before experiment runners |
| P1 | overloaded “coverage” | predictive, support and material coverage share terminology | use distinct metric IDs and denominators |

## Named legacy assumptions

### Delay-only evaluation

Old Exp1 warning code evaluates a strict D_TO warning event and old Exp2/Exp234 reconstructs consequence from delay fields. This is narrower than the frozen operational uncertainty -> consequence -> action response -> monetary residual-risk chain. Historical warning metrics are not evidence for the new Exp1 question.

### Raw CU ranking

Exp234 compares actions using sums of legacy component CU. Current M4 explicitly forbids raw-CU fallback. These rankings are scenario-conditioned historical diagnostics, not authoritative decisions or risk.

### Old RMB/manual cost mapping

No production monetary mapping is frozen. Test-only mappings and `induced_score_to_cu=0.10` cannot be labelled RMB, cost, savings or residual risk. Any historical manual cost/action value must be excluded from the new pipeline.

### Legacy action score

Legacy candidates expose mitigation, induced score and response draws. The new boundary requires M3 eligibility, typed response mechanism/support/provenance, and `Ca_CU`. Experiment code may not recompute the response score.

### Old module ablation

The current Exp3 evidence/coverage/induced-consequence ablations and old Exp4 sensitivity grid answer superseded questions. They must not be renamed to ONE_SHOT/ROLLING or prediction/validation/portability/runtime.

## Additional hazards

- `configs/evaluation/exp1.yaml` through `exp4.yaml` still encode the former experiment philosophy.
- old README/status/manifests can disagree with the current typed V2 model boundaries.
- quick validation CRPS outputs are historical diagnostics and use stale report text/inputs.
- compatibility APIs remain importable in M1, M2 and M4; a new runner can accidentally select them unless tests forbid those imports.
- historical Development artifacts may have valid hashes while being scientifically incompatible; hash validity is not interface compatibility.

## Containment policy

- preserve historical code/artifacts for provenance; do not delete during migration planning;
- place new runners behind explicit current schema/version guards;
- add dependency tests that ban compatibility modules from new experiment packages;
- use `HISTORICAL_ONLY`, `CONDITIONAL`, `BLOCKED`, and `AUTHORITATIVE` as distinct states;
- never translate an unavailable current output into a numeric zero or a legacy substitute.

`LEGACY_STATUS = HIGH_RISK_NOT_REUSABLE_END_TO_END`

