# JATM Section 5 Development Report

## A. Section 4 H-capacity status
- Status: REUSED_NOT_RERUN
- H8: REUSED_NOT_RERUN
- H16: REUSED_NOT_RERUN
- H32: REUSED_NOT_RERUN
- Selected capacity: 8
- Section 5 primary model: H16_FROZEN_PRIMARY

## B. Attention value
- Materialized rolling node count: 1769
- Materialized canonical counts: {'PRE': 48, 'TAXI': 67, 'TURN': 121}
- Stage-I canonical counts: {'PRE': 48, 'TURN': 121}
- Stage-I eligible counts: {'PRE': 48, 'TURN': 120}
- q grid: [0.05, 0.1, 0.2, 0.3]
- Overall L_att: 0.10608621474321107
- Bootstrap status: COMPLETE

## C. Recovery value
- R* size: 17
- Stage-specific shortlist IDs: {'PRE': ['sha256:1102e3941a4ba02c56ead46df20bb04649038ed44ac7e5d7ef448336f2abc783', 'sha256:4265ee37dba0c96a46e7f000d7a70378132a9ce5c43004e8631e178c2ddad6b2', 'sha256:bcd219b6a06009efa545d617b7ca5e37f9eeeeacceddd96afd9777a245ec1d80', 'sha256:bad37ff8136f26d48e5826a56df1ba7692a52e99ab2c1ff77425abc9e3d44051', 'sha256:ee337d5afe24bc12ccb7088a360a521511cf786935110a3a1460c47782156d95'], 'TURN': ['sha256:b61b41dfbb5e9a4fd307732b727adaab5722ded5b97efe7f9aa3f903cf057e8f', 'sha256:93f5c0828bd5b82d3832d919d8fe5b8f4300cfe6c9c3e953746e86d251821675', 'sha256:3a2e051d5300bc13cdeb1205da3de6f9b24d42d7dd6550f716e0fce91548828b', 'sha256:9c905603d962258ebd674ea474cd50ccde1889ee9fecd1af27b961746a52ab03', 'sha256:14c8a0e539a0f474de7629fc92576c735804e76360b6b724a2b7dd0b3a4415fb', 'sha256:10809eca963a9c4c722ab89c586e46c0a44162740e22dadcf03ed15806e37eb6', 'sha256:f04baf4fb53741cd69106693fe8001b9b6b936bd7510e514b20dd2053435a4f7', 'sha256:2499816614111cc383b6c624095d7defc8d995e92089a1aaa28e4ae01985699f', 'sha256:d8b1aa0a19b345d100b48a09dda67fd5e213f801bf849f37cfc19b3ebf52c069', 'sha256:5d4aaf5d038a4ef9d1787f7054b0cd411efbb12bf18cafdd47f326e4d452eb3b', 'sha256:c52a32811d10ab099df28a44fcbb319a95f6bd349963617bd381db4f0f7b31ba', 'sha256:e428615e517b78bc97e766c56032e1531e4345ec50c396659dbc43989fa6afeb']}
- Stage-specific R* IDs: {'PRE': ['sha256:bcd219b6a06009efa545d617b7ca5e37f9eeeeacceddd96afd9777a245ec1d80', 'sha256:1102e3941a4ba02c56ead46df20bb04649038ed44ac7e5d7ef448336f2abc783', 'sha256:4265ee37dba0c96a46e7f000d7a70378132a9ce5c43004e8631e178c2ddad6b2', 'sha256:ee337d5afe24bc12ccb7088a360a521511cf786935110a3a1460c47782156d95', 'sha256:bad37ff8136f26d48e5826a56df1ba7692a52e99ab2c1ff77425abc9e3d44051'], 'TURN': ['sha256:93f5c0828bd5b82d3832d919d8fe5b8f4300cfe6c9c3e953746e86d251821675', 'sha256:e428615e517b78bc97e766c56032e1531e4345ec50c396659dbc43989fa6afeb', 'sha256:10809eca963a9c4c722ab89c586e46c0a44162740e22dadcf03ed15806e37eb6', 'sha256:b61b41dfbb5e9a4fd307732b727adaab5722ded5b97efe7f9aa3f903cf057e8f', 'sha256:3a2e051d5300bc13cdeb1205da3de6f9b24d42d7dd6550f716e0fce91548828b', 'sha256:5d4aaf5d038a4ef9d1787f7054b0cd411efbb12bf18cafdd47f326e4d452eb3b', 'sha256:9c905603d962258ebd674ea474cd50ccde1889ee9fecd1af27b961746a52ab03', 'sha256:d8b1aa0a19b345d100b48a09dda67fd5e213f801bf849f37cfc19b3ebf52c069', 'sha256:2499816614111cc383b6c624095d7defc8d995e92089a1aaa28e4ae01985699f', 'sha256:14c8a0e539a0f474de7629fc92576c735804e76360b6b724a2b7dd0b3a4415fb', 'sha256:c52a32811d10ab099df28a44fcbb319a95f6bd349963617bd381db4f0f7b31ba', 'sha256:f04baf4fb53741cd69106693fe8001b9b6b936bd7510e514b20dd2053435a4f7']}
- Flattened R* compatibility IDs: ['sha256:bcd219b6a06009efa545d617b7ca5e37f9eeeeacceddd96afd9777a245ec1d80', 'sha256:1102e3941a4ba02c56ead46df20bb04649038ed44ac7e5d7ef448336f2abc783', 'sha256:4265ee37dba0c96a46e7f000d7a70378132a9ce5c43004e8631e178c2ddad6b2', 'sha256:ee337d5afe24bc12ccb7088a360a521511cf786935110a3a1460c47782156d95', 'sha256:bad37ff8136f26d48e5826a56df1ba7692a52e99ab2c1ff77425abc9e3d44051', 'sha256:93f5c0828bd5b82d3832d919d8fe5b8f4300cfe6c9c3e953746e86d251821675', 'sha256:e428615e517b78bc97e766c56032e1531e4345ec50c396659dbc43989fa6afeb', 'sha256:10809eca963a9c4c722ab89c586e46c0a44162740e22dadcf03ed15806e37eb6', 'sha256:b61b41dfbb5e9a4fd307732b727adaab5722ded5b97efe7f9aa3f903cf057e8f', 'sha256:3a2e051d5300bc13cdeb1205da3de6f9b24d42d7dd6550f716e0fce91548828b', 'sha256:5d4aaf5d038a4ef9d1787f7054b0cd411efbb12bf18cafdd47f326e4d452eb3b', 'sha256:9c905603d962258ebd674ea474cd50ccde1889ee9fecd1af27b961746a52ab03', 'sha256:d8b1aa0a19b345d100b48a09dda67fd5e213f801bf849f37cfc19b3ebf52c069', 'sha256:2499816614111cc383b6c624095d7defc8d995e92089a1aaa28e4ae01985699f', 'sha256:14c8a0e539a0f474de7629fc92576c735804e76360b6b724a2b7dd0b3a4415fb', 'sha256:c52a32811d10ab099df28a44fcbb319a95f6bd349963617bd381db4f0f7b31ba', 'sha256:f04baf4fb53741cd69106693fe8001b9b6b936bd7510e514b20dd2053435a4f7']
- Flattened union semantics: COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION
- Stage counts: {'PRE': 5, 'TURN': 12}
- Stage summary: [{'IQR_J_star': 0.35175770502117687, 'IQR_J_zero': 0.35570778706914596, 'IQR_V': 0.013303656747155168, 'IQR_positive_u': 3.75, 'N_actionable': 5, 'P90_V': 0.052330074884311434, 'P90_positive_u': 15.500000000000004, 'activation_count': 4, 'activation_share': 0.8, 'median_J_star': 0.9110987112629263, 'median_J_zero': 0.9636240024164796, 'median_V': 0.005816490147251052, 'median_positive_u': 5.0, 'positive_V_count': 4, 'positive_V_share': 0.8, 'stage': 'PRE'}, {'IQR_J_star': 0.24463914918396024, 'IQR_J_zero': 0.30304305529430897, 'IQR_V': 0.010356947822268092, 'IQR_positive_u': 0.0, 'N_actionable': 12, 'P90_V': 0.07209953729377926, 'P90_positive_u': 14.000000000000002, 'activation_count': 5, 'activation_share': 0.4166666666666667, 'median_J_star': 0.9579163239277431, 'median_J_zero': 0.9579163239277431, 'median_V': 0.0, 'median_positive_u': 5.0, 'positive_V_count': 5, 'positive_V_share': 0.4166666666666667, 'stage': 'TURN'}]

