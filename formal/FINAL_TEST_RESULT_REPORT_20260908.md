# Air Slot Held-Out Final Test Result Report

Status: `FINAL_TEST_COMPLETE_READY_FOR_HUMAN_RESULT_REVIEW`.

## Execution

- Execution HEAD: `c7bf2695335013994e09657e07bb023087a4039f`
- Development scientific code lock: `c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6`
- Final Test cohort authority commit: `1c336fb42b0fa7df716f8bf3bc7a67ca0153c06b`
- `FINAL_TEST_ACCESS_COUNT = 1`
- `model_retrained = false`; `calibration_refit = false`; `parameter_reselected = false`
- `paper_result = true`; this does not modify the manuscript.

## Cohort And Support

- Selected episodes: 128 (`sha256:1208ea465a123a7a6333dc2fd95b182492d5636fb1d8add50845d2f716313d4f`)
- Frozen Q4 eligible pool: 1407908; PRE rolling nodes: 1660; active analysis nodes: 1656.
- Exp2-Exp4 primary-support nodes: 1656.0; all three active stages retain full primary support coverage.
- Exp4 canonical events: 238 supported; 0 typed unsupported exclusions. No later-node replacement occurred.

## Exp1

| Target | N nodes | N episodes | History MAE | Current MAE | Delta MAE [95% CI] |
| --- | ---: | ---: | ---: | ---: | ---: |
| R_IB | 102 | 29 | 10.281 | 10.670 | -0.389 [-1.923, 1.361] |
| D_OB | 1535 | 128 | 6.878 | 6.843 | 0.035 [-0.032, 0.112] |
| D_TX | 1656 | 128 | 4.724 | 4.518 | 0.206 [-0.028, 0.450] |

R_IB finite-support CRPS is 7.561 (History) versus 9.060 (Current), with Delta -1.498 [-3.139, 0.155]. Evaluation-lead reporting has 16 passing rows and 14 legitimate typed abstentions.

## Exp2

Primary delay/consequence association: Kendall tau-b 0.736 [0.676, 0.788], Top-10 overlap 0.729 [0.441, 0.873], median rank displacement 0.070 [0.048, 0.094]. Exp2B uses the independently defined finite, support-applicable component/domain population.

## Exp3

| Stage | N nodes | Tau-b [95% CI] | Top-10 overlap [95% CI] | Same-delay percentile gap [95% CI] |
| --- | ---: | ---: | ---: | ---: |
| PRE_IB | 102 | 0.793 [0.669, 0.881] | 0.545 [0.000, 1.000] | 0.233 [0.191, 0.307] |
| POST_IB_PRE_OB | 1433 | 0.710 [0.637, 0.770] | 0.743 [0.399, 0.900] | 0.230 [0.208, 0.258] |
| POST_OB_PRE_TO | 121 | 0.983 [0.964, 0.995] | 0.923 [0.636, 1.000] | 0.302 [0.291, 0.318] |

All three frozen pairwise contrasts and common-episode robustness are present in the formal tables with 2,000 episode-cluster replicates.

## Exp4 At q=10%

| Stage | N | K | Overlap [95% CI] | Reassigned rate [95% CI] | Delta robust miss m=4 [95% CI] | Pareto reversals D/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PRE_IB | 29 | 3 | 3.000 [1.000, 4.000] | 0.000 [0.000, 0.750] | 0.000 [-0.667, 0.333] | 0/0 |
| POST_IB_PRE_OB | 127 | 13 | 8.000 [5.000, 11.000] | 0.385 [0.154, 0.615] | -0.231 [-0.538, 0.000] | 0/0 |
| POST_OB_PRE_TO | 82 | 9 | 8.000 [6.000, 10.000] | 0.111 [0.000, 0.333] | -0.111 [-0.250, 0.111] | 0/0 |

The frozen q grid is 5%, 10%, 20%, and 30%. Pareto reversals remain zero under the locked definition; no alternative definition was introduced.

## Integrity And Interpretation Boundary

All Exp1-Exp4 primary bootstrap artifacts contain 2,000 unique replicate IDs using the frozen seed and original-episode clusters. The Development-versus-Test comparison is stored as sign/value provenance in `FINAL_TEST_RESULT_REPORT.json`; it is descriptive only. No Test result was used to alter a scientific definition or to select reporting parameters.

Paper-facing figure data and vector figures are under `artifacts/experiment/final_test/exp1`, `exp3`, and `exp4`; existing Exp2 figures remain under its Final Test root.
