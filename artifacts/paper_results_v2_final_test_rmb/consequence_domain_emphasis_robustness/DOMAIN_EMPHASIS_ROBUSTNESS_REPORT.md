# Consequence-domain emphasis robustness (post-hoc)

`CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS` -- a read-only projection over the sealed canonical-v2 Final-Test epoch. Descriptive robustness only: no significance testing, no confidence interval, no threshold and no claim.

## Declarations

* `primary_profile` = `BALANCED`
* `primary_weight_profile_changed` = `False`
* `weights_reselected` = `False`
* `weights_learned` = `False`
* `weights_calibrated` = `False`
* `expert_elicitation_used` = `False`
* `model_retrained` = `False`
* `model_recalibrated` = `False`
* `parameter_reselected` = `False`
* `final_test_cohort_changed` = `False`
* `stage2_reference_cohort` = `R_STAR`
* `stage2_N` = `16`
* `stage1_q` = `0.1`
* `stage1_stage_q_grid_rerun` = `False`
* `consequence_components_changed` = `False`
* `component_normalization_changed` = `False`
* `bootstrap_used` = `False`
* `significance_testing_used` = `False`
* `robustness_threshold_defined` = `False`
* `decision_margin_quantities_reported` = `False`

## Gates

| gate | status | evidence |
| --- | --- | --- |
| B | PASS | 952/952 sealed consequence priorities; 6 sealed Stage-I comparators; PRE 29/3, TURN 127/13 |
| C | PASS | 160/160 objective points; 64/64 sealed actions; 64 profile-basis cases; 3 sealed recovery comparators |
| D | PASS | PRIMARY_BALANCED_ARTIFACTS_UNCHANGED; R* 16 (PRE 3 / TURN 13); head stable True; 46 paper-result files fingerprinted unchanged |

Gate A status: `PASS` (unexpected tracked modifications at run start: 0; declared implementation modifications: 1).

## A. Do domain emphases materially change the consequence shortlist?

| stage | profile_id | N | K | shortlist_overlap_count | shortlist_overlap_rate | changed_positions | entered_count | displaced_count | balanced_retained_value | balanced_attention_loss | profile_retained_value | profile_attention_loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRE_IB | FLIGHT_EMPHASIS | 29 | 3 | 3 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| POST_IB_PRE_OB | FLIGHT_EMPHASIS | 127 | 13 | 12 | 0.923077 | 1 | 1 | 1 | 0.995316 | 0.00468367 | 0.997524 | 0.00247607 |
| PRE_IB | PASSENGER_EMPHASIS | 29 | 3 | 3 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| POST_IB_PRE_OB | PASSENGER_EMPHASIS | 127 | 13 | 11 | 0.846154 | 2 | 2 | 2 | 0.989914 | 0.0100861 | 0.993643 | 0.00635688 |
| PRE_IB | RESOURCE_EMPHASIS | 29 | 3 | 3 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| POST_IB_PRE_OB | RESOURCE_EMPHASIS | 127 | 13 | 12 | 0.923077 | 1 | 1 | 1 | 0.991771 | 0.00822893 | 0.988708 | 0.011292 |

Both directions are reported per row: the balanced basis evaluates the emphasis shortlist (`balanced_*`), and the profile basis evaluates the balanced shortlist (`profile_*`).

## B. Does the Delay-vs-Consequence finding persist?

