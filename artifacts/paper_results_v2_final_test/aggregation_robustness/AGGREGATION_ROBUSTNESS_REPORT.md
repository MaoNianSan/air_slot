# Aggregation Robustness Report

Reporting-only Final Test computation using the frozen Exp2A node population.

- HEAD: `860befd20e968ba702b1aad99e618830a3a6acfe`
- Population: `1656` nodes, `128` episodes
- Bootstrap: `2000` episode clusters, seed `20260906`, percentile 95% CI
- Interpretation: numerical estimates and ranges are shown; no automatic robustness conclusion is assigned.

## Overall

| aggregation_view   | metric                             |   estimate |   ci_low |   ci_high | support_status   |
|:-------------------|:-----------------------------------|-----------:|---------:|----------:|:-----------------|
| BASE_EQUAL_DOMAIN  | kendall_tau_b                      |   0.736489 | 0.676347 |  0.788455 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | spearman_rho                       |   0.896065 | 0.842446 |  0.929507 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | top_decile_overlap                 |   0.728916 | 0.440989 |  0.872942 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | median_abs_rank_displacement       |   0.069746 | 0.047766 |  0.093967 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | p90_abs_rank_displacement          |   0.227053 | 0.178178 |  0.294760 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | share_abs_rank_displacement_ge_030 |   0.047705 | 0.015159 |  0.095127 | SUPPORTED        |
| EQUAL_COMPONENT    | kendall_tau_b                      |   0.842601 | 0.809239 |  0.871617 | SUPPORTED        |
| EQUAL_COMPONENT    | spearman_rho                       |   0.963110 | 0.941263 |  0.973830 | SUPPORTED        |
| EQUAL_COMPONENT    | top_decile_overlap                 |   0.831325 | 0.596215 |  0.935682 | SUPPORTED        |
| EQUAL_COMPONENT    | median_abs_rank_displacement       |   0.045894 | 0.032787 |  0.059649 | SUPPORTED        |
| EQUAL_COMPONENT    | p90_abs_rank_displacement          |   0.133756 | 0.108054 |  0.177611 | SUPPORTED        |
| EQUAL_COMPONENT    | share_abs_rank_displacement_ge_030 |   0.000000 | 0.000000 |  0.010019 | SUPPORTED        |
| NO_F_EXEC          | kendall_tau_b                      |   0.711648 | 0.646995 |  0.769038 | SUPPORTED        |
| NO_F_EXEC          | spearman_rho                       |   0.877665 | 0.816533 |  0.916609 | SUPPORTED        |
| NO_F_EXEC          | top_decile_overlap                 |   0.710843 | 0.386039 |  0.849726 | SUPPORTED        |
| NO_F_EXEC          | median_abs_rank_displacement       |   0.076087 | 0.053778 |  0.105039 | SUPPORTED        |
| NO_F_EXEC          | p90_abs_rank_displacement          |   0.242452 | 0.193831 |  0.312313 | SUPPORTED        |
| NO_F_EXEC          | share_abs_rank_displacement_ge_030 |   0.056159 | 0.022209 |  0.112443 | SUPPORTED        |
| FLIGHT_EMPHASIS    | kendall_tau_b                      |   0.833193 | 0.792213 |  0.866842 | SUPPORTED        |
| FLIGHT_EMPHASIS    | spearman_rho                       |   0.956328 | 0.928726 |  0.970624 | SUPPORTED        |
| FLIGHT_EMPHASIS    | top_decile_overlap                 |   0.789157 | 0.612080 |  0.934132 | SUPPORTED        |
| FLIGHT_EMPHASIS    | median_abs_rank_displacement       |   0.041667 | 0.029935 |  0.056142 | SUPPORTED        |
| FLIGHT_EMPHASIS    | p90_abs_rank_displacement          |   0.146437 | 0.114816 |  0.194464 | SUPPORTED        |
| FLIGHT_EMPHASIS    | share_abs_rank_displacement_ge_030 |   0.002415 | 0.000000 |  0.024678 | SUPPORTED        |
| PASSENGER_EMPHASIS | kendall_tau_b                      |   0.764511 | 0.710511 |  0.809521 | SUPPORTED        |
| PASSENGER_EMPHASIS | spearman_rho                       |   0.915571 | 0.870683 |  0.942840 | SUPPORTED        |
| PASSENGER_EMPHASIS | top_decile_overlap                 |   0.728916 | 0.511621 |  0.885070 | SUPPORTED        |
| PASSENGER_EMPHASIS | median_abs_rank_displacement       |   0.052536 | 0.038325 |  0.074741 | SUPPORTED        |
| PASSENGER_EMPHASIS | p90_abs_rank_displacement          |   0.204710 | 0.162660 |  0.270457 | SUPPORTED        |
| PASSENGER_EMPHASIS | share_abs_rank_displacement_ge_030 |   0.033816 | 0.005357 |  0.077435 | SUPPORTED        |
| OPERATING_EMPHASIS | kendall_tau_b                      |   0.597026 | 0.520281 |  0.672275 | SUPPORTED        |
| OPERATING_EMPHASIS | spearman_rho                       |   0.778249 | 0.689224 |  0.843011 | SUPPORTED        |
| OPERATING_EMPHASIS | top_decile_overlap                 |   0.457831 | 0.216803 |  0.739406 | SUPPORTED        |
| OPERATING_EMPHASIS | median_abs_rank_displacement       |   0.126510 | 0.089581 |  0.164509 | SUPPORTED        |
| OPERATING_EMPHASIS | p90_abs_rank_displacement          |   0.324275 | 0.266079 |  0.385009 | SUPPORTED        |
| OPERATING_EMPHASIS | share_abs_rank_displacement_ge_030 |   0.137681 | 0.064911 |  0.215512 | SUPPORTED        |

