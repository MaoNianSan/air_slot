# ROUND2_TRANCHE3_FULL_BEFORE

- Audit date: 2026-08-20
- Repository HEAD at restart: `66002114d85e575f5b6a89bac545843949c08e59`
- Scope: actual execution path `Data2 -> PRE -> PREState -> M1 adapter -> r_fast -> network -> calibration -> forecast -> scenario sampler`
- Boundary: no M2 implementation, Final Test, paper experiment, commit, or push.

This audit inspected code, contracts, registries, services, pipelines, and tests. The
worktree already contained an uncommitted tranche3 candidate implementation when
the audit began; those changes were treated as candidate code and verified rather
than assumed correct.

## Findings before closure

| Execution point | Classification | Finding |
|---|---|---|
| Primitive graph and derived identities | ALIGNED | Principal graph is `T_IB_A00 -> D_OB -> D_TX`; `R_IB=max(0,T_IB_A00-t)` and samplewise `D_TO=D_OB+D_TX` remain derived. |
| `M1Service.predict_now` and scenario information state | ALIGNED | Candidate worktree code routed both through `_information_state`, which derives `r_fast` from the last legal sequence row and accepts PRE-published `c_static`. |
| Hazard calibration | ALIGNED | Candidate implementation used discrete-hazard event-time likelihood and filtered inactive `label=-1` rows before interval lookup. No multiclass CE path was used. |
| Hurdle zero-mass calibration | ALIGNED | D_OB and D_TX zero logits had independent binary-CE temperatures; positive quantile logits/values were not temperature-scaled. |
| Calibration artifact | CODE_STALE | `M1CalibrationContract` existed, but version/split/policy and positive-quantile coverage diagnostics were not persisted with the model artifact. |
| Scenario taxi-reference lineage | CODE_STALE | Production scenario provenance depended on the caller re-supplying the taxi reference object even when PRE had already published the frozen reference. |
| Production observed-state boundary | CODE_STALE | `M1Service.generate_scenarios` allowed an arbitrary caller-provided `observed` dictionary, permitting bypass of PRE legality checks. |
| Factual legality predicate | CODE_STALE | The candidate checked `availability_time <= cutoff`; it did not independently reject an inconsistent record whose `event_time > cutoff`. |
| Turnaround reference lookup | CODE_STALE | Static publication looked up turnaround by successor destination rather than the connection airport/successor origin. |
| Static/reference typed object | CODE_STALE | PRE values existed, but `M1StaticReferenceField` retained only status/reference metadata rather than the self-contained value, unit, support, provenance, reference id, freeze id, and fallback level. |
| Data2 carrier and aircraft identity | ALIGNED | BTS `Reporting_Airline` and `Tail_Number` were retained in the canonical schedule; tail identity was never ordinal-encoded. |
| Route/carrier numeric encodings | SCIENTIFIC_GATE | Identities/context are published, but deterministic numeric encodings are not frozen; they remain `MODEL_FEATURE_PENDING`, not `UNSUPPORTED`. |
| Data2 factual availability rule | SCIENTIFIC_GATE | BTS has no true airline-message arrival timestamp. Formal policy remains `UNRESOLVED / HUMAN_DECISION_REQUIRED`; architecture may execute only an explicitly declared retrospective rule. |
| Positive tail and quantile grid | SCIENTIFIC_GATE | `M1_POSITIVE_TAIL_DECISION_REQUIRED`; the development quantile grid is not promoted. |
| Forecast horizon execution contract | SCIENTIFIC_GATE | `MANUSCRIPT_REQUIREMENT_CLEAR / CODE_LABEL_EXECUTION_CONTRACT_INCOMPLETE`; this tranche does not add a new `tau={0,15,60}` label/execution dimension. |
| Frozen PRE reference supply | UPSTREAM_INTERFACE_REQUIRED | A production caller must supply already train-frozen turnaround/taxi artifacts to PRE; this tranche does not refit or freeze them. |
| Formal FAST fitted artifact | UPSTREAM_INTERFACE_REQUIRED | FAST architecture is executable in development, but no train-frozen production FAST artifact is registered; principal inference continues to abstain. |

All `CODE_STALE` items above are in scope for direct repair. Scientific and
upstream gates remain explicit and are not silently resolved.

`FINAL_TEST_ACCESS_COUNT = 0`.
