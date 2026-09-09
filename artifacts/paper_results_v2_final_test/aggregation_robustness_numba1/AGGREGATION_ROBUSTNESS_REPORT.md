# Aggregation Robustness Report

Reporting-only Final Test computation using the frozen Exp2A node population.

- HEAD: `860befd20e968ba702b1aad99e618830a3a6acfe`
- Population: `1656` nodes, `128` episodes
- Bootstrap: `1` episode clusters, seed `20260906`, percentile 95% CI
- Interpretation: numerical estimates and ranges are shown; no automatic robustness conclusion is assigned.

## Overall

| aggregation_view   | metric                             |   estimate |   ci_low |   ci_high | support_status   |
|:-------------------|:-----------------------------------|-----------:|---------:|----------:|:-----------------|
| BASE_EQUAL_DOMAIN  | kendall_tau_b                      |   0.736489 | 0.664678 |  0.664678 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | spearman_rho                       |   0.896065 | 0.838651 |  0.838651 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | top_decile_overlap                 |   0.728916 | 0.739130 |  0.739130 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | median_abs_rank_displacement       |   0.069746 | 0.081047 |  0.081047 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | p90_abs_rank_displacement          |   0.227053 | 0.305486 |  0.305486 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | share_abs_rank_displacement_ge_030 |   0.047705 | 0.107232 |  0.107232 | SUPPORTED        |
| EQUAL_COMPONENT    | kendall_tau_b                      |   0.842601 | 0.797712 |  0.797712 | SUPPORTED        |
| EQUAL_COMPONENT    | spearman_rho                       |   0.963110 | 0.935903 |  0.935903 | SUPPORTED        |
| EQUAL_COMPONENT    | top_decile_overlap                 |   0.831325 | 0.838509 |  0.838509 | SUPPORTED        |
| EQUAL_COMPONENT    | median_abs_rank_displacement       |   0.045894 | 0.046135 |  0.046135 | SUPPORTED        |
| EQUAL_COMPONENT    | p90_abs_rank_displacement          |   0.133756 | 0.173130 |  0.173130 | SUPPORTED        |
| EQUAL_COMPONENT    | share_abs_rank_displacement_ge_030 |   0.000000 | 0.016209 |  0.016209 | SUPPORTED        |
| NO_F_EXEC          | kendall_tau_b                      |   0.711648 | 0.637795 |  0.637795 | SUPPORTED        |
| NO_F_EXEC          | spearman_rho                       |   0.877665 | 0.814579 |  0.814579 | SUPPORTED        |
| NO_F_EXEC          | top_decile_overlap                 |   0.710843 | 0.714286 |  0.714286 | SUPPORTED        |
| NO_F_EXEC          | median_abs_rank_displacement       |   0.076087 | 0.089776 |  0.089776 | SUPPORTED        |
| NO_F_EXEC          | p90_abs_rank_displacement          |   0.242452 | 0.319825 |  0.319825 | SUPPORTED        |
| NO_F_EXEC          | share_abs_rank_displacement_ge_030 |   0.056159 | 0.130923 |  0.130923 | SUPPORTED        |
| FLIGHT_EMPHASIS    | kendall_tau_b                      |   0.833193 | 0.780802 |  0.780802 | SUPPORTED        |
| FLIGHT_EMPHASIS    | spearman_rho                       |   0.956328 | 0.924304 |  0.924304 | SUPPORTED        |
| FLIGHT_EMPHASIS    | top_decile_overlap                 |   0.789157 | 0.807453 |  0.807453 | SUPPORTED        |
| FLIGHT_EMPHASIS    | median_abs_rank_displacement       |   0.041667 | 0.051122 |  0.051122 | SUPPORTED        |
| FLIGHT_EMPHASIS    | p90_abs_rank_displacement          |   0.146437 | 0.206359 |  0.206359 | SUPPORTED        |
| FLIGHT_EMPHASIS    | share_abs_rank_displacement_ge_030 |   0.002415 | 0.028055 |  0.028055 | SUPPORTED        |
| PASSENGER_EMPHASIS | kendall_tau_b                      |   0.764511 | 0.699145 |  0.699145 | SUPPORTED        |
| PASSENGER_EMPHASIS | spearman_rho                       |   0.915571 | 0.861489 |  0.861489 | SUPPORTED        |
| PASSENGER_EMPHASIS | top_decile_overlap                 |   0.728916 | 0.782609 |  0.782609 | SUPPORTED        |
| PASSENGER_EMPHASIS | median_abs_rank_displacement       |   0.052536 | 0.068267 |  0.068267 | SUPPORTED        |
| PASSENGER_EMPHASIS | p90_abs_rank_displacement          |   0.204710 | 0.262469 |  0.262469 | SUPPORTED        |
| PASSENGER_EMPHASIS | share_abs_rank_displacement_ge_030 |   0.033816 | 0.079177 |  0.079177 | SUPPORTED        |
| OPERATING_EMPHASIS | kendall_tau_b                      |   0.597026 | 0.513834 |  0.513834 | SUPPORTED        |
| OPERATING_EMPHASIS | spearman_rho                       |   0.778249 | 0.687014 |  0.687014 | SUPPORTED        |
| OPERATING_EMPHASIS | top_decile_overlap                 |   0.457831 | 0.496894 |  0.496894 | SUPPORTED        |
| OPERATING_EMPHASIS | median_abs_rank_displacement       |   0.126510 | 0.143392 |  0.143392 | SUPPORTED        |
| OPERATING_EMPHASIS | p90_abs_rank_displacement          |   0.324275 | 0.400249 |  0.400249 | SUPPORTED        |
| OPERATING_EMPHASIS | share_abs_rank_displacement_ge_030 |   0.137681 | 0.216958 |  0.216958 | SUPPORTED        |

