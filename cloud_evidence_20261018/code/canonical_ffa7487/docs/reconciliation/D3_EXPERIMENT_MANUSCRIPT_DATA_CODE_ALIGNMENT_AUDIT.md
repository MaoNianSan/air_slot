# D3 Experiment, Manuscript, Data, and Code Alignment Audit

- audit date: `2026-08-17`
- latest repository Experiment V5 implementation report: `docs/EXPERIMENT_V5_IMPLEMENTATION_REPORT.md`
- latest evaluated Exp1 config: `configs/evaluation/exp1.yaml`
- Data2 contract: `data2/DATA_USAGE.md`
- scientific config: `configs/scientific/foundation.yaml`
- Final Test access count: `0`

## Manuscript availability

No `.tex` manuscript or current manuscript source was found in the repository,
`D:\Local_Projects\airslot`, or `D:\research\air_slot`. The newest located
Air Slot prose document is the May 5, 2026 research proposal DOCX; it contains
no M1/Exp1 equations or warning-probability contract. Therefore the manuscript
column below is `NOT_LOCATED` where an exact current rule cannot be verified.

An older manuscript-facing reconciliation item in
`docs/reconciliation/SCIENTIFIC_CONFLICT_LEDGER.md` states a sample identity
`D_TO=D_OB+D_TX`. That statement is incompatible with the current event-time
and reference contract and is a stale item; production code must not be changed
to reproduce it.

## Alignment table

| OBJECT | LATEST_EXP_RULE | MANUSCRIPT_RULE | DATA2_SUPPORT | PRE_IMPLEMENTATION | M1_IMPLEMENTATION | EXP1_IMPLEMENTATION | STATUS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `H_STAR` | signed-target Development choice `32` | NOT_LOCATED | not data-limited | signed cache is split-contained | config/pipeline use `32` | signed H evidence frozen; no rerun after approval | PASS |
| `W_STAR` | signed-target fixed window `30` minutes | NOT_LOCATED | not data-limited | canonical five-minute nodes | M1 closed `[t-30,t]` history API | signed W evidence frozen; no rerun after approval | PASS |
| history semantics | CURRENT node; FIXED closed current-episode interval; ADAPTIVE full current-episode prefix | NOT_LOCATED | PRE supplies legal episode grid | episode-bounded causal membership | `model/M1/history.py` owns all transformations | exp imports/invokes only | PASS |
| Data2 schedule reference | same across variants | NOT_LOCATED | official CRS schedule fields | canonical schedule reference with decision-time publication | signed time-to-schedule feature; labels use scheduled departure | no raw schedule handling | PASS |
| `R_IB` | same target across variants | NOT_LOCATED | predecessor actual arrival available post hoc | typed outcome retained outside inference state | nonnegative remaining-to-in-block label | consumed, not redefined | PASS |
| `DELTA_OB` | signed stochastic target across variants | NOT_LOCATED | actual and CRS scheduled departure supported | typed schedule/outcome available post hoc | signed ordered head with explicit underflow/overflow | consumed, not redefined | PASS |
| `R_OB` | derived compatibility value | NOT_LOCATED | derived from signed departure offset | typed schedule/outcome available | `max(0, DELTA_OB)`; no stochastic head | consumed only as derived value | PASS |
| `T_TX` | same target across variants | NOT_LOCATED | official `TaxiOut` supported | typed post-hoc taxi-out and train-frozen direct reference supported | ordered nonnegative taxi duration head | consumed, not redefined | PASS |
| `D_TO` | principal warning event names `D_TO_POST_GT_30` | old reconciliation identity `D_TO=D_OB+D_TX` is stale | realized event and train-frozen reference are supported | event/reference inputs are supportable | derived jointly as `max(0, DELTA_OB+T_TX-taxi_reference)` | approved probability construction consumes aligned scenarios | PASS |
| taxi reference | required train-frozen term | NOT_LOCATED | Data2 direct airport-cell/global median contract exists | `DATA2_TAXI_REFERENCE@1.0.0` | sampling populates value, id, hash, fallback, and support; missing lookup abstains | warning probability refuses unsupported references | PASS |
| warning event | strict `D_TO > 30` | NOT_LOCATED | realized label support exists | PRE retains outcomes outside inference evidence | signed scenarios identify the event under frozen bin representatives | principal event frozen in config and model manifest | PASS_IMPLEMENTED_NOT_RUN |
| warning probability | weighted aligned-scenario frequency | NOT_LOCATED | data support sufficient | full legal Development cohort published/countable | typed probability result with node-level abstention | implementation complete; operating point not selected | PASS_IMPLEMENTED_NOT_RUN |
| sustained warning | two consecutive five-minute nodes | NOT_LOCATED | node grid supports it | 734 episodes have fewer than two legal nodes | no model change required | metric helper implements adjacent-step rule | PASS |
| Development cohort | full 2019-08-01 through 2019-09-30; no silent sample | NOT_LOCATED | corrected split-contained pool has 946,981 episodes | full PRE stream PASS, 13,608,096 nodes | inference not run | threshold/headline evaluation not run | PASS |
| Final Test isolation | October-December sealed | NOT_LOCATED | files exist but are excluded | all manifests report access count `0` | no test inference | no paper/full run | PASS |

## Current drift and unsupported items

```text
MANUSCRIPT_STALE_ITEMS = 1
CODE_DRIFT_ITEMS = 0
DATA_UNSUPPORTED_ITEMS = 0
```

- Stale manuscript-facing item: additive `D_TO=D_OB+D_TX` statement in the old conflict ledger.
- The signed M1 target, scenario, taxi-reference, and probability contracts now align.
- Data2 supplies the required realized event fields and train-frozen taxi reference.
- Full Development warning inference remains blocked on the warning operating-point protocol, not on data or model identifiability.

## Full Development inference gate

The final warning model is the single first-pre-registered-seed artifact, not a
three-seed ensemble. Full Development warning inference was not run and no new
runtime extrapolation was promoted from the small model-selection cohort.

Before full inference, the warning operating-point protocol still needs an
explicit scientific freeze for:

- whether the target FPR is episode-level or node-level;
- how probability-threshold ties are handled;
- how abstained nodes/episodes enter the FPR denominator;
- which registered Development scenario budget is principal versus numerical sensitivity.

```text
FULL_DEVELOPMENT_WARNING_INFERENCE = BLOCKED_PENDING_WARNING_OPERATING_POINT_PROTOCOL
FINAL_TEST_ACCESS_COUNT = 0
```