| stage | profile_id | N | K | delay_consequence_overlap | delay_consequence_changed_positions | profile_reference_consequence_value | delay_shortlist_consequence_value | retained_value | attention_loss | attention_loss_note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRE_IB | BALANCED | 29 | 3 | 3 | 0 | 3.26159 | 3.26159 | 1 | 0 | MACHINE_PRECISION_ONLY_IDENTICAL_SHORTLIST_SUMMATION_ORDER_ARTIFACT_NOT_A_DECISION_LOSS |
| POST_IB_PRE_OB | BALANCED | 127 | 13 | 8 | 5 | 13.502 | 12.524 | 0.92757 | 0.0724303 |  |
| PRE_IB | FLIGHT_EMPHASIS | 29 | 3 | 3 | 0 | 2.95695 | 2.95695 | 1 | 1.50185e-16 | MACHINE_PRECISION_ONLY_IDENTICAL_SHORTLIST_SUMMATION_ORDER_ARTIFACT_NOT_A_DECISION_LOSS |
| POST_IB_PRE_OB | FLIGHT_EMPHASIS | 127 | 13 | 9 | 4 | 12.1022 | 11.5346 | 0.953099 | 0.0469008 |  |
| PRE_IB | PASSENGER_EMPHASIS | 29 | 3 | 3 | 0 | 4.12526 | 4.12526 | 1 | 0 | MACHINE_PRECISION_ONLY_IDENTICAL_SHORTLIST_SUMMATION_ORDER_ARTIFACT_NOT_A_DECISION_LOSS |
| POST_IB_PRE_OB | PASSENGER_EMPHASIS | 127 | 13 | 7 | 6 | 17.7091 | 16.1271 | 0.910669 | 0.0893313 |  |
| PRE_IB | RESOURCE_EMPHASIS | 29 | 3 | 3 | 0 | 2.70256 | 2.70256 | 1 | -1.64322e-16 | MACHINE_PRECISION_ONLY_IDENTICAL_SHORTLIST_SUMMATION_ORDER_ARTIFACT_NOT_A_DECISION_LOSS |
| POST_IB_PRE_OB | RESOURCE_EMPHASIS | 127 | 13 | 8 | 5 | 10.961 | 9.91037 | 0.904152 | 0.0958484 |  |

These `attention_loss` values are profile-specific Delay-vs-Consequence attention losses. They do **not** replace the primary `BALANCED` headline, which Gate B reproduced against the sealed projection.

## C. Does priority remain distinct from local recoverability?

| profile_id | exact_action_count | exact_action_rate | N_action_changed | N_increased_recovery | N_decreased_recovery | median_abs_action_change | max_abs_action_change | balanced_objective_regret_of_profile_action | profile_objective_regret_of_balanced_action | balanced_total_recoverable_value | profile_total_recoverable_value |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FLIGHT_EMPHASIS | 15 | 0.9375 | 1 | 0 | 1 | 0 | 15 | 0.00681739 | 0.00641423 | 0.414062 | 0.42304 |
| PASSENGER_EMPHASIS | 16 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.414062 | 0.653903 |
| RESOURCE_EMPHASIS | 8 | 0.5 | 8 | 0 | 8 | 2.5 | 20 | 0.0463351 | 0.0416376 | 0.414062 | 0.213295 |

| profile_id | stage2_shortlisted_chains_with_zero_action | stage2_shortlisted_chains_with_positive_recoverable_value | stage2_activated_chains |
| --- | --- | --- | --- |
| BALANCED | 3 | 13 | 13 |
| FLIGHT_EMPHASIS | 3 | 13 | 13 |
| PASSENGER_EMPHASIS | 3 | 13 | 13 |
| RESOURCE_EMPHASIS | 11 | 5 | 5 |

Interpretation priority for this section: action agreement and the two directional objective regrets. `total_recoverable_value` is descriptive only -- each profile defines its own consequence objective, so a larger total under one profile is not superior welfare across profiles.

## D. Does the information-value ordering persist?

### Stage-I screening (`P^C` retention of each comparator shortlist)

