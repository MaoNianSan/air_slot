# AirSlot V2 - Section 5 Final-Test paper-facing views

Generated only from the persisted Phase-7 checkpoints (`artifacts/experiment/final_test_v2/checkpoints/`). No decision, metric or estimand is recomputed here; every number is read from the Stage-I, Stage-II, M4 or bootstrap payloads.

**Reference vs comparators.** `HISTORY_JOINT` is the reference representation (`H_g^{C,*} = H_g^{C,History+Joint}`, `R_g*` fixed at 166 support-qualified nodes). Its self-comparison identity (`L_att=0`, `L_rec=0`, `A0=A5=1`) is an identity check, **not** a comparator result. Comparator numbers are reported separately below.

## Section 5.2 - Stage-I attention (stage x q primary design)

| q | K = ceil(qN) | cohort | selected | PRE | TURN | abstaining |
|---|---|---|---|---|---|---|
| 0.05 | 83 | 1656 | 83 | 11 | 72 | 0 |
| 0.1 | 166 | 1656 | 166 | 13 | 153 | 0 |
| 0.2 | 332 | 1656 | 332 | 18 | 314 | 0 |
| 0.3 | 497 | 1656 | 497 | 26 | 471 | 0 |

Reference variant `HISTORY_JOINT`; `q` is the Section 5.2 operating axis, never an OFAT sensitivity axis.

## Section 5.3 - Stage-II recovery decisions (nominal specification)

| variant | cohort | u*=0 | mean u* | max u* | V>0 | mean V | sum V |
|---|---|---|---|---|---|---|---|
| HISTORY_JOINT | 166 | 68 | 3.7048 | 40.0 | 98 | 0.011666 | 1.936577 |
| CURRENT_JOINT | 166 | 90 | 4.006 | 45.0 | 76 | 0.013328 | 2.212484 |
| HISTORY_POINT | 166 | 164 | 0.0602 | 5.0 | 2 | 3.4e-05 | 0.005681 |
| HISTORY_MARGINAL | 166 | 68 | 3.4337 | 40.0 | 98 | 0.013053 | 2.16685 |

Every actionable row is the frozen exact enumeration over `{0,5,...,45}` (`solver_status=EXACT_ENUMERATION`, `row_parity_checks_executed=0`); comparator rows are that variant's own optimum, never a copy of the reference action.

## Section 5.4 - M4 common-basis comparison on `R_g*`

| comparator | L_att | L_att 95% CI | L_rec | L_rec 95% CI | A0 | A5 | exact/within-5 |
|---|---|---|---|---|---|---|---|
| CURRENT_JOINT | 0.026904 | [-0.151522, 0.223335] | 0.819601 | [0.149536, 2.126201] | 0.650602 | 0.921687 | 108/153 of 166 |
| HISTORY_POINT | 0.593794 | [-0.164235, 0.831861] | 0.978742 | [0.952011, 1.000000] | 0.421687 | 0.957831 | 70/159 of 166 |
| HISTORY_MARGINAL | 0.001005 | [-0.033606, 0.032653] | 0.038177 | [0.000000, 0.142590] | 0.969880 | 0.969880 | 161/161 of 166 |

Reference self-comparison (`HISTORY_JOINT`): `L_att = 0.0`, `L_rec = 0.0`, `A0 = A5 = 1.0`, exact actions 166/166 - identity by construction, not a comparator outcome. `L_total` is never constructed; monetary conversion stays secondary interpretation only.

## Section 5.5 - Predefined sensitivity scope

| axis | nominal | grid | status |
|---|---|---|---|
| lambda | 0.25 | [0.1, 0.25, 0.5, 1.0] | FROZEN_SENSITIVITY_AXIS_DECLARED |
| turnaround_lower_bound_q | 41.0 | [34.0, 41.0, 47.0] | FROZEN_SENSITIVITY_AXIS_DECLARED |
| u_max | 45.0 | [25.0, 45.0, 75.0] | FROZEN_SENSITIVITY_AXIS_DECLARED |
| history_capacity | 16 | [8, 16] | FROZEN_SENSITIVITY_AXIS_DECLARED |
| similar_delay_5_10_15 | - | - | NOT_ACTIVATED_BY_PHASE6_FREEZE |
| itinerary_threshold_30_60 | - | - | NOT_ACTIVATED_BY_PHASE6_FREEZE |
| service_threshold_150_210 | - | - | NOT_ACTIVATED_BY_PHASE6_FREEZE |
| fixed_window_history | - | - | NOT_AVAILABLE_NOT_FROZEN |

`sensitivity_results_status = DECLARED_SCOPE_ONLY_NO_SENSITIVITY_RESULTS_IN_THIS_RUN` - the frozen OFAT axes are declared, and no Final-Test sensitivity run is persisted in this single-shot execution. Producing them would require a new Final-Test access epoch and is not authorized.

Fixed-window history stays `NOT_AVAILABLE_NOT_FROZEN`; no substitute model is trained.
