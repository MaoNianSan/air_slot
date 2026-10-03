# JATM Stage-Matched Final-Test Post-Execution Audit

- Status: FAIL
- Epoch root: D:\Local_Projects\airslot\_v2_phase7_execution\artifacts\experiment\final_test_v2_stage_matched
- Execution result SHA256: sha256:65968e4dfaf51ca78e44343c56adfb3c28860e8a88b9aeca9ca8de2c5252b0bc
- Access audit SHA256: sha256:61bb1fca18c741e6ef7be9210d7d6d5619717411e62dd16affd9c538c6aad759
- Freeze artifact hash: sha256:818ba6dbba84c9096171a7c12302f321521933a3996e2b0aee27e6645c898b79

## Checks
- FINAL_TEST_EXECUTION_STATUS: PASS
- CHECKPOINT_HASH_AND_DEPENDENCIES: PASS
- STAGE_I_ACTIONABLE_STAGE_SCOPE: PASS
- STAGE_I_QUEUE_IDENTITY_AND_K: PASS
- CANONICALIZATION_BEFORE_SUPPORT: FAIL
- NO_POOLED_STAGE_I_RANKING: PASS
- STAGE1_OVERALL_OBJECTIVE_THEN_NORMALIZE: PASS
- R_STAR_SUPPORT_QUALIFIED_PRE_TURN_UNION: PASS
- STAGE2_NODE_RELATIVE_SOBT: PASS
- CURRENT_HISTORICAL_EPOCH_ROOTS_DISTINCT: PASS
- CURRENT_RELEASE_ACCESS_AUDIT_BINDING: PASS
- HISTORICAL_EPOCH_HASH_STABLE_READ_ONLY: PASS
- ACTIVE_MODEL_MUTATION: PASS
- SECTION4_H_CAPACITY_STATUS: PASS
- EXECUTION_FREEZE_REVALIDATION: PASS
- SECTION5_PRIMARY_OUTPUT_SURFACES: PASS

## Blocking Failures
- CANONICALIZATION_BEFORE_SUPPORT: {"POST_IB_PRE_OB": {"canonical_stage_node_count": 1433, "duplicate_group_count": 125, "episode_stage_group_count": 127, "max_nodes_in_one_episode_stage_group": 44, "sample_duplicate_groups": {"sha256:8f10fc3d06a1ceca09da607023ad97536daaa41a209b1dbc893855f966c4e6db|POST_IB_PRE_OB": 12, "sha256:bc24e3930bea7251f86fe351a82a9983bae107469a72e1d8d0b10472e2083cac|POST_IB_PRE_OB": 18, "sha256:c048336919f3e39d80d73a48d5b6fd5d5e0e9a3ace24fb201bc4897d9e1d6f19|POST_IB_PRE_OB": 4, "sha256:c76bc28500075caf9834af73b017a1a789116d70bb9c8e405bb1daa51a85b53b|POST_IB_PRE_OB": 7, "sha256:edbcacbc46f77257e51e2fd2273d78cdce82316370d8c4f48868254577e7d34d|POST_IB_PRE_OB": 13}}, "PRE_IB": {"canonical_stage_node_count": 102, "duplicate_group_count": 22, "episode_stage_group_count": 29, "max_nodes_in_one_episode_stage_group": 10, "sample_duplicate_groups": {"sha256:1dd5cc7105f57640595b7343292de576b3098e9d7a0024983d237c37d687bd49|PRE_IB": 5, "sha256:419e155b9874ba532827d8753d6a5c6489c82d4a8e3c49eba2df80cc75b57369|PRE_IB": 5, "sha256:901759615954c2672297afee40f268b7099a7323f77c41e357d1dc42a6819df8|PRE_IB": 2, "sha256:d7ce77792223668e97638f9d4860d230c8160e71e3bc799dfc9459e660ca2ca4|PRE_IB": 6, "sha256:e3a06db01f4ca40f07f3e8841f02d87e9642b25450778e924bcd23643c2103e6|PRE_IB": 6}}}

## Required Guards
- CANONICALIZATION_BEFORE_SUPPORT: FAIL
- H_CAPACITY_ACTIVE_MODEL_MUTATION: NONE
- H_CAPACITY_DOWNSTREAM_EXECUTION: NONE
- SECTION5_PRIMARY_MODEL: H16_FROZEN_PRIMARY
- STAGE1_OVERALL_AGGREGATION: OBJECTIVE_THEN_NORMALIZE
- STAGE2_SOBT_COORDINATE: NODE_RELATIVE_SOBT

## Notes
- The audit reads only persisted epoch/canonical/checkpoint artifacts; it does not read raw Final-Test source data.
- The epoch is sealed as SEALED_AUDIT_FAILED because the frozen canonicalization contract is not satisfied by the persisted Stage-I queues.
- No scientific definition was changed and no Final-Test stage was rerun.