| stage | profile_id | comparator_variant | N_common | K | shortlist_identical | changed_positions | overlap_rate | retained_value | attention_loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRE_IB | BALANCED | CURRENT_JOINT | 29 | 3 | True | 0 | 1 | 1 | 0 |
| PRE_IB | BALANCED | HISTORY_POINT | 29 | 3 | False | 3 | 0 | 0.35427 | 0.64573 |
| PRE_IB | BALANCED | HISTORY_MARGINAL | 29 | 3 | True | 0 | 1 | 1 | 0 |
| POST_IB_PRE_OB | BALANCED | CURRENT_JOINT | 127 | 13 | False | 3 | 0.769231 | 0.976933 | 0.0230668 |
| POST_IB_PRE_OB | BALANCED | HISTORY_POINT | 127 | 13 | False | 11 | 0.153846 | 0.463813 | 0.536187 |
| POST_IB_PRE_OB | BALANCED | HISTORY_MARGINAL | 127 | 13 | False | 0 | 1 | 1 | 0 |
| PRE_IB | FLIGHT_EMPHASIS | CURRENT_JOINT | 29 | 3 | True | 0 | 1 | 1 | 0 |
| PRE_IB | FLIGHT_EMPHASIS | HISTORY_POINT | 29 | 3 | False | 3 | 0 | 0.364074 | 0.635926 |
| PRE_IB | FLIGHT_EMPHASIS | HISTORY_MARGINAL | 29 | 3 | True | 0 | 1 | 1 | 0 |
| POST_IB_PRE_OB | FLIGHT_EMPHASIS | CURRENT_JOINT | 127 | 13 | False | 3 | 0.769231 | 0.986145 | 0.013855 |
| POST_IB_PRE_OB | FLIGHT_EMPHASIS | HISTORY_POINT | 127 | 13 | False | 12 | 0.0769231 | 0.475666 | 0.524334 |
| POST_IB_PRE_OB | FLIGHT_EMPHASIS | HISTORY_MARGINAL | 127 | 13 | True | 0 | 1 | 1 | 0 |
| PRE_IB | PASSENGER_EMPHASIS | CURRENT_JOINT | 29 | 3 | True | 0 | 1 | 1 | 0 |
| PRE_IB | PASSENGER_EMPHASIS | HISTORY_POINT | 29 | 3 | False | 3 | 0 | 0.277244 | 0.722756 |
| PRE_IB | PASSENGER_EMPHASIS | HISTORY_MARGINAL | 29 | 3 | True | 0 | 1 | 1 | 0 |
| POST_IB_PRE_OB | PASSENGER_EMPHASIS | CURRENT_JOINT | 127 | 13 | False | 3 | 0.769231 | 0.957719 | 0.0422808 |
| POST_IB_PRE_OB | PASSENGER_EMPHASIS | HISTORY_POINT | 127 | 13 | False | 12 | 0.0769231 | 0.362085 | 0.637915 |
| POST_IB_PRE_OB | PASSENGER_EMPHASIS | HISTORY_MARGINAL | 127 | 13 | False | 1 | 0.923077 | 0.997997 | 0.00200293 |
| PRE_IB | RESOURCE_EMPHASIS | CURRENT_JOINT | 29 | 3 | True | 0 | 1 | 1 | 0 |
| PRE_IB | RESOURCE_EMPHASIS | HISTORY_POINT | 29 | 3 | False | 3 | 0 | 0.461119 | 0.538881 |
| PRE_IB | RESOURCE_EMPHASIS | HISTORY_MARGINAL | 29 | 3 | True | 0 | 1 | 1 | 0 |
| POST_IB_PRE_OB | RESOURCE_EMPHASIS | CURRENT_JOINT | 127 | 13 | False | 6 | 0.538462 | 0.894915 | 0.105085 |
| POST_IB_PRE_OB | RESOURCE_EMPHASIS | HISTORY_POINT | 127 | 13 | False | 10 | 0.230769 | 0.592223 | 0.407777 |
| POST_IB_PRE_OB | RESOURCE_EMPHASIS | HISTORY_MARGINAL | 127 | 13 | False | 0 | 1 | 1 | 0 |

### Stage-II local recovery (`HISTORY_JOINT` reference)

