from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-08-02"


def write(name: str, text: str) -> None:
    (REPORTS / name).write_text(text.strip() + "\n", encoding="utf-8")


def main() -> None:
    fault = pd.read_csv(REPORTS / "FAULT_INJECTION_RESULTS.csv")
    parallel = json.loads((REPORTS / "PARALLEL_DETERMINISM_RESULTS.json").read_text(encoding="utf-8"))
    reach = pd.read_csv(REPORTS / "M3_ACTION_REACHABILITY.csv")
    zero_scored = reach.loc[reach["scored_count"].eq(0), "action_id"].astype(str).tolist()
    fault_failures = fault.loc[fault["status"].eq("FAIL"), "injection"].astype(str).tolist()

    write(
        "STATIC_HARDCODE_AUDIT.md",
        f"""
# Static Hardcode Audit

Audit date: {DATE}

STATIC_HARDCODE_AUDIT=FAIL

## Findings

- R3 scientific thresholds are centralized in `pre/config/predecessor_matching.yaml`; no production-code copies of `1568.34` or `2880` were found.
- The ranking depths have one shared definition at `ranking_contract.py:9`, but are independently repeated in production metadata at `overall_run/src/pipeline_finalize.py:255`, `overall_run/src/pipeline_finalize.py:336`, `overall_adv/src/pipeline.py:275`, and `part_adv/src/pipeline.py:192`. This violates the single-authority requirement.
- The formal M3 action set is independently encoded in `overall_run/src/m3.py:13-23`, `overall_run/src/config.py:223-230`, `overall_run/src/selfcheck.py:135-136`, `pre/config/actions.yaml`, and `overall_run/config/m3_response_v3_expanded_provisional.yaml`. A change can therefore pass one layer and disagree with another.
- `fast_three_change_dev` is isolated from formal fast in the run configs and existing outputs. However, all four `clean.py` files restrict `--mode` to a fixed enum (`pre/clean.py:22-33` and equivalents), so the development output name cannot be dry-run cleaned directly.
- Runtime `n_jobs` is propagated through the CLI and run plan rather than hard-coded into scientific calculations.

## Decision

The threshold and output-path checks pass, but duplicated action/ranking authorities and the non-cleanable development profile make the static hardcode audit fail.
""",
    )

    write(
        "STATIC_ERROR_HANDLING_AUDIT.md",
        f"""
# Static Error Handling Audit

Audit date: {DATE}

STATIC_ERROR_HANDLING_AUDIT=FAIL

## Confirmed protections

- Missing required PRE predecessor keys raise at `pre/src/pipeline_config.py:126-143`.
- Missing/unsupported typed gates fail closed at `overall_run/src/m4_screening.py:242-260`.
- Ranking padding with a non-null action is rejected at `ranking_contract.py:125-132`.
- Missing upstream artifacts are rejected by overall_adv and part_adv loaders.

## Defects

- PRE configuration uses an unrestricted recursive merge (`pre/src/pipeline_config.py:26-33`) and its validator does not reject unknown fields. The active injection `unknown PRE override field added` was silently accepted.
- overall_adv and part_adv apply shallow `cfg.update(...)` overrides (`overall_adv/src/pipeline_analysis.py:26-30`, `part_adv/src/pipeline_inputs.py:22-26`) without a schema or unknown-field rejection.
- `build_predecessor_features` catches broad `Exception` and silently substitutes `NaN` for movement and turnaround reference failures (`pre/src/predecessor_matcher.py:271-286`), which can conceal programming and schema errors.
- M3 boolean fields are not type-validated: injected string `"false"` remains a truthy string in `Action.capacity_required`.
- The ranking builder returns an empty frame for empty input (`ranking_contract.py:34-36`), so a known zero-candidate episode cannot receive the required fixed-width padding.
- The Global/Local ranking comparator treats a candidate-set contract violation as a normal `DIFFERENT_SET` result instead of rejecting it.

## Validator depth

Existing validators inspect schemas, row counts, lineage, padding, and artifact hashes. They are stronger than file-existence checks, but the defects above remain outside their rejection surface.
""",
    )

    write(
        "M1_MATCHER_CODE_AUDIT.md",
        f"""
# M1 Matcher Code Audit

Audit date: {DATE}

M1_CODE_AUDIT=FAIL

## Correctly implemented

- `icao24` is normalized before matching in `pre/src/episode.py:92-96` using `pre/src/input.py:41-43`.
- Legs are stably sorted by `icao24`, `firstseen_utc`, `lastseen_utc`, and `flight_id` at `pre/src/predecessor_matcher.py:117-120`.
- Temporal order, overlap, gap, airport continuity, registration, typecode, endpoint quality, and split/merge risk produce explicit rejection reasons at `pre/src/predecessor_matcher.py:134-240`.
- Snapshot times are generated from `firstseen_utc + ratio * reference_movement_time` at `pre/src/snapshot.py:21-43`; `lastseen_utc` is used only to determine whether the snapshot still lies inside the current flight.
- Availability gating at `pre/src/predecessor_matcher.py:339-365` passed the required counterexample: t1 unavailable, t2/t3 available.
- The existing fast output has 142,659 snapshots, zero supported-predecessor availability violations, and predecessor features in the published schema.

## Blocking matcher defect

The candidate builder uses exactly one `groupby("icao24").shift(1)` at `pre/src/predecessor_matcher.py:127-129`. It rejects an overlapping immediate row but does not search earlier rows for the latest valid non-overlapping predecessor.

Active counterexample:

- `valid_old` ends before the current flight and has airport continuity.
- `overlap` is the immediately preceding sorted row but overlaps the current flight.
- Expected selection: `valid_old`.
- Actual selection: `overlap`, then rejection `TEMPORAL_OVERLAP`.

This is a false-negative predecessor match and directly matches the workflow's warned `shift(1)` failure mode.

## Data characteristics, not parameter approval

- Candidate rate: 89.62%.
- Supported rate: 9.05%.
- The largest rejection class is `AIRPORT_DISCONTINUITY` (91,251 snapshot rows).
- Train/validation/test supported rates are close (9.09%, 9.00%, 9.00%), but no R3 parameter approval is made because code correctness failed first.
""",
    )

    write(
        "M1_TRAIN_INFERENCE_PARITY_AUDIT.md",
        f"""
# M1 Train/Inference Parity Audit

Audit date: {DATE}

M1_TRAIN_INFERENCE_PARITY=FAIL

## Evidence

- Training features are selected from the frozen allowlist in `overall_run/src/m1_training.py:8-55` and stored in `M1Artifact.feature_columns`.
- Inference selects `df[self.feature_columns]` before applying the fitted transformer at `overall_run/src/m1.py:61-68`.
- The actual development artifact records `feature_schema_hash`, `feature_columns`, and `M1_PREVIOUS_LEG_V1`; predecessor features are present in both training and inference tests.

## Missing guard

The requested active mutation of feature order was not rejected by the fitted transformer, and there is no separate inference-time assertion that the stored feature-order hash equals the expected contract hash. Named-column selection makes ordinary input column order harmless, but a corrupted artifact/order contract is not explicitly detected. Under the workflow's strict fault-injection rule, parity is therefore FAIL rather than inferred PASS.
""",
    )

    write(
        "M1_LEAKAGE_CODE_AUDIT.md",
        f"""
# M1 Leakage Code Audit

Audit date: {DATE}

M1_LEAKAGE_AUDIT=PASS

- The M1 feature contract is an allowlist and additionally removes `lastseen`, target/outcome, `future_`, `successor_`, action, scenario, residual, score, and rank patterns in `overall_run/config/scientific.yaml:72-83`.
- An injected `future_successor_delay` was excluded even after it was added to the allowlist.
- Current state extraction restricts event and availability time to the decision time at `pre/src/snapshot.py:116-121`.
- Predecessor features are nulled when their availability time is later than the snapshot decision time.
- Existing fast evidence contains zero supported-predecessor availability violations.

Previous-leg information available at decision time? YES, for rows marked `has_supported_predecessor=true`.
""",
    )

    write(
        "M3_CODE_AUDIT.md",
        f"""
# M3 Code Audit

Audit date: {DATE}

M3_CODE_AUDIT=FAIL
M3_TYPED_GATE_AUDIT=PASS
M3_RANDOMNESS_AUDIT=PASS
M3_ACTION_REACHABILITY=FAIL

## Passing evidence

- The merged formal configuration contains exactly 26 ordered actions and complete response-parameter fields; removing one action and duplicating A00 are rejected.
- S01/S02 are excluded from the formal library.
- Response means, costs, concentration, cost CV, and failure probability are range-validated in `overall_run/src/m3.py:106-190`.
- Required typed gates fail closed when the value or evidence column is missing/unsupported.
- M3 draws use stable per-action seed namespaces (`overall_run/src/m3.py:213-223`); reversing action iteration order produced identical success, recovery, and cost arrays.
- The current candidate-screen output contains all 26 formal action IDs.

## Blocking defects

- The action inventory has multiple independent authorities instead of one source.
- Boolean fields are not type-checked. Injected `capacity_required: "false"` is stored as the string `"false"`, and `bool("false")` is true.
- Thirteen formal actions have `scored_count=0` in the current fast output: `{', '.join(zero_scored)}`. Their zero reachability is explained by trigger/value/gate failures, but the workflow requires every zero-scored formal action to be explicitly resolved before approval.
- Extreme provisional actions A61/A62, A71-A73, and A81-A83 never reach scoring in this development output; this blocks action-reachability confirmation even though fail-closed gating itself is correct.

Detailed counts are in `reports/M3_ACTION_REACHABILITY.csv`.
""",
    )

    write(
        "M4_CODE_AUDIT.md",
        f"""
# M4 and Downstream Code Audit

Audit date: {DATE}

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
""",
    )

    table = fault[["injection", "expected_detection", "status", "mechanism", "detail"]].to_markdown(index=False)
    write(
        "FAULT_INJECTION_AUDIT.md",
        f"""
# Fault Injection Audit

Audit date: {DATE}

FAULT_INJECTION_STATUS=FAIL

Results: {int(fault['status'].eq('PASS').sum())} PASS, {int(fault['status'].eq('FAIL').sum())} FAIL.

{table}

Uncaught or unsatisfied injections: {', '.join(fault_failures)}.

The audit probe is `reports/code_audit_fault_probe.py`; detailed machine-readable results are `FAULT_INJECTION_RESULTS.csv` and `FAULT_INJECTION_RESULTS.json`. No production code or data was modified.
""",
    )

    write(
        "PARALLEL_DETERMINISM_AUDIT.md",
        f"""
# Parallel Determinism Audit

Audit date: {DATE}

PARALLEL_DETERMINISM_STATUS={parallel['status']}

- Shared PRE input: `pre/output/fast_three_change_dev`.
- 1-thread downstream output: `fast_code_audit_n1`.
- 14-thread comparison output: `fast_three_change_dev`.
- overall_run, overall_adv, and part_adv 1-thread runs all passed their validators.
- Compared parquet files: {parallel['parquet_file_count']}.
- Parquet failures: {parallel['parquet_fail_count']}.
- Numeric tolerance: atol={parallel['numeric_tolerance']['atol']}, rtol={parallel['numeric_tolerance']['rtol']}.
- Maximum scientific numeric absolute difference: {parallel['max_abs_diff']}.
- Compared summary/registry logical files: {parallel['registry_file_count']}.
- Logical registry failures after excluding run IDs, timestamps, wall time, paths, hashes, and worker metadata: {parallel['registry_fail_count']}.
- The only raw parquet difference before excluding performance-only fields was M1 prediction timing; CRPS, Brier, coverage, actions, scores, rankings, candidates, and summary statistics were identical.

Detailed comparisons are in `PARALLEL_DETERMINISM_FILE_COMPARISON.csv` and `PARALLEL_DETERMINISM_REGISTRY_COMPARISON.csv`.
""",
    )

    write(
        "DEV_FAST_CHAIN_AUDIT.md",
        f"""
# Isolated Fast Development Chain Audit

Audit date: {DATE}

DEV_FAST_CHAIN_STATUS=FAIL

## Existing chain evidence

- PRE 1-thread run `pre-fast-20260802T071319Z-fc0ea135`: PASS.
- overall_run 14-thread run `20260802_160200_fast_three_change_dev_d4aabdf0_6516ede`: engineering core PASS, publication NOT_ALLOWED.
- overall_adv 14-thread run `overall-adv-fast_three_change_dev-20260802T080421Z-a5a18264`: PASS.
- part_adv 14-thread run `part-adv-fast_three_change_dev-20260802T080502Z-510210c6`: PASS.
- Lineage records M1_PREVIOUS_LEG_V1, M3_RESPONSE_V3_EXPANDED_PROVISIONAL, 26 actions, and M4_RANKING_1235_V1_PROVISIONAL.
- Existing stale artifact count is zero in downstream validators.

## Why the required recheck failed

The workflow requires `clean --dry-run fast_three_change_dev` before rerun. The clean CLIs accept only fixed modes and cannot target `fast_three_change_dev`; using `--mode fast` would target formal fast. Therefore no destructive clean and no redundant 14-thread rerun were performed. The existing chain is engineering-valid, but the required safely isolated rerun contract is not satisfied.

Middle and full were not run. Formal baseline was not replaced.
""",
    )

    write(
        "CODE_AUDIT_PARAMETER_REVIEW.md",
        f"""
# Parameter Review Gate

Audit date: {DATE}

R3_PARAMETER_REVIEW=PENDING
M3_PARAMETER_REVIEW=PENDING

Parameter review is intentionally not started because static, M1, M3, M4, fault-injection, and isolated-clean gates are not all PASS. The observed 9.05% predecessor support rate and M3 reachability counts are descriptive audit evidence only, not parameter approval.

No provisional parameter was promoted, no parameter hash/version was approved, and no test/full outcome was used for tuning.
""",
    )

    statuses = [
        ("STATIC_CODE_AUDIT", "FAIL", "duplicate authorities, unknown config fields, unsafe dev clean scope"),
        ("M1_CODE_AUDIT", "FAIL", "shift(1) overlap counterexample"),
        ("M1_TRAIN_INFERENCE_PARITY", "FAIL", "feature-order mutation lacks explicit contract rejection"),
        ("M1_LEAKAGE_AUDIT", "PASS", "allowlist/prohibited patterns and availability gates"),
        ("M3_CODE_AUDIT", "FAIL", "string boolean parsing and duplicate authorities"),
        ("M3_ACTION_REACHABILITY", "FAIL", f"{len(zero_scored)} formal actions scored_count=0"),
        ("M3_TYPED_GATE_AUDIT", "PASS", "missing/unsupported gates fail closed"),
        ("M3_RANDOMNESS_AUDIT", "PASS", "stable per-action seeds"),
        ("M4_CODE_AUDIT", "FAIL", "wrong tie-break and zero-candidate boundary"),
        ("M4_PADDING_AUDIT", "FAIL", "0-candidate fixed width unsupported"),
        ("OVERALL_ADV_CODE_AUDIT", "FAIL", "candidate-set mismatch not rejected"),
        ("PART_ADV_CODE_AUDIT", "PASS", "shared lineage and existing output contract"),
        ("FAULT_INJECTION_STATUS", "FAIL", f"{int(fault['status'].eq('FAIL').sum())} injections unsatisfied"),
        ("PARALLEL_DETERMINISM_STATUS", "PASS", "63 parquets and 6 logical registries equal"),
        ("DEV_FAST_CHAIN_STATUS", "FAIL", "dev output cannot be clean dry-run scoped"),
        ("R3_PARAMETER_REVIEW", "PENDING", "blocked by code audit"),
        ("M3_PARAMETER_REVIEW", "PENDING", "blocked by code audit"),
        ("CODE_CORRECTNESS_CONFIRMED", "NO", "blocking defects remain"),
        ("FORMAL_FAST_ALLOWED", "NO", "all Phase J gates not PASS"),
        ("MIDDLE_ALLOWED", "NO", "explicitly prohibited"),
        ("FULL_ALLOWED", "NO", "explicitly prohibited"),
        ("NEXT_ALLOWED_COMMAND", "修复代码错误", "do not promote parameters or run formal fast"),
        ("WAITING_FOR_USER", "YES", "audit complete and stopped"),
    ]
    pd.DataFrame(statuses, columns=["check", "status", "evidence"]).to_csv(
        REPORTS / "CODE_AUDIT_FINAL_STATUS.csv", index=False
    )
    status_lines = "\n".join(f"{name}={value}" for name, value, _ in statuses)
    write(
        "CODE_AUDIT_FINAL_STATUS.md",
        f"""
# Air Slot Code Audit Final Status

Audit date: {DATE}

{status_lines}

## Blocking findings

1. M1 immediate-row `shift(1)` misses an older valid predecessor when the adjacent row overlaps.
2. M3 string booleans are not rejected or normalized, and the formal action set has multiple authorities.
3. M4 tie-break uses implementation cost instead of expected residual.
4. Zero-candidate ranking cannot emit fixed-width padding.
5. overall_adv does not reject Global/Local candidate-set mismatch.
6. Development output cannot be targeted by clean dry-run.
7. Seven active fault injections remain unsatisfied.

## Confirmed positives

- All 227 existing tests pass.
- All 494 protected formal files remain hash-identical; 118 pre-existing non-report/non-output worktree files also show zero audit-induced drift.
- M1 leakage protections pass.
- Typed gates fail closed.
- M3 action-order random draws are stable.
- 1-thread versus 14-thread scientific outputs are deterministic.
- No middle/full run, publication promotion, parameter approval, or formal-baseline replacement occurred.
""",
    )

    write(
        "MODEL_MODIFICATION_COMPLETION_AUDIT.md",
        f"""
# Model Modification Completion Audit

Audit date: {DATE}

M1_STATUS=PARTIAL
M3_STATUS=PARTIAL
RANKING_STATUS=PARTIAL

## M1

Previous-leg features exist in PRE schema, flow into the M1 training/inference contract, and are present in existing output. Completion is PARTIAL because the one-row `shift(1)` matcher fails a valid-overlap counterexample and train/inference order corruption lacks an explicit contract rejection.

## M3

The 26-action V3 provisional library exists, all action IDs enter the candidate-screen schema, parameters and versions are recorded, and typed gates fail closed. Completion is PARTIAL because the inventory has multiple authorities, string booleans are unsafe, and {len(zero_scored)} formal actions have zero scored rows in the fast output.

## Ranking

Ranking@1/@2/@3/@5, required schema, null padding, K1 compatibility, downstream metrics, and lineage exist in current output. Completion is PARTIAL because the tie-break is not the required one, zero-candidate fixed-width output is unsupported, and Global/Local candidate mismatch is not rejected.

This decision is based on code, schema, manifests, tests, validators, active fault injection, and actual output files, not documentation claims.
""",
    )

    write(
        "MODEL_MODIFICATION_COMPLETION_SUMMARY.md",
        f"""
# M1

STATUS: PARTIAL

Evidence:

- PRE schema and current fast output contain previous-leg fields.
- Stored M1 feature contract includes previous-leg inputs for training and inference.
- Decision-time leakage checks pass.

Missing:

- Matcher must search past an overlapping adjacent record to the latest valid predecessor.
- Add explicit feature-order/hash parity rejection.

# M3

STATUS: PARTIAL

Evidence:

- 26 formal actions are defined and present in M4 candidate-screen output.
- Parameter schema, version lineage, fail-closed typed gates, and stable draws exist.

Missing:

- One authoritative inventory and strict boolean parsing.
- Resolve/explain and validate {len(zero_scored)} zero-scored formal actions.

# Ranking

STATUS: PARTIAL

Evidence:

- K=1/2/3/5 output schemas and downstream comparisons exist and validate for nonempty candidates.
- Padding is null and excluded from metrics in existing output.

Missing:

- Required expected-residual tie-break.
- Fixed-width padding for zero candidates.
- Rejection of Global/Local candidate-set mismatch.
""",
    )

    write(
        "MODEL_CHANGE_TEST_AUDIT.md",
        f"""
# Model Change Test Audit

Audit date: {DATE}

## Existing suite

| Group | Passed | Failed |
|---|---:|---:|
| PRE | 22 | 0 |
| overall_run | 97 | 0 |
| overall_adv | 13 | 0 |
| part_adv | 13 | 0 |
| root profiles | 64 | 0 |
| P1 reconstruction | 18 | 0 |
| Total | 227 | 0 |

## Active fault injection

- PASS: R3 seconds/minutes corruption, action count 25, duplicate A00, padding A00, missing typed gate, future M1 field, action-order seed stability, t1/t2/t3 availability.
- FAIL: unknown PRE override, overlap masking earlier valid predecessor, string boolean parsing, feature-order contract mutation, Global/Local candidate mismatch, expected-residual tie-break, zero-candidate padding.

MODEL_CHANGE_TEST_AUDIT=FAIL because the normal-path suite passes while seven required erroneous states remain uncaught or unsupported.
""",
    )


if __name__ == "__main__":
    main()
