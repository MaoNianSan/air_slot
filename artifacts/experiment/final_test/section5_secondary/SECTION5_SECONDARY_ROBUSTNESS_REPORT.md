# Section 5 Secondary Robustness Report

Status: SECONDARY_REPORTING_COMPLETE_HUMAN_REVIEW_REQUIRED

Reporting-only derivation of the existing held-out Final Test. No model, calibration, weights, thresholds, primary estimand, canonical events, stage cohort, or manuscript was changed.

- HEAD_START: `860befd20e968ba702b1aad99e618830a3a6acfe`
- HEAD_END: `860befd20e968ba702b1aad99e618830a3a6acfe`
- Frozen Final Test access count remains 1; no new raw-data opening.
- All three point estimates reconcile at rtol=0, atol=1e-12.
- All 2,000 primary 5-min bootstrap rows and headline CIs reconcile with their existing frozen counterparts.

## Exp2 Similar-Delay Sensitivity

| Caliper (min) | Episode pairs | Median separation [95% CI] | Share separation >= 0.30, % [95% CI] |
|---:|---:|---:|---:|
| 5 | 7045 | 0.2041 [0.1806, 0.2343] | 33.7828 [27.9314, 39.4977] |
| 10 | 7943 | 0.2711 [0.2539, 0.2942] | 45.8769 [42.8239, 49.2402] |
| 15 | 8029 | 0.2829 [0.2681, 0.3012] | 47.4530 [45.0589, 50.1736] |

Bootstrap: original-episode clusters, 2,000 replicates, seed 20260906, percentile 95% intervals. The complete ranked sample is restored from EXP2A_NODE_RECORDS; stored scores and common support are unchanged. Point reconstruction calls the existing pair builder, episode-pair aggregation, and summary functions.

The existing primary optimized bootstrap backend caches only invariant qualifying node membership. Each draw rebuilds ranks and cross-original-episode bootstrap-occurrence pairs, recomputes node rank gaps and episode-pair medians, and then computes pair-balanced summaries. This is not resampling a frozen list of pair-level gaps. The original draw order is retained when execution is split into worker chunks. All calipers use the same frozen episode draw plan.

## Exp4 Appendix Capacity Summary

Exact source-field projection; Exp4 and its bootstrap were not rerun. Values below are display-rounded only. The CSV preserves every selected source field verbatim. Reassigned rate is shown as a fraction; capture differences are percentage points.

| Stage | q | N | K | Reassigned rate [95% CI] | Delta Capture F (pp) [95% CI] | Delta Capture P (pp) [95% CI] | Delta Capture R (pp) [95% CI] |
|---|---:|---:|---:|---:|---:|---:|---:|
| PRE_IB | 0.05 | 29 | 2 | 0.5000 [0.0000, 1.0000] | -2.5167 [-4.1378, 0.0000] | 0.7056 [-3.5887, 7.6244] | 3.9112 [0.0000, 12.2841] |
| PRE_IB | 0.10 | 29 | 3 | 0.0000 [0.0000, 0.7500] | 0.0000 [-4.7508, 0.0000] | 0.0000 [-5.5915, 5.1101] | 0.0000 [0.0000, 19.1815] |
| PRE_IB | 0.20 | 29 | 6 | 0.1667 [0.0000, 0.6000] | -1.6291 [-7.5099, 0.0000] | -3.5740 [-7.7846, 4.6796] | 6.9978 [0.0000, 26.8084] |
| PRE_IB | 0.30 | 29 | 9 | 0.2222 [0.0000, 0.4557] | -4.4519 [-8.7459, 0.0000] | 0.6300 [-6.3973, 6.9729] | 12.9169 [0.0000, 29.9252] |
| POST_IB_PRE_OB | 0.05 | 127 | 7 | 0.4286 [0.1429, 0.8571] | -1.2382 [-3.2239, -0.3926] | 3.2878 [-1.3158, 6.5874] | 4.5510 [-0.8925, 14.5464] |
| POST_IB_PRE_OB | 0.10 | 127 | 13 | 0.3846 [0.1538, 0.6154] | -2.6818 [-4.8440, -0.9422] | 0.8892 [-1.4887, 3.9613] | 13.0879 [4.3657, 21.1403] |
| POST_IB_PRE_OB | 0.20 | 127 | 26 | 0.3462 [0.1154, 0.4615] | -4.6654 [-6.7517, -1.6481] | 0.9548 [-1.2581, 4.0964] | 18.9927 [7.0566, 25.4257] |
| POST_IB_PRE_OB | 0.30 | 127 | 39 | 0.1795 [0.0769, 0.3077] | -3.0821 [-5.2211, -1.2343] | 1.7575 [-0.7662, 3.3369] | 14.3486 [5.5885, 25.7399] |
| POST_OB_PRE_TO | 0.05 | 82 | 5 | 0.0000 [0.0000, 0.5000] | 0.0000 [-1.0703, 0.0000] | 0.0000 [0.0000, 9.5091] | 0.0000 [-1.0703, 0.0000] |
| POST_OB_PRE_TO | 0.10 | 82 | 9 | 0.1111 [0.0000, 0.3333] | -0.0795 [-1.0281, 0.0000] | 3.4655 [0.0000, 9.6534] | -0.0795 [-1.0281, 0.0000] |
| POST_OB_PRE_TO | 0.20 | 82 | 17 | 0.0000 [0.0000, 0.1176] | 0.0000 [-0.2124, 0.0000] | 0.0000 [0.0000, 3.1715] | 0.0000 [-0.2124, 0.0000] |
| POST_OB_PRE_TO | 0.30 | 82 | 25 | 0.0400 [0.0000, 0.1071] | -0.1306 [-0.2389, 0.0000] | 1.0094 [0.0000, 2.9869] | -0.1306 [-0.2389, 0.0000] |

