# Aggregation Robustness Report

Reporting-only Final Test computation using the frozen Exp2A node population.

- HEAD: `860befd20e968ba702b1aad99e618830a3a6acfe`
- Population: `1656` nodes, `128` episodes
- Bootstrap: `20` episode clusters, seed `20260906`, percentile 95% CI
- Interpretation: numerical estimates and ranges are shown; no automatic robustness conclusion is assigned.

## Overall

| aggregation_view   | metric                             |   estimate |   ci_low |   ci_high | support_status   |
|:-------------------|:-----------------------------------|-----------:|---------:|----------:|:-----------------|
| BASE_EQUAL_DOMAIN  | kendall_tau_b                      |   0.736489 | 0.665018 |  0.780067 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | spearman_rho                       |   0.896065 | 0.837010 |  0.926097 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | top_decile_overlap                 |   0.728916 | 0.407670 |  0.822614 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | median_abs_rank_displacement       |   0.069746 | 0.047693 |  0.090196 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | p90_abs_rank_displacement          |   0.227053 | 0.181647 |  0.310407 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | share_abs_rank_displacement_ge_030 |   0.047705 | 0.014794 |  0.106709 | SUPPORTED        |
| EQUAL_COMPONENT    | kendall_tau_b                      |   0.842601 | 0.802009 |  0.872298 | SUPPORTED        |
| EQUAL_COMPONENT    | spearman_rho                       |   0.963110 | 0.937892 |  0.974912 | SUPPORTED        |
| EQUAL_COMPONENT    | top_decile_overlap                 |   0.831325 | 0.666086 |  0.924401 | SUPPORTED        |
| EQUAL_COMPONENT    | median_abs_rank_displacement       |   0.045894 | 0.035094 |  0.055430 | SUPPORTED        |
| EQUAL_COMPONENT    | p90_abs_rank_displacement          |   0.133756 | 0.107879 |  0.180254 | SUPPORTED        |
| EQUAL_COMPONENT    | share_abs_rank_displacement_ge_030 |   0.000000 | 0.000000 |  0.012991 | SUPPORTED        |
| NO_F_EXEC          | kendall_tau_b                      |   0.711648 | 0.634212 |  0.756387 | SUPPORTED        |
| NO_F_EXEC          | spearman_rho                       |   0.877665 | 0.808849 |  0.910614 | SUPPORTED        |
| NO_F_EXEC          | top_decile_overlap                 |   0.710843 | 0.332518 |  0.803022 | SUPPORTED        |
| NO_F_EXEC          | median_abs_rank_displacement       |   0.076087 | 0.052159 |  0.103092 | SUPPORTED        |
| NO_F_EXEC          | p90_abs_rank_displacement          |   0.242452 | 0.198715 |  0.322171 | SUPPORTED        |
| NO_F_EXEC          | share_abs_rank_displacement_ge_030 |   0.056159 | 0.022918 |  0.123287 | SUPPORTED        |
| FLIGHT_EMPHASIS    | kendall_tau_b                      |   0.833193 | 0.786022 |  0.860496 | SUPPORTED        |
| FLIGHT_EMPHASIS    | spearman_rho                       |   0.956328 | 0.926518 |  0.969660 | SUPPORTED        |
| FLIGHT_EMPHASIS    | top_decile_overlap                 |   0.789157 | 0.688426 |  0.920261 | SUPPORTED        |
| FLIGHT_EMPHASIS    | median_abs_rank_displacement       |   0.041667 | 0.027331 |  0.051866 | SUPPORTED        |
| FLIGHT_EMPHASIS    | p90_abs_rank_displacement          |   0.146437 | 0.112845 |  0.211317 | SUPPORTED        |
| FLIGHT_EMPHASIS    | share_abs_rank_displacement_ge_030 |   0.002415 | 0.000000 |  0.025377 | SUPPORTED        |
| PASSENGER_EMPHASIS | kendall_tau_b                      |   0.764511 | 0.699135 |  0.812599 | SUPPORTED        |
| PASSENGER_EMPHASIS | spearman_rho                       |   0.915571 | 0.857813 |  0.945384 | SUPPORTED        |
| PASSENGER_EMPHASIS | top_decile_overlap                 |   0.728916 | 0.614907 |  0.859568 | SUPPORTED        |
| PASSENGER_EMPHASIS | median_abs_rank_displacement       |   0.052536 | 0.043429 |  0.065948 | SUPPORTED        |
| PASSENGER_EMPHASIS | p90_abs_rank_displacement          |   0.204710 | 0.165857 |  0.283163 | SUPPORTED        |
| PASSENGER_EMPHASIS | share_abs_rank_displacement_ge_030 |   0.033816 | 0.002320 |  0.090917 | SUPPORTED        |
| OPERATING_EMPHASIS | kendall_tau_b                      |   0.597026 | 0.499780 |  0.642720 | SUPPORTED        |
| OPERATING_EMPHASIS | spearman_rho                       |   0.778249 | 0.669150 |  0.817898 | SUPPORTED        |
| OPERATING_EMPHASIS | top_decile_overlap                 |   0.457831 | 0.217645 |  0.676736 | SUPPORTED        |
| OPERATING_EMPHASIS | median_abs_rank_displacement       |   0.126510 | 0.095809 |  0.174172 | SUPPORTED        |
| OPERATING_EMPHASIS | p90_abs_rank_displacement          |   0.324275 | 0.282376 |  0.393975 | SUPPORTED        |
| OPERATING_EMPHASIS | share_abs_rank_displacement_ge_030 |   0.137681 | 0.074324 |  0.224727 | SUPPORTED        |