| profile_id | comparator_variant | N | exact_action_count | exact_action_rate | within_five_count | within_five_rate | missed_activation_count | false_activation_count | under_recovery_count | over_recovery_count | L_rec | delta_recovery_objective | reference_recoverable_value | comparator_total_reference_value | retained_value |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BALANCED | CURRENT_JOINT | 16 | 6 | 0.375 | 13 | 0.8125 | 6 | 1 | 2 | 1 | 0.907016 | 0.375561 | 0.414062 | 0.0385013 | 0.0929843 |
| BALANCED | HISTORY_POINT | 16 | 4 | 0.25 | 14 | 0.875 | 12 | 0 | 0 | 0 | 0.953642 | 0.394867 | 0.414062 | 0.0191952 | 0.0463583 |
| BALANCED | HISTORY_MARGINAL | 16 | 15 | 0.9375 | 15 | 0.9375 | 0 | 0 | 1 | 0 | 0.0164647 | 0.00681739 | 0.414062 | 0.407245 | 0.983535 |
| FLIGHT_EMPHASIS | CURRENT_JOINT | 16 | 10 | 0.625 | 14 | 0.875 | 3 | 1 | 1 | 1 | 0.687446 | 0.290817 | 0.42304 | 0.132223 | 0.312554 |
| FLIGHT_EMPHASIS | HISTORY_POINT | 16 | 4 | 0.25 | 15 | 0.9375 | 12 | 0 | 0 | 0 | 0.930991 | 0.393846 | 0.42304 | 0.0291935 | 0.0690089 |
| FLIGHT_EMPHASIS | HISTORY_MARGINAL | 16 | 16 | 1 | 16 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.42304 | 0.42304 | 1 |
| PASSENGER_EMPHASIS | CURRENT_JOINT | 16 | 7 | 0.4375 | 12 | 0.75 | 4 | 1 | 2 | 2 | 0.926433 | 0.605797 | 0.653903 | 0.0481055 | 0.0735667 |
| PASSENGER_EMPHASIS | HISTORY_POINT | 16 | 4 | 0.25 | 14 | 0.875 | 12 | 0 | 0 | 0 | 0.967977 | 0.632963 | 0.653903 | 0.0209402 | 0.0320234 |
| PASSENGER_EMPHASIS | HISTORY_MARGINAL | 16 | 15 | 0.9375 | 15 | 0.9375 | 0 | 0 | 1 | 0 | 0.0651269 | 0.0425867 | 0.653903 | 0.611316 | 0.934873 |
| RESOURCE_EMPHASIS | CURRENT_JOINT | 16 | 10 | 0.625 | 14 | 0.875 | 2 | 2 | 1 | 1 | 1.35197 | 0.28837 | 0.213295 | -0.0750744 | -0.351974 |
| RESOURCE_EMPHASIS | HISTORY_POINT | 16 | 11 | 0.6875 | 15 | 0.9375 | 5 | 0 | 0 | 0 | 1 | 0.213295 | 0.213295 | 0 | 0 |
| RESOURCE_EMPHASIS | HISTORY_MARGINAL | 16 | 14 | 0.875 | 16 | 1 | 0 | 2 | 0 | 0 | 0.0305883 | 0.00652434 | 0.213295 | 0.206771 | 0.969412 |

## E. Exceptions

* `STAGE2_INFORMATION_LOSS_ORDERING_CHANGED:RESOURCE_EMPHASIS:['CURRENT_JOINT', 'HISTORY_POINT', 'HISTORY_MARGINAL']:BALANCED:['HISTORY_POINT', 'CURRENT_JOINT', 'HISTORY_MARGINAL']`

## Robustness interpretation questions

