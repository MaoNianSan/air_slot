# Decision-Margin Mechanism Diagnostic

Post-hoc mechanism diagnostic over the sealed canonical-v2 Final-Test epoch. Nothing is retrained, recalibrated, reselected or redefined.

- analysis: `DECISION_MARGIN_MECHANISM_DIAGNOSTIC` (`POST_HOC_MECHANISM_DIAGNOSTIC`)
- split: `FINAL_TEST`
- git head: `af93743e1b417319dc6aa5dc0f84c80cac4a9fc2`
- epoch root: `D:\research\air_slot\code\explore\artifacts\experiment\final_test_v2_stage_matched_canonical_v2`
- write mode: `STAGED_TRANSACTIONAL_MATERIALIZATION` (`FRESH_ATOMIC_RENAME`)
- stage-I primary capacity: `q = 0.1`; stage-II cohort: `FIXED_REFERENCE_STAGE_II_COHORT` with `N = 16`
- tolerances: margin strictness `1e-06` from `C.M3_NUMERICAL_COMPARISON_TOLERANCE`; objective replay `1e-06` from `C.M3_NUMERICAL_COMPARISON_TOLERANCE`

## Gates

| gate | result | evidence |
| --- | --- | --- |
| A repository authority | PASS | head `af93743` stable, 10 pre-existing untracked entries, 0 pre-existing tracked modifications, none introduced by this run |
| B stage-I authority replay | PASS | N {'PRE_IB': 29, 'POST_IB_PRE_OB': 127}, K {'PRE_IB': 3, 'POST_IB_PRE_OB': 13}, 624 scores corroborated against the sealed M4 rows |
| C-L1 HISTORY_JOINT curve replay | PASS | 160/160 points, max deviation 0 |
| C-L2 four-variant decision replay | PASS | 64/64 sealed actions reproduced |
| D margin materialization | PASS | stage-x-q cross-check ran (56 comparisons, max deviation 1.11e-16) |

## Stage-I diagnostics

`m` is the reference cutoff margin, `eps` the information-induced priority perturbation, `span` the additive-shift-insensitive perturbation span (`span <= 2*eps`, reported only and never used for a status), and `m - 2*eps` the certificate slack.

| comparison | stage | m | eps | span | m-2*eps | certificate | shortlist changed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CURRENT_JOINT__TO__HISTORY_JOINT | PRE | 0.204961 | 0.405344 | 0.539758 | -0.605728 | NOT_CERTIFIED | no |
| CURRENT_JOINT__TO__HISTORY_JOINT | TURN | 0.0305202 | 0.432971 | 0.69882 | -0.835421 | NOT_CERTIFIED | yes |
| HISTORY_POINT__TO__HISTORY_MARGINAL | PRE | 0.193871 | 1.30608 | 1.26641 | -2.41828 | NOT_CERTIFIED | yes |
| HISTORY_POINT__TO__HISTORY_MARGINAL | TURN | 0.0309228 | 1.83187 | 1.80636 | -3.63281 | NOT_CERTIFIED | yes |
| HISTORY_MARGINAL__TO__HISTORY_JOINT | PRE | 0.204961 | 0.147546 | 0.147546 | -0.0901318 | NOT_CERTIFIED | no |
| HISTORY_MARGINAL__TO__HISTORY_JOINT | TURN | 0.0305202 | 0.217427 | 0.285305 | -0.404333 | NOT_CERTIFIED | no |

`pairwise_reference_value`, `pairwise_alternative_value` and `pairwise_attention_loss` are the pair-specific diagnostic analogue of the attention-loss construction, computed with the frozen M4 objective under each pair's own reference basis. They are **not** the primary HISTORY_JOINT-referenced `L^att` and must never be reported as it.

## Stage-II diagnostics

Gap and perturbation statistics are medians over the fixed `R*` cohort unless `scope` narrows them. `changed` counts action changes; `NC` abbreviates `NOT_CERTIFIED`.

