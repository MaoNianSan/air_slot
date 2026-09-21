# Air Slot — Delay vs Consequence Stage-I Held-Out Results (sealed canonical-v2 projection)

Read-only manuscript-facing projection of the sealed canonical stage-matched
Final-Test epoch. No scientific computation, no bootstrap, no raw-data access.

## Declarations

- projection_only = `true`
- scientific_recomputation_performed = `false`
- final_test_raw_data_read = `false`
- new_final_test_execution = `false`
- scientific_definition_changed = `false`
- source_representation = `HISTORY_JOINT`
- source_representation_id = `HISTORY_H16:JOINT`
- nominal_q = `0.1`
- stage_evaluation = `PRE_AND_TURN_EVALUATED_INDEPENDENTLY`
- overall_rule = `STAGE_OBJECTIVES_THEN_NORMALIZE`
- pooled_stage1_ranking = `false`
- source checkpoint: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/checkpoints/ATTENTION_DECISIONS.json` (schema `AIR_SLOT_V2_PHASE7_ATTENTION_DECISIONS_V1`)
- source checkpoint file SHA256: `sha256:fbcf25389312ac799e19f83469369eb9fad1df080e5fed411227211248badd92`
- source checkpoint payload hash: `sha256:23841da03e74af349988c14a581429a16da00bf73e096ecf430dc311426bf0df`
- canonical-v2 epoch identity: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2` — branch `v2/phase7-gate-a` @ `8360dd7d88958ae139322d0ea5c66f1c5fe6455c` (tag `jatm-final-test-freeze-20260920`); EPOCH_SEAL `SEALED_AUDIT_PASS` `sha256:eb4a22a2079183f1eca3511c5002334eeccb9f19b282f9781189475ce9c21614`
- no confidence interval is created and no bootstrap is started; this projection reports deterministic held-out point results only

## Paper-facing table (Section 5.1)

| Stage | Actionable candidates | K | Positions changed: delay vs consequence | Changed share | Delay-based consequence value retained |
|---|---|---|---|---|---|
| PRE | 29 | 3 | 0/3 | 0.0 | 1.0 |
| TURN | 127 | 13 | 5/13 | 0.38461538461538464 | 0.9275697132482993 |
| Overall | 156 | 16 | 5/16 | 0.3125 | 0.941662056595928 |

Zero changed positions means that delay-based and consequence-based screening selected exactly the same shortlist at that stage; it is a realized decision result, not a missing value or an unexecuted comparison.

## Validation summary

- source checkpoint hash verification: schema match, file/payload hashes verified against both `FINAL_TEST_EXECUTION_RESULT.json` and `POST_EXECUTION_AUDIT.json` — all `True`
- PRE/TURN candidate-set equality (cohort, k, q, eligible IDs, support status) between delay and consequence: `True`
- objective identity checks: `True`
- overall aggregation identity: `True`
- no raw-data access / no recomputation / no bootstrap / no new epoch (all boundary flags false as required): `True`