## D. Information value
- Components: ['ROLLING_HISTORY', 'DISTRIBUTIONAL_INFORMATION', 'CROSS_STATE_DEPENDENCE', 'MARGINAL_UNCERTAINTY']
- CROSS_STATE_DEPENDENCE_L_ATT: {'ci_high': 0.008962858065093508, 'ci_low': 0.0, 'comparator': 'HISTORY_MARGINAL', 'definition': 'L_HISTORY_MARGINAL - L_HISTORY_JOINT', 'information_component': 'CROSS_STATE_DEPENDENCE', 'reference': 'HISTORY_JOINT', 'value': 0.005434626866172922}
- CROSS_STATE_DEPENDENCE_L_REC: {'ci_high': 0.8914421543412551, 'ci_low': 0.0, 'comparator': 'HISTORY_MARGINAL', 'definition': 'L_HISTORY_MARGINAL - L_HISTORY_JOINT', 'information_component': 'CROSS_STATE_DEPENDENCE', 'reference': 'HISTORY_JOINT', 'value': 0.5090467564697767}
- MARGINAL_UNCERTAINTY_INCREMENT_L_ATT: {'ci_high': 0.45268376713609604, 'ci_low': 0.4457387869039205, 'comparator': 'POINT_MINUS_MARGINAL', 'definition': 'L_HISTORY_POINT - L_HISTORY_MARGINAL', 'information_component': 'MARGINAL_UNCERTAINTY', 'paired_bootstrap': True, 'reference': 'HISTORY_POINT_MINUS_HISTORY_MARGINAL', 'value': 0.4492933210879138}
- MARGINAL_UNCERTAINTY_INCREMENT_L_REC: {'ci_high': 0.6092497439737172, 'ci_low': 0.5810154820593822, 'comparator': 'POINT_MINUS_MARGINAL', 'definition': 'L_HISTORY_POINT - L_HISTORY_MARGINAL', 'information_component': 'MARGINAL_UNCERTAINTY', 'paired_bootstrap': True, 'reference': 'HISTORY_POINT_MINUS_HISTORY_MARGINAL', 'value': 0.5952918817011299}
- Paired increments: [{'A0': None, 'A5': None, 'L_att': 0.4492933210879138, 'L_att_ci_high': 0.45268376713609604, 'L_att_ci_low': 0.4457387869039205, 'L_rec': 0.5952918817011299, 'L_rec_ci_high': 0.6092497439737172, 'L_rec_ci_low': 0.5810154820593822, 'comparator': 'POINT_MINUS_MARGINAL', 'delta_J': 0.1453785654730112, 'false_activation': None, 'information_component': 'MARGINAL_UNCERTAINTY', 'missed_activation': None, 'over_recovery': None, 'reference_V': None, 'stage1_reassigned_share': None, 'under_recovery': None}]

## E. Robustness
- Rows: 20

## F. Definition and orchestration provenance
- SCIENTIFIC_DEFINITION_CHANGED: STAGE1_EMPIRICAL_ORCHESTRATION_PATCH_ONLY
- M1_DEFINITION_CHANGED: NO
- M2_DEFINITION_CHANGED: NO
- M3_SELECTOR_DEFINITION_CHANGED: NO
- M3_STAGE2_DEFINITION_CHANGED: NO
- M4_LOSS_DEFINITION_CHANGED: NO
- SCIENTIFIC_ORCHESTRATION_CHANGED: YES
- SCIENTIFIC_ORCHESTRATION_PATCH: STAGE_MATCHED_PRE_TURN_SCREENING

## G. Final-Test readiness
- Development ready for freeze: YES
- Final-Test ready to open: YES
- Final-Test complete: NO
- Development readiness status: DEVELOPMENT_READY_FOR_FREEZE
- Blockers: []