## Similar Delay

| aggregation_view   | metric                           |   estimate |   ci_low |   ci_high |   n_pair |   n_node |   n_episode | support_status   |
|:-------------------|:---------------------------------|-----------:|---------:|----------:|---------:|---------:|------------:|:-----------------|
| BASE_EQUAL_DOMAIN  | median_abs_priority_separation   |   0.204106 | 0.179039 |  0.234402 |     7045 |     1656 |         128 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | share_priority_separation_ge_030 |   0.337828 | 0.280106 |  0.398373 |     7045 |     1656 |         128 | SUPPORTED        |
| EQUAL_COMPONENT    | median_abs_priority_separation   |   0.189010 | 0.162468 |  0.219983 |     7045 |     1656 |         128 | SUPPORTED        |
| EQUAL_COMPONENT    | share_priority_separation_ge_030 |   0.294819 | 0.225450 |  0.356851 |     7045 |     1656 |         128 | SUPPORTED        |
| NO_F_EXEC          | median_abs_priority_separation   |   0.207126 | 0.184214 |  0.237508 |     7045 |     1656 |         128 | SUPPORTED        |
| NO_F_EXEC          | share_priority_separation_ge_030 |   0.344642 | 0.291648 |  0.404485 |     7045 |     1656 |         128 | SUPPORTED        |
| FLIGHT_EMPHASIS    | median_abs_priority_separation   |   0.195954 | 0.168904 |  0.229367 |     7045 |     1656 |         128 | SUPPORTED        |
| FLIGHT_EMPHASIS    | share_priority_separation_ge_030 |   0.309013 | 0.234710 |  0.376613 |     7045 |     1656 |         128 | SUPPORTED        |
| PASSENGER_EMPHASIS | median_abs_priority_separation   |   0.201087 | 0.177761 |  0.231442 |     7045 |     1656 |         128 | SUPPORTED        |
| PASSENGER_EMPHASIS | share_priority_separation_ge_030 |   0.323918 | 0.260223 |  0.385776 |     7045 |     1656 |         128 | SUPPORTED        |
| OPERATING_EMPHASIS | median_abs_priority_separation   |   0.225845 | 0.203206 |  0.253735 |     7045 |     1656 |         128 | SUPPORTED        |
| OPERATING_EMPHASIS | share_priority_separation_ge_030 |   0.381547 | 0.335600 |  0.435923 |     7045 |     1656 |         128 | SUPPORTED        |

## Stage

