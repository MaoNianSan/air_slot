# M4 and Downstream Code Audit

Audit date: 2026-08-02

M4_CODE_AUDIT=FAIL
M4_PADDING_AUDIT=FAIL
OVERALL_ADV_CODE_AUDIT=FAIL
PART_ADV_CODE_AUDIT=PASS

## Passing evidence

- `ranking_contract.py` is the shared ranking implementation used by overall_run, overall_adv, and part_adv.
- Existing output materializes depths 1/2/3/5 from one full ranking, with the required schema and 4,297 null-action padding rows.
- Existing K1 recommendations contain 640 episodes and agree with the K1 view.
- Padding is excluded from ranking set metrics and never repeats A00.
- overall_adv emits ordered disagreement, set disagreement, order-only disagreement, overlap, and mutually exclusive comparison classes.
- part_adv registry lineage matches the same M1 feature contract, 26-action M3 library, and 1/2/3/5 ranking contract.

## Blocking defects

- The required tie-break is `score, expected_residual, priority, action_id`; the implementation uses `score, expected_implementation_cost_rmb, priority, action_id` at `ranking_contract.py:151-160`. Active tied scores ranked A11 before lower-residual A12.
- Zero-real-candidate input returns zero rows instead of 11 padding rows across K=1/2/3/5.
- Global/Local candidate-set mismatch is accepted and classified rather than rejected, so shared-candidate support is not enforced.
- Ranking depths are repeated in downstream production metadata rather than imported from the shared constant.

Existing nonzero-candidate outputs are structurally valid, but the full required boundary and comparison contract are not.