## Similar Delay

| aggregation_view   | metric                           |   estimate |   ci_low |   ci_high |   n_pair |   n_node |   n_episode | support_status   |
|:-------------------|:---------------------------------|-----------:|---------:|----------:|---------:|---------:|------------:|:-----------------|
| BASE_EQUAL_DOMAIN  | median_abs_priority_separation   |   0.204106 | 0.231920 |  0.231920 |     7045 |     1656 |         128 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | share_priority_separation_ge_030 |   0.337828 | 0.393406 |  0.393406 |     7045 |     1656 |         128 | SUPPORTED        |
| EQUAL_COMPONENT    | median_abs_priority_separation   |   0.189010 | 0.204333 |  0.204333 |     7045 |     1656 |         128 | SUPPORTED        |
| EQUAL_COMPONENT    | share_priority_separation_ge_030 |   0.294819 | 0.349120 |  0.349120 |     7045 |     1656 |         128 | SUPPORTED        |
| NO_F_EXEC          | median_abs_priority_separation   |   0.207126 | 0.234726 |  0.234726 |     7045 |     1656 |         128 | SUPPORTED        |
| NO_F_EXEC          | share_priority_separation_ge_030 |   0.344642 | 0.397178 |  0.397178 |     7045 |     1656 |         128 | SUPPORTED        |
| FLIGHT_EMPHASIS    | median_abs_priority_separation   |   0.195954 | 0.219763 |  0.219763 |     7045 |     1656 |         128 | SUPPORTED        |
| FLIGHT_EMPHASIS    | share_priority_separation_ge_030 |   0.309013 | 0.357223 |  0.357223 |     7045 |     1656 |         128 | SUPPORTED        |
| PASSENGER_EMPHASIS | median_abs_priority_separation   |   0.201087 | 0.224127 |  0.224127 |     7045 |     1656 |         128 | SUPPORTED        |
| PASSENGER_EMPHASIS | share_priority_separation_ge_030 |   0.323918 | 0.367980 |  0.367980 |     7045 |     1656 |         128 | SUPPORTED        |
| OPERATING_EMPHASIS | median_abs_priority_separation   |   0.225845 | 0.251247 |  0.251247 |     7045 |     1656 |         128 | SUPPORTED        |
| OPERATING_EMPHASIS | share_priority_separation_ge_030 |   0.381547 | 0.429170 |  0.429170 |     7045 |     1656 |         128 | SUPPORTED        |

## Stage