| aggregation_view   | stage          | metric                       |   estimate |   ci_low |   ci_high |   n_node |   n_episode | support_status   |
|:-------------------|:---------------|:-----------------------------|-----------:|---------:|----------:|---------:|------------:|:-----------------|
| BASE_EQUAL_DOMAIN  | PRE_IB         | kendall_tau_b                |   0.792662 | 0.704815 |  0.866923 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.034615 |  0.100247 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | PRE_IB         | top_decile_overlap           |   0.545455 | 0.178125 |  1.000000 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | kendall_tau_b                |   0.709885 | 0.630569 |  0.762233 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | median_abs_rank_displacement |   0.080949 | 0.054933 |  0.104165 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | top_decile_overlap           |   0.743056 | 0.365918 |  0.826941 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | kendall_tau_b                |   0.982696 | 0.962683 |  0.995616 |      121 |          82 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.645536 |  1.000000 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | kendall_tau_b                |   0.866434 | 0.795929 |  0.917766 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | median_abs_rank_displacement |   0.039216 | 0.026128 |  0.078372 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | top_decile_overlap           |   0.818182 | 0.449242 |  1.000000 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | kendall_tau_b                |   0.820716 | 0.770473 |  0.856054 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | median_abs_rank_displacement |   0.051640 | 0.040668 |  0.062121 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | top_decile_overlap           |   0.819444 | 0.600101 |  0.946196 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | kendall_tau_b                |   0.967595 | 0.948634 |  0.987616 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.007955 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.567857 |  1.000000 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | kendall_tau_b                |   0.782178 | 0.684988 |  0.858529 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.038828 |  0.100247 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | top_decile_overlap           |   0.545455 | 0.178125 |  1.000000 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | kendall_tau_b                |   0.683190 | 0.598215 |  0.736888 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | median_abs_rank_displacement |   0.090021 | 0.062047 |  0.119768 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | top_decile_overlap           |   0.694444 | 0.297080 |  0.785028 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | kendall_tau_b                |   0.983011 | 0.962843 |  0.996039 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.645536 |  1.000000 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | kendall_tau_b                |   0.859833 | 0.791671 |  0.914982 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | median_abs_rank_displacement |   0.049020 | 0.021474 |  0.064736 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | top_decile_overlap           |   0.818182 | 0.274242 |  1.000000 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | kendall_tau_b                |   0.815182 | 0.759681 |  0.846590 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | median_abs_rank_displacement |   0.043964 | 0.030376 |  0.059501 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | top_decile_overlap           |   0.805556 | 0.635803 |  0.889291 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | kendall_tau_b                |   0.983955 | 0.963806 |  0.996334 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.645536 |  1.000000 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | kendall_tau_b                |   0.788779 | 0.697034 |  0.881706 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.031098 |  0.113498 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | top_decile_overlap           |   0.545455 | 0.178125 |  1.000000 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | kendall_tau_b                |   0.738623 | 0.658010 |  0.792431 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | median_abs_rank_displacement |   0.056525 | 0.049826 |  0.072054 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | top_decile_overlap           |   0.736111 | 0.539668 |  0.833865 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | kendall_tau_b                |   0.970426 | 0.952018 |  0.990668 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.007798 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.601786 |  1.000000 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | kendall_tau_b                |   0.688216 | 0.497978 |  0.778524 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | median_abs_rank_displacement |   0.088235 | 0.052599 |  0.154457 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | top_decile_overlap           |   0.545455 | 0.073077 |  0.908750 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | kendall_tau_b                |   0.561946 | 0.455430 |  0.614866 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | median_abs_rank_displacement |   0.144452 | 0.107548 |  0.188787 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | top_decile_overlap           |   0.451389 | 0.164755 |  0.719998 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | kendall_tau_b                |   0.991820 | 0.975097 |  0.999217 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.872917 |  1.000000 |      121 |          82 | SUPPORTED        |

## Gates

- BASE reproduction: `PASS`
- Exp4 view-definition consistency: `PASS`
- Model retraining: `false`; calibration refit: `false`; parameter reselection: `false`.
- BLOCKED / ABSTAIN: none in the materialized six-view tables.