| comparison | scope | N | changed | median gamma | median eps | median span | certified stable | NC but stable | NC and changed | no strict margin | abstain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CURRENT_JOINT__TO__HISTORY_JOINT | ALL | 16 | 10 | 0.00749529 | 0.136313 | 0.0269127 | 0 | 6 | 10 | 0 | 0 |
| CURRENT_JOINT__TO__HISTORY_JOINT | PRE | 3 | 1 | 0.0087576 | 0.110508 | 0.0319273 | 0 | 2 | 1 | 0 | 0 |
| CURRENT_JOINT__TO__HISTORY_JOINT | TURN | 13 | 9 | 0.00718095 | 0.136421 | 0.024149 | 0 | 4 | 9 | 0 | 0 |
| HISTORY_POINT__TO__HISTORY_MARGINAL | ALL | 16 | 12 | 0.00933172 | 0.910511 | 0.118592 | 0 | 4 | 12 | 0 | 0 |
| HISTORY_POINT__TO__HISTORY_MARGINAL | PRE | 3 | 2 | 0.0121398 | 1.12552 | 0.125267 | 0 | 1 | 2 | 0 | 0 |
| HISTORY_POINT__TO__HISTORY_MARGINAL | TURN | 13 | 10 | 0.00780962 | 0.907736 | 0.103795 | 0 | 3 | 10 | 0 | 0 |
| HISTORY_MARGINAL__TO__HISTORY_JOINT | ALL | 16 | 1 | 0.00749529 | 2.77556e-16 | 4.44089e-16 | 13 | 2 | 1 | 0 | 0 |
| HISTORY_MARGINAL__TO__HISTORY_JOINT | PRE | 3 | 1 | 0.0087576 | 2.22045e-16 | 4.44089e-16 | 2 | 0 | 1 | 0 | 0 |
| HISTORY_MARGINAL__TO__HISTORY_JOINT | TURN | 13 | 0 | 0.00718095 | 3.33067e-16 | 4.44089e-16 | 11 | 2 | 0 | 0 | 0 |

## Stage x q consequence-boundary descriptor

Boundary location only. No delay-versus-consequence perturbation certificate is constructed anywhere in this diagnostic, because delay priority and consequence priority are not a perturbation pair on a shared numerical scale. `retained_value` is the published `retained_consequence_value` and `attention_loss` the published `L_att` of the Stage-x-q experiment; the frozen `STAGE_Q_SCREENING_SUMMARY.csv` is the authority for those columns.

| stage | q | N | K | consequence cutoff margin | changed positions | overlap rate | retained value | attention loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRE | 0.05 | 29 | 2 | 0.295529 | 1 | 0.5 | 0.878463 | 0.121537 |
| PRE | 0.1 | 29 | 3 | 0.204961 | 0 | 1 | 1 | 0 |
| PRE | 0.2 | 29 | 6 | 0.0235731 | 1 | 0.833333 | 0.993802 | 0.00619769 |
| PRE | 0.3 | 29 | 9 | 0.0303099 | 2 | 0.777778 | 0.955413 | 0.0445874 |
| TURN | 0.05 | 127 | 7 | 0.0561678 | 4 | 0.428571 | 0.776353 | 0.223647 |
| TURN | 0.1 | 127 | 13 | 0.0305202 | 5 | 0.615385 | 0.92757 | 0.0724303 |
| TURN | 0.2 | 127 | 26 | 0.0135881 | 8 | 0.692308 | 0.939 | 0.0609995 |
| TURN | 0.3 | 127 | 39 | 0.004792 | 9 | 0.769231 | 0.950053 | 0.0499475 |

## Reading rules

- The certificates are **sufficient** stability certificates, never necessary conditions. `NOT_CERTIFIED` says the certificate is inconclusive; it never predicts or implies a changed decision, and the `N_not_certified_but_stable` counts exist precisely because that case is expected.
- `CERTIFIED_STABLE` must correspond to an empirically stable decision. A `CERTIFIED_STABLE` row with a changed decision would indicate an implementation error in the formula, the score orientation, the ranking direction, the tie-breaking, the objective orientation or the common-support construction, and blocks the run instead of being reported.
- A certificate is a mechanism diagnostic, not a classifier: no accuracy, precision, recall, F1, ROC or AUC is computed, and no such field exists in any artifact schema.
- The manifest deliberately does not contain its own SHA256 (`SELF_REFERENTIAL_HASH_NOT_DEFINED`): its hash would have to include itself, which is not a well-defined value. `output_artifact_hashes` therefore covers the seven payload artifacts only, and the manifest is listed in `output_artifact_paths` alone.