| aggregation_view   | stage          | metric                       |   estimate |   ci_low |   ci_high |   n_node |   n_episode | support_status   |
|:-------------------|:---------------|:-----------------------------|-----------:|---------:|----------:|---------:|------------:|:-----------------|
| BASE_EQUAL_DOMAIN  | PRE_IB         | kendall_tau_b                |   0.792662 | 0.771408 |  0.771408 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.056604 |  0.056604 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | PRE_IB         | top_decile_overlap           |   0.545455 | 0.545455 |  0.545455 |      102 |          29 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | kendall_tau_b                |   0.709885 | 0.631123 |  0.631123 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | median_abs_rank_displacement |   0.080949 | 0.093275 |  0.093275 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_IB_PRE_OB | top_decile_overlap           |   0.743056 | 0.755396 |  0.755396 |     1433 |         127 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | kendall_tau_b                |   0.982696 | 0.985549 |  0.985549 |      121 |          82 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| BASE_EQUAL_DOMAIN  | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.583333 |  0.583333 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | kendall_tau_b                |   0.866434 | 0.857765 |  0.857765 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | median_abs_rank_displacement |   0.039216 | 0.033019 |  0.033019 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | PRE_IB         | top_decile_overlap           |   0.818182 | 0.818182 |  0.818182 |      102 |          29 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | kendall_tau_b                |   0.820716 | 0.768009 |  0.768009 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | median_abs_rank_displacement |   0.051640 | 0.057122 |  0.057122 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_IB_PRE_OB | top_decile_overlap           |   0.819444 | 0.834532 |  0.834532 |     1433 |         127 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | kendall_tau_b                |   0.967595 | 0.973988 |  0.973988 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| EQUAL_COMPONENT    | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.500000 |  0.500000 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | kendall_tau_b                |   0.782178 | 0.759071 |  0.759071 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.066038 |  0.066038 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | PRE_IB         | top_decile_overlap           |   0.545455 | 0.545455 |  0.545455 |      102 |          29 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | kendall_tau_b                |   0.683190 | 0.603069 |  0.603069 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | median_abs_rank_displacement |   0.090021 | 0.099783 |  0.099783 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_IB_PRE_OB | top_decile_overlap           |   0.694444 | 0.741007 |  0.741007 |     1433 |         127 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | kendall_tau_b                |   0.983011 | 0.985910 |  0.985910 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| NO_F_EXEC          | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.583333 |  0.583333 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | kendall_tau_b                |   0.859833 | 0.861393 |  0.861393 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | median_abs_rank_displacement |   0.049020 | 0.047170 |  0.047170 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | PRE_IB         | top_decile_overlap           |   0.818182 | 0.818182 |  0.818182 |      102 |          29 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | kendall_tau_b                |   0.815182 | 0.754634 |  0.754634 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | median_abs_rank_displacement |   0.043964 | 0.059291 |  0.059291 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_IB_PRE_OB | top_decile_overlap           |   0.805556 | 0.776978 |  0.776978 |     1433 |         127 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | kendall_tau_b                |   0.983955 | 0.985910 |  0.985910 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| FLIGHT_EMPHASIS    | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.583333 |  0.583333 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | kendall_tau_b                |   0.788779 | 0.786284 |  0.786284 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | median_abs_rank_displacement |   0.058824 | 0.047170 |  0.047170 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | PRE_IB         | top_decile_overlap           |   0.545455 | 0.545455 |  0.545455 |      102 |          29 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | kendall_tau_b                |   0.738623 | 0.662382 |  0.662382 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | median_abs_rank_displacement |   0.056525 | 0.070137 |  0.070137 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_IB_PRE_OB | top_decile_overlap           |   0.736111 | 0.769784 |  0.769784 |     1433 |         127 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | kendall_tau_b                |   0.970426 | 0.976879 |  0.976879 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| PASSENGER_EMPHASIS | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.500000 |  0.500000 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | kendall_tau_b                |   0.688216 | 0.658563 |  0.658563 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | median_abs_rank_displacement |   0.088235 | 0.099057 |  0.099057 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | PRE_IB         | top_decile_overlap           |   0.545455 | 0.545455 |  0.545455 |      102 |          29 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | kendall_tau_b                |   0.561946 | 0.477355 |  0.477355 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | median_abs_rank_displacement |   0.144452 | 0.147505 |  0.147505 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_IB_PRE_OB | top_decile_overlap           |   0.451389 | 0.503597 |  0.503597 |     1433 |         127 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | kendall_tau_b                |   0.991820 | 0.997110 |  0.997110 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | median_abs_rank_displacement |   0.000000 | 0.000000 |  0.000000 |      121 |          82 | SUPPORTED        |
| OPERATING_EMPHASIS | POST_OB_PRE_TO | top_decile_overlap           |   0.923077 | 0.916667 |  0.916667 |      121 |          82 | SUPPORTED        |

## Gates

- BASE reproduction: `PASS`
- Exp4 view-definition consistency: `PASS`
- Model retraining: `false`; calibration refit: `false`; parameter reselection: `false`.
- BLOCKED / ABSTAIN: none in the materialized six-view tables.