## Similar Delay

| aggregation_view   | metric                           |   estimate |   ci_low |   ci_high |   n_pair |   n_node |   n_episode | support_status   |
|:-------------------|:---------------------------------|-----------:|---------:|----------:|---------:|---------:|------------:|:-----------------|
| BASE_EQUAL_DOMAIN  | median_abs_priority_separation   |   0.204106 | 0.180596 |  0.234293 |     7045 |     1656 |         128 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | share_priority_separation_ge_030 |   0.337828 | 0.279314 |  0.394977 |     7045 |     1656 |         128 | SUPPORTED        |
| EQUAL_COMPONENT    | median_abs_priority_separation   |   0.189010 | 0.164732 |  0.218824 |     7045 |     1656 |         128 | SUPPORTED        |
| EQUAL_COMPONENT    | share_priority_separation_ge_030 |   0.294819 | 0.230879 |  0.361524 |     7045 |     1656 |         128 | SUPPORTED        |
| NO_F_EXEC          | median_abs_priority_separation   |   0.207126 | 0.183343 |  0.237471 |     7045 |     1656 |         128 | SUPPORTED        |
| NO_F_EXEC          | share_priority_separation_ge_030 |   0.344642 | 0.286934 |  0.399869 |     7045 |     1656 |         128 | SUPPORTED        |
| FLIGHT_EMPHASIS    | median_abs_priority_separation   |   0.195954 | 0.169216 |  0.227390 |     7045 |     1656 |         128 | SUPPORTED        |
| FLIGHT_EMPHASIS    | share_priority_separation_ge_030 |   0.309013 | 0.243259 |  0.375024 |     7045 |     1656 |         128 | SUPPORTED        |
| PASSENGER_EMPHASIS | median_abs_priority_separation   |   0.201087 | 0.177426 |  0.229857 |     7045 |     1656 |         128 | SUPPORTED        |
| PASSENGER_EMPHASIS | share_priority_separation_ge_030 |   0.323918 | 0.267889 |  0.384109 |     7045 |     1656 |         128 | SUPPORTED        |
| OPERATING_EMPHASIS | median_abs_priority_separation   |   0.225845 | 0.200915 |  0.254324 |     7045 |     1656 |         128 | SUPPORTED        |
| OPERATING_EMPHASIS | share_priority_separation_ge_030 |   0.381547 | 0.332262 |  0.432259 |     7045 |     1656 |         128 | SUPPORTED        |

## Stage