## Delay-Linkage Audit

| Existing result | Kendall tau-b | Median rank displacement | Top-decile overlap |
|---|---:|---:|---:|
| PRIMARY | 0.736489 | 0.069746 | 0.728916 |
| NO_F_EXECUTION | 0.711648 | 0.076087 | 0.710843 |

PRIMARY is absent from the robustness CSV; read the manifest-tracked EXP2A_SUMMARY, not a support sensitivity.

Component/domain associations below are the original frozen Kendall tau-b estimates, with their original uncertainty and population metadata retained in the audit JSON.

| Component/domain | Kendall tau-b | 95% CI |
|---|---:|---:|
| F_continuity | -0.071730 | [-0.137741, 0.008894] |
| F_execution | 0.808511 | [0.759493, 0.850437] |
| F_propagation | 1.000000 | [1.000000, 1.000000] |
| P_time | 0.647186 | [0.573151, 0.716545] |
| P_itinerary | 0.408278 | [0.293494, 0.506404] |
| P_service | 0.556228 | [0.450106, 0.637788] |
| R_operating | 0.212109 | [0.116115, 0.309634] |
| score_F | 0.932289 | [0.912379, 0.949239] |
| score_P | 0.652115 | [0.581306, 0.721093] |
| score_R | 0.212109 | [0.116115, 0.309634] |

### Reviewer-Facing Interpretation

These results are consistent with delay-linked consequence channels contributing to high overall association, while similar predicted delay severity need not imply identical consequence-based recovery priority. This evidence does not require removing delay from the primary consequence score.

- No causal decomposition or fraction of correlation attributable to any channel is identified.
- NO_F_EXECUTION is not a delay-free score: other channels retain their frozen delay dependence.
- A positive caliper permits residual delay differences; these comparisons do not prove exact-delay conditional independence.
- Wider calipers change the qualifying pair set; they are not new primary estimands or evidence of causal superiority.
- Screening capture describes allocation trade-offs, not uniformly improved capture in every domain or a causal recovery benefit.

Delay dependence in F_execution, F_propagation, P_time, P_itinerary, P_service, and R_operating belongs to their consequence semantics. Mechanically deleting these components would change the scientific object. No such score, new weighting, or new threshold is introduced here. Eq. (7)-(8) remain unchanged.

## Provenance and Boundaries

- `model_retrained=false`
- `calibration_refit=false`
- `parameter_reselected=false`
- `primary_scientific_object_changed=false`
- `new_primary_estimand=false`
- `final_test_secondary_derivation=true`
- `exp4_rerun=false`
- `final_test_cohort_rematerialized=false`
- `manuscript_modified=false`
- `raw_final_test_data_read=false`
- Protected files verified unchanged: 1289.
- Remaining execution BLOCKED items: none.
- Source component-level ABSTAIN cells retained: 20; see audit JSON. Undefined/zero-denominator capture is not replaced with zero.
- Manuscript integration: HUMAN_DECISION_REQUIRED. Stop here.

## Output Hashes

- `SECTION5_EXP2_CALIPER_SENSITIVITY.csv`: `sha256:6f7007599fcca0b1ef9474eae29c922c9cd456483d5ef63ad7ed8e2ce33b94b4`
- `SECTION5_EXP4_CAPACITY_SENSITIVITY.csv`: `sha256:806e03e426a15bf44566f3b2abeb93d9d2a39d3097ffaec183d88cb0f23e87e7`
- `SECTION5_DELAY_LINKAGE_AUDIT.json`: `sha256:3887936bbb6b1346e46259f155cb2381f0acca97b59a3b3ebdbc4011ffe40024`
- `SECTION5_EXP2_CALIPER_BOOTSTRAP.csv`: `sha256:6e781fa4950d31b990da1101c8f966e351c25f83605f29cb9bbccd4e9c335a6f`

The manifest records the report hash. Its own hash is external to avoid a self-referential checksum.
