# JATM Section 5 Development Report

## A. Section 4 H-capacity status
- H8 complete: COMPLETE
- H16 complete: COMPLETE
- H32 complete: COMPLETE
- Selected capacity: 8

## B. Attention value
- Canonical counts: {'PRE': 48, 'TURN': 121, 'TAXI': 67}
- q grid: [0.05, 0.1, 0.2, 0.3]
- Overall L_att: 0.09581692141611248
- Bootstrap status: COMPLETE

## C. Recovery value
- R* size: 17
- Stage counts: {'TURN': 12, 'PRE': 5}
- Stage summary: [{'stage': 'PRE', 'N_actionable': 5, 'median_J_zero': 0.9636240024164796, 'IQR_J_zero': 0.35570778706914596, 'median_J_star': 0.9110987112629263, 'IQR_J_star': 0.35175770502117687, 'median_V': 0.005816490147251052, 'IQR_V': 0.013303656747155168, 'P90_V': 0.052330074884311434, 'positive_V_count': 4, 'positive_V_share': 0.8, 'activation_count': 4, 'activation_share': 0.8, 'median_positive_u': 5.0, 'IQR_positive_u': 3.75, 'P90_positive_u': 15.500000000000004}, {'stage': 'TURN', 'N_actionable': 12, 'median_J_zero': 0.9579163239277431, 'IQR_J_zero': 0.30304305529430897, 'median_J_star': 0.9579163239277431, 'IQR_J_star': 0.24463914918396024, 'median_V': 0.0, 'IQR_V': 0.010356947822268092, 'P90_V': 0.07209953729377926, 'positive_V_count': 5, 'positive_V_share': 0.4166666666666667, 'activation_count': 5, 'activation_share': 0.4166666666666667, 'median_positive_u': 5.0, 'IQR_positive_u': 0.0, 'P90_positive_u': 14.000000000000002}]

## D. Information value
- Components: ['ROLLING_HISTORY', 'DISTRIBUTIONAL_INFORMATION', 'CROSS_STATE_DEPENDENCE', 'MARGINAL_UNCERTAINTY']
- Paired increments: [{'information_component': 'MARGINAL_UNCERTAINTY', 'comparator': 'POINT_MINUS_MARGINAL', 'L_att': 0.41927374076004653, 'L_att_ci_low': 0.4011322637396169, 'L_att_ci_high': 0.4073248528254373, 'delta_J': None, 'reference_V': None, 'L_rec': 0.4909532435302233, 'L_rec_ci_low': 0.5810154820593822, 'L_rec_ci_high': 0.6092497439737172, 'stage1_reassigned_share': None, 'A0': None, 'A5': None, 'missed_activation': None, 'false_activation': None, 'under_recovery': None, 'over_recovery': None}]

## E. Robustness
- Rows: 20

## F. Final-Test readiness
READY_FOR_FREEZE
- Blockers: []