| aggregation_view   | stage          | metric                       |   estimate |   ci_low |   ci_high |   n_node |   n_episode | support_status   |
|:-------------------|:---------------|:-----------------------------|-----------:|---------:|----------:|---------:|------------:|:-----------------|
| BASE_EQUAL_DOMAIN  | PRE_IB         | kendall_tau_b                |   0.792662 | 0.669205 |  0.881138 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.023622 |  0.118289 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | PRE_IB         | top_decile_overlap           |   0.545455 | 0.000000 |  1.000000 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | kendall_tau_b                |   0.709885 | 0.636776 |  0.769894 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | median_abs_rank_displacement |   0.080949 | 0.050833 |  0.107726 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | top_decile_overlap           |   0.743056 | 0.398563 |  0.900018 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | kendall_tau_b                |   0.982696 | 0.964044 |  0.995342 |      121 |          82 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.636364 |  1.000000 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | kendall_tau_b                |   0.866434 | 0.777001 |  0.928128 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | median_abs_rank_displacement |   0.039216 | 0.012654 |  0.078947 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | top_decile_overlap           |   0.818182 | 0.384375 |  1.000000 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | kendall_tau_b                |   0.820716 | 0.779857 |  0.855622 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | median_abs_rank_displacement |   0.051640 | 0.036879 |  0.068420 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | top_decile_overlap           |   0.819444 | 0.542813 |  0.942153 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | kendall_tau_b                |   0.967595 | 0.944451 |  0.985860 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.008475 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.545455 |  1.000000 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | kendall_tau_b                |   0.782178 | 0.652663 |  0.872644 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.025316 |  0.120373 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | top_decile_overlap           |   0.545455 | 0.000000 |  1.000000 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | kendall_tau_b                |   0.683190 | 0.605016 |  0.749607 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | median_abs_rank_displacement |   0.090021 | 0.057912 |  0.121364 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | top_decile_overlap           |   0.694444 | 0.355050 |  0.875822 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | kendall_tau_b                |   0.983011 | 0.964745 |  0.995363 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.636364 |  1.000000 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | kendall_tau_b                |   0.859833 | 0.767665 |  0.920027 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | median_abs_rank_displacement |   0.049020 | 0.013694 |  0.082196 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | top_decile_overlap           |   0.818182 | 0.090909 |  1.000000 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | kendall_tau_b                |   0.815182 | 0.766034 |  0.854490 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | median_abs_rank_displacement |   0.043964 | 0.031892 |  0.064664 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | top_decile_overlap           |   0.805556 | 0.573638 |  0.944796 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | kendall_tau_b                |   0.983955 | 0.966431 |  0.995687 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.636364 |  1.000000 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | kendall_tau_b                |   0.788779 | 0.661534 |  0.877503 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.024992 |  0.118114 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | top_decile_overlap           |   0.545455 | 0.000000 |  1.000000 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | kendall_tau_b                |   0.738623 | 0.672736 |  0.793968 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | median_abs_rank_displacement |   0.056525 | 0.039130 |  0.085141 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | top_decile_overlap           |   0.736111 | 0.472964 |  0.900766 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | kendall_tau_b                |   0.970426 | 0.948896 |  0.987104 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.008132 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.583333 |  1.000000 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | kendall_tau_b                |   0.688216 | 0.518165 |  0.806956 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | median_abs_rank_displacement |   0.088235 | 0.042017 |  0.170461 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | top_decile_overlap           |   0.545455 | 0.000000 |  1.000000 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | kendall_tau_b                |   0.561946 | 0.468772 |  0.648613 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | median_abs_rank_displacement |   0.144452 | 0.099412 |  0.184834 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | top_decile_overlap           |   0.451389 | 0.179104 |  0.764706 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | kendall_tau_b                |   0.991820 | 0.979279 |  0.999408 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.769231 |  1.000000 |      121 |          82 | SUPPORTED        |

## Gates

- BASE reproduction: `PASS`
- Exp4 view-definition consistency: `PASS`
- Model retraining: `false`; calibration refit: `false`; parameter reselection: `false`.
- BLOCKED / ABSTAIN: none in the materialized six-view tables.