**RQ-R1 -- Does Delay-vs-Consequence screening retain the same qualitative stage pattern under all three domain-emphasis scenarios?** Facts: BALANCED/PRE_IB overlap=3 of 3, changed=0, retained=1.0; BALANCED/POST_IB_PRE_OB overlap=8 of 13, changed=5, retained=0.9275697132482993; FLIGHT_EMPHASIS/PRE_IB overlap=3 of 3, changed=0, retained=0.9999999999999999; FLIGHT_EMPHASIS/POST_IB_PRE_OB overlap=9 of 13, changed=4, retained=0.9530991905236388; PASSENGER_EMPHASIS/PRE_IB overlap=3 of 3, changed=0, retained=1.0; PASSENGER_EMPHASIS/POST_IB_PRE_OB overlap=7 of 13, changed=6, retained=0.910668652274626; RESOURCE_EMPHASIS/PRE_IB overlap=3 of 3, changed=0, retained=1.0000000000000002; RESOURCE_EMPHASIS/POST_IB_PRE_OB overlap=8 of 13, changed=5, retained=0.9041516359016134.

**RQ-R2 -- Does the distinction between recovery priority and positive local recoverability remain present?** Facts: BALANCED: shortlisted chains with u*=0 = 3, positive-recovery chains = 13, activated = 13; FLIGHT_EMPHASIS: shortlisted chains with u*=0 = 3, positive-recovery chains = 13, activated = 13; PASSENGER_EMPHASIS: shortlisted chains with u*=0 = 3, positive-recovery chains = 13, activated = 13; RESOURCE_EMPHASIS: shortlisted chains with u*=0 = 11, positive-recovery chains = 5, activated = 5.

**RQ-R3 -- Does HISTORY_POINT remain materially less decision-preserving than the richer distributional representations?** Facts (Stage-II L_rec): BALANCED: HP=0.9536416660613012, HJ=0, HM=0.016464660023900957, CJ=0.9070157057407199; FLIGHT_EMPHASIS: HP=0.9309911026373813, HJ=0, HM=0.0, CJ=0.6874456680240977; PASSENGER_EMPHASIS: HP=0.9679766009532227, HJ=0, HM=0.06512693896528317, CJ=0.9264332759709661; RESOURCE_EMPHASIS: HP=1.0, HJ=0, HM=0.03058833205385258, CJ=1.351974087618347.

**RQ-R4 -- Does HISTORY_MARGINAL remain close to HISTORY_JOINT?** Facts: BALANCED: L_rec(HM) = 0.016464660023900957, action agreement = 15/16; FLIGHT_EMPHASIS: L_rec(HM) = 0.0, action agreement = 16/16; PASSENGER_EMPHASIS: L_rec(HM) = 0.06512693896528317, action agreement = 15/16; RESOURCE_EMPHASIS: L_rec(HM) = 0.03058833205385258, action agreement = 14/16.

## Reading rules

* `BALANCED` is the only primary specification and the only primary headline; every emphasis row is a symmetric stress-test scenario.
* Field aliases: `attention_loss` equals the canonical `L_att` (Stage-I) and the canonical `L_rec` (Stage-II); `retained_value` equals `1 - attention_loss`; `exact_action_rate` is `A0` and `within_five_rate` is `A5`. Canonical names are used wherever the repository defines one.
* `RESOURCE_EMPHASIS` emphasises the `R_operating` domain. It is formula-identical to the legacy development-lane `OPERATING_EMPHASIS` view, but it is computed on the sealed M2 CU vector under the v2 aggregation interface; the two are not interchangeable.
* No stability certificate, margin, epsilon, span or perturbation quantity is produced here, and no robustness threshold is applied.
* Per-chain audit: see `DOMAIN_EMPHASIS_STAGE2_CHAIN_RECORDS.parquet` (`PROFILE_ACTION`, `COMPARATOR_ACTION`, `HJ_PREFERENCE`) and `DOMAIN_EMPHASIS_STAGE1_CHAIN_RECORDS.parquet`.

## Interpretation boundary for the manuscript

> We examined three symmetric domain-emphasis scenarios that placed greater weight on flight, passenger, or operating-resource consequences while leaving the underlying consequence construction unchanged.

> These scenarios are robustness checks rather than empirically elicited airline utility weights.

* No manuscript claim is emitted by this artifact. The qualitative stability, magnitude and direction of the observed differences are reported as facts only.

