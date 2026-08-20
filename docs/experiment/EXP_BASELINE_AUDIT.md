# Experiment Baseline Audit

## Baseline inventory

| Baseline | Category | Current location | Leakage / unsupported-cost / bypass audit | Disposition |
| --- | --- | --- | --- | --- |
| `empirical` | Prediction | `Exp1Runner.variants` only | undefined computation; arbitrary metric can be injected | `REWRITE` |
| `independent_heads` | Prediction/representation | old Exp1 runner | historical V1 model idea; no current V2 builder or artifact contract | `REWRITE` or remove after protocol decision |
| `CURRENT` | Representation/history | `model/M1/history.py` | causal current node only; no future leak | `KEEP` |
| `FIXED_HISTORY` | Representation/history | `model/M1/history.py` | causal closed window; no future leak | `KEEP` |
| `ADAPTIVE_HISTORY` | Representation/history | `model/M1/history.py` | full legal episode prefix; no future leak | `KEEP` |
| `RETROSPECTIVE_LEAKAGE_DIAGNOSTIC` | Evaluation diagnostic | `exp/exp1/variants.py` | intentionally uses invalid future information; correctly marked evaluation-only | `REMOVE` from scientific baselines; may remain a negative control |
| weighted joint medoid | Representation | `exp/exp2/representations.py::point_collapse` | coherent scenario, but legacy fields | `REUSE_WITH_ADAPTATION` as `COLLAPSED` |
| marginal-preserving shuffle | Representation | `corrupt_scenario_lineage` | no future leak; breaks joint association; legacy fields | `REUSE_WITH_ADAPTATION` as `MARGINAL` |
| unchanged distribution | Representation | q=0/source artifact | correct shared-source reference | `KEEP` as `JOINT` |
| flight/full five-component scope | Representation | old Exp2/Exp234 | historical M2 scope; not the current seven-component V2 ontology | `REMOVE` |
| A00 identity | Decision | `model/M3/action_response.py::build_a00_identity_envelope` | typed `Ca_CU=C0_CU`; no unsupported effect | `KEEP` |
| legacy non-A00 action response | Decision | `model/M3/response.py`, Exp234 | scenario-only response; no formal support upgrade | `REMOVE` from new baseline path |
| raw-CU action ranking | Decision | Exp234 action maps | bypasses M4 monetary/risk boundary | `REMOVE` |
| hard-coded induced conversion | Decision | `exp/exp234/exp234_helpers.py::_post_scope` | `induced_score_to_cu=0.10` is an unsupported/manual mapping in the new chain | `REMOVE` |
| Data1 static support gate | Evaluation/portability | `exp/exp4/portability.py` | no raw-value substitution; does not execute a dataset replication | `KEEP` as a gate, not a performance baseline |
| STATE_AWARE versus FAST | System | `M1Service`, old Exp4 design | explicitly labelled model path; parity/equivalence still required | `REUSE_WITH_ADAPTATION` |

## Baseline rules for the rewrite

1. A baseline must be an executable, versioned transformation or evaluator, not a label attached to caller-supplied metrics.
2. All paired baselines must preserve cohort, cutoff, model/calibration identity, scenario budget and seeds except for the declared intervention.
3. A negative-control leakage diagnostic must be excluded from model candidates, headline comparisons and paper-support counts.
4. Decision baselines must consume M3 action envelopes; risk baselines must consume M4 risk envelopes.
5. Unsupported cost, test-only money, raw-CU totals and scenario-only response must remain conditional/blocked and cannot become reference truth.
6. Data1 portability cannot silently replace missing Data2 semantics or be pooled with Data2.

`BASELINE_STATUS = STALE_WITH_NARROW_REUSABLE_CONTROLS`

