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
| `H_STAR` | frozen Development choice `32` | NOT_LOCATED | not data-limited | typed PRE cache unchanged | config/pipeline use `32` | historical H runner moved to exp; no rerun | PASS |
| `W_STAR` | frozen fixed window `30` minutes | NOT_LOCATED | not data-limited | canonical five-minute nodes | M1 closed `[t-30,t]` history API | historical W runner moved to exp; no rerun | PASS |
| history semantics | CURRENT node; FIXED closed current-episode interval; ADAPTIVE full current-episode prefix | NOT_LOCATED | PRE supplies legal episode grid | episode-bounded causal membership | `model/M1/history.py` owns all transformations | exp imports/invokes only | PASS |
| Data2 schedule reference | same across variants | NOT_LOCATED | official CRS schedule fields | canonical schedule reference with decision-time publication | signed time-to-schedule feature; labels use scheduled departure | no raw schedule handling | PASS |
| `R_IB` | same target across variants | NOT_LOCATED | predecessor actual arrival available post hoc | typed outcome retained outside inference state | nonnegative remaining-to-in-block label | consumed, not redefined | PASS |
| `R_OB` | same target across variants | NOT_LOCATED | actual and scheduled departure supported | typed schedule/outcome available | `max(0, actual_departure-scheduled_departure)` | consumed, not redefined | PASS |
| `T_TX` | same target across variants | NOT_LOCATED | official `TaxiOut` supported | typed post-hoc taxi-out and train-frozen direct reference supported | ordered nonnegative taxi duration head | consumed, not redefined | PASS |
| `D_TO` | principal warning event names `D_TO_POST_GT_30` | old reconciliation identity `D_TO=D_OB+D_TX` is stale | realized event can be built, but current M1 outputs lose signed departure offset | event/reference inputs are supportable | exact tail not identified from current heads | no approved probability construction | AMBIGUOUS_REQUIRES_HUMAN_DECISION |
| taxi reference | required train-frozen term | NOT_LOCATED | Data2 direct airport-cell/global median contract exists | `DATA2_TAXI_REFERENCE@1.0.0` | optional scenario field exists but current sampling does not populate it | lookup/probability contract absent | CODE_DRIFT |
| warning event | `D_TO > 30` | NOT_LOCATED | realized label support exists | PRE does not define experiment outcome | exact predictive event unavailable | config name exists only | AMBIGUOUS_REQUIRES_HUMAN_DECISION |
| warning probability | fixed-FPR Development selection intended | NOT_LOCATED | data alone is sufficient | full legal Development cohort now published/countable | no exact current tail distribution | not implemented/approved | AMBIGUOUS_REQUIRES_HUMAN_DECISION |
| sustained warning | two consecutive five-minute nodes | NOT_LOCATED | node grid supports it | 734 episodes have fewer than two legal nodes | no model change required | metric helper implements adjacent-step rule | PASS |
| Development cohort | full 2019-08-01 through 2019-09-30; no silent sample | NOT_LOCATED | 1,264,440 source rows; 951,359 episodes | full PRE stream PASS, 13,721,540 nodes | inference not run | threshold/headline evaluation not run | PASS |
| Final Test isolation | October-December sealed | NOT_LOCATED | files exist but are excluded | all manifests report access count `0` | no test inference | no paper/full run | PASS |

## Current drift and unsupported items

```text
MANUSCRIPT_STALE_ITEMS = 1
CODE_DRIFT_ITEMS = 2
DATA_UNSUPPORTED_ITEMS = 0
```

- Stale manuscript-facing item: additive `D_TO=D_OB+D_TX` statement in the old conflict ledger.
- Code drift item 1: optional taxi-reference/event-time scenario fields are not populated by current M1 sampling.
- Code drift item 2: Exp1 names an exact D_TO warning event without an identifiable current probability implementation.
- Data2 supplies the required realized event fields and train-frozen taxi reference; the blocker is the model/probability contract, not raw-data support.

## Full Development inference estimate

Frozen W30 evidence reports mean Development inference time `0.507226` seconds
for `1,782` cached Development examples. Linear scaling to `13,721,540`
PRE-eligible nodes gives:

- one W30 checkpoint: approximately `3,905.7` seconds (`65.1` minutes);
- three-checkpoint ensemble: approximately `11,717.0` seconds (`195.3` minutes).

This estimate excludes any additional full-cohort M1 feature-materialization and
artifact-writing overhead. Full warning inference was not run.
