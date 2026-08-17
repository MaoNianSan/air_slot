# Scientific Conflict Ledger

Phase 0 read-only audit for the PRE-M4 global reconciliation. Repository SHA at
audit time: `8aa01f9866d12fd7cdf01148087db7e5fb688b8b`.

The pasted reconciliation brief is treated as the latest scientific definition
(Level A). Typed contracts are Level B, registries/configs Level C, and older
validation or experiment shells are engineering references only.

| ID | Scientific object | Latest scientific definition | Current code/config/registry | Affected consumers | Resolution | Files modified | Tests | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M1-HIDDEN-001 | M1 hidden dimension | Development candidates `[16, 32]`; no winner before development protocol; final test immutable | `foundation.yaml` freezes `m1_hidden_size: 8` and sensitivity `[16]`; `M1Pipeline.smoke()` hardcodes 8 | M1 pipeline, Exp1, Exp4, reports | Move 16/32 to explicit development candidates; remove 8 as scientific default; keep smoke fixture clearly non-formal | pending | pending | OPEN |
| M1-HORIZON-001 | Forecast horizons | Formal M1 output horizons `T=[0,15,60]`; delay thresholds `D=[15,30,60]` are distinct | Config and `model/M1/summaries.py` use `[0,30,60,120,180,240,300,360,420,480]` as default | M1 summaries, Exp1/Exp4, reporting | Make formal horizons `[0,15,60]`; retain old grid only as evaluation/sensitivity artifact | pending | pending | OPEN |
| M1-TARGET-001 | M1 target semantics | Preserve internal `R_IB/R_OB/T_TX`, with explicit external mapping and sample identity `D_TO=D_OB+D_TX` | Typed target contract has only the three internal names; no single semantic mapping; no `D_TO` identity contract | M1, Exp1, reports, paper outputs | Add one canonical semantic mapping and a derived sample-level total-delay helper; do not add a fourth trainable head | pending | pending | OPEN |
| DATASET-001 | Dataset-specific logic | Raw schema and quirks remain in PRE adapters/registries only | `model/M1/target_builder.py` and `model/M1/coverage.py` contain data2-specific API/logic | M1 and validation consumers | Replace M1 dataset-specific builder with generic typed target builder; keep data2 adapter wrappers in validation/PRE | pending | pending | OPEN |
| FORMAL-EVAL-001 | Formal/evaluation separation | Evaluation-only contrasts stay in `exp/`; formal artifacts are immutable | `exp/common/runner.py` copies a pre-existing `metric` for every variant and has no artifact/cohort/paired contracts | Exp1-Exp4, promotion | Add explicit evaluation configs, frozen-artifact manifest fields, and reject metric-copy placeholder inputs | pending | pending | OPEN |
| EXP4-001 | Exp4 contrast definitions | Hidden-size sensitivity is `[16,32]`; roll is `[5,10]`; operational heterogeneity is stratification, not retraining | Exp4 runner includes `m1_hidden_8`, old parameter names, and no strata contract | Exp4 and reporting | Rename variants/config namespace and add strata contract without training variants | pending | pending | OPEN |
| M4-001 | M4 identity validation | Hard-fail all listed lineage, ontology, scope, coverage, duplicate, and A00 checks | Current typed request covers most checks but does not explicitly reject duplicate scenario IDs or empty M2 scenario sets | M4 ranking and formal gate | Strengthen request validators and preserve A00 baseline semantics | pending | pending | OPEN |
| DEP-001 | Dependency rules | M1-M4 cannot import raw adapters/evaluation; model cannot import exp/reporting | Scanner checks only a subset; current M1 target builder violates dataset isolation by behavior, not import | Validation and CI | Extend static rules and tests to detect forbidden imports and dataset branches | pending | pending | OPEN |
| STATUS-001 | Readiness status | Scientific readiness must distinguish engineering PASS, conditional development freeze, and paper eligibility | No reconciliation/readiness matrix exists | Docs, promotion, manuscript handoff | Add readiness matrix and promotion metadata fields | pending | pending | OPEN |

Non-critical engineering item observed during audit: the repository code-size
test currently reports `model/PRE/transformation.py`, `model/PRE/episode/builder.py`,
and `validation/data2_m1_fast_january_wx_v2.py` over the local 500-line review
threshold. This is not a scientific semantic conflict and is tracked separately
from the reconciliation gate.

## After reconciliation

The baseline table above is intentionally preserved as a read-only audit snapshot.
The current worktree resolves the critical conflicts as follows:

| ID | Current status | Evidence | Remaining boundary |
| --- | --- | --- | --- |
| M1-HIDDEN-001 | DEVELOPMENT_FROZEN | `D2_H_STAR` freezes `foundation.yaml` at H=32 from five-seed Development-only evidence; Exp4 retains the approved 16/32 sensitivity candidates | Final Test remains sealed; no paper-full artifact exists |
| M1-HORIZON-001 | RESOLVED | `model/M1/semantics.py`, configuration tests, `M1Forecast` contract | Evaluation-only long horizon grid remains intentionally non-formal |
| M1-TARGET-001 | RESOLVED | canonical target map and `takeoff_delay_minutes`; behavioral equivalence and reconciliation tests | No fourth trainable head was introduced |
| DATASET-001 | RESOLVED | typed dataset identity check in target builder; adapter isolation and foundation smoke | Data2 validation aliases remain validation-only |
| FORMAL-EVAL-001 | RESOLVED_ENGINEERING_CONDITIONAL | frozen-artifact loader, variant transforms, paired runner, final-test guard | No complete paper-eligible frozen experiment manifest |
| EXP4-001 | RESOLVED | explicit 16/32 and 5/10 candidates; frozen strata with no retraining | Formal sensitivity run deferred |
| M4-001 | RESOLVED | explicit empty/duplicate scenario and candidate guards; decomposed decision facade | Real formal valuation artifacts remain absent |
| DEP-001 | RESOLVED_ENGINEERING | dependency scanner, adapter boundary checks, zero-cycle scan | A real CI job is not configured in this checkout |
| STATUS-001 | RESOLVED_ENGINEERING_CONDITIONAL | after readiness matrix and promotion metadata contract | Scientific readiness remains conditional, not PASS |

The only unresolved scientific choice is the formal hidden-size selection. It is
therefore reported as `EXPERIMENT_READINESS=CONDITIONAL`, while the repository
reconciliation itself is `GLOBAL_RECONCILIATION=PASS`.
