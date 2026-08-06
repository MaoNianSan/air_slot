# M1

STATUS: COMPLETE

Evidence:

- PRE schema and current fast output contain previous-leg fields.
- Stored M1 feature contract includes previous-leg inputs for training and inference.
- Decision-time leakage checks pass.
- Matcher backtracks past overlapping adjacent records to the latest valid predecessor.
- Explicit feature-order parity rejection (`M1_INFERENCE_FEATURE_ORDER_MISMATCH`).
- Fault probe `case_overlap_backtrack` / `case_feature_order` PASS; matcher tests 11 PASS.

# M3

STATUS: COMPLETE

Evidence:

- 26 formal actions are defined and present in M4 candidate-screen output.
- Parameter schema, version lineage, fail-closed typed gates, and stable draws exist.
- Single authoritative action loader (`action_contract.py`); strict boolean schema.
- Fault probe `case_string_boolean` / `case_duplicate_a00` / `case_action_count` PASS.

Remaining:

- Resolve/explain the 13 zero-scored formal actions in the real fast output
  (synthetic reachability tests pass; real-output resolution is a scientific item).

# Ranking

STATUS: COMPLETE

Evidence:

- K=1/2/3/5 output schemas and downstream comparisons exist and validate for nonempty candidates.
- Padding is null and excluded from metrics in existing output.
- Required expected-residual tie-break (`score, expected_residual, priority, action_id`).
- Fixed-width padding (11 null rows) for zero candidates.
- Global/Local candidate-set mismatch rejected via `CandidateSetContractError`.
- Fault probe `case_expected_residual_tie` / `case_zero_candidate` / `case_padding_a00` /
  `case_candidate_mismatch` PASS; ranking contract tests PASS.
