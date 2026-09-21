"""Gate B.0a exact-equivalence validator for the solver-authority correction.

The pre-change safe-fixture DAG is retained under ``tmp/gate_b0a_baseline``.
This validator reruns the same Development-safe fixture and separates two
classes of differences:

* upstream state/consequence materialization must remain exactly equal;
* the approved stage-matched Stage-I patch must change only the declared
  orchestration payloads, while every recovery decision on a node shared by
  the old and new reference cohorts keeps the same ``u*``, ``J_zero``,
  ``J*``, ``V``, action grid and typed state.

Unexpected scientific differences are typed blockers.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from formal.v2_phase7 import constants as C  # noqa: E402
from formal.v2_phase7.errors import TypedBlocker  # noqa: E402
from formal.v2_phase7.executor import stages as S  # noqa: E402
from formal.v2_phase7.executor.runner import (  # noqa: E402
    run_development_safe_dag,
)
from formal.v2_phase7.materialization import _write_json_atomic  # noqa: E402

DEFAULT_BASELINE_ROOT = ROOT / "tmp" / "gate_b0a_baseline"
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase7"
    / "GATE_B0A_EQUIVALENCE_VALIDATION.json"
)
NODE_LIMIT = 48

SCIENTIFIC_DECISION_FIELDS = (
    "u_star",
    "j_zero",
    "j_star",
    "recoverable_value",
    "action_grid",
    "lambda_policy",
    "u_max",
    "tie_break_applied",
    "near_tie_candidate_count",
)


def _load_checkpoint_payload(root: Path, stage: str) -> Any:
    path = root / "dag" / f"{stage}.json"
    if not path.is_file():
        raise TypedBlocker(
            "PHASE7_GATE_B0A_BASELINE_CHECKPOINT_MISSING",
            str(path),
        )
    return json.loads(path.read_text(encoding="utf-8"))["payload"]


def _row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["variant"]), str(row["node_id"])


def _decision_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    decision = row.get("decision")
    if decision is None:
        return {}
    return {name: decision.get(name) for name in SCIENTIFIC_DECISION_FIELDS}


def validate_equivalence(
    *,
    baseline_root: Path,
    current_root: Path | None = None,
    node_limit: int = NODE_LIMIT,
) -> dict[str, Any]:
    """Run the fixture twice-equivalent check and return the evidence report."""

    baseline_root = Path(baseline_root)
    if current_root is None:
        current_root = Path(
            tempfile.mkdtemp(prefix="air_slot_gate_b0a_equivalence_")
        )
    run = run_development_safe_dag(
        output_root=current_root,
        node_limit=node_limit,
        resume=False,
    )

    failures: list[dict[str, Any]] = []
    exact_payload_stages: tuple[str, ...] = ()
    stage_matched_payload_stages = (
        S.ATTENTION_DECISIONS,
        S.REFERENCE_RECOVERY_COHORT,
        S.RECOVERY_DECISIONS,
        S.M4_COMPARISONS,
        S.BOOTSTRAP,
        S.PAPER_VIEWS,
    )
    intentional_orchestration_differences: list[dict[str, Any]] = []
    for stage in stage_matched_payload_stages:
        observed = run.payload(stage)
        expected = _load_checkpoint_payload(baseline_root, stage)
        if observed != expected:
            intentional_orchestration_differences.append(
                {
                    "field": f"{stage}.payload",
                    "reason": "STAGE_MATCHED_ORCHESTRATION_PATCH",
                }
            )

    canonical_observed = run.payload(S.CANONICAL_NODES)
    canonical_expected = _load_checkpoint_payload(
        baseline_root, S.CANONICAL_NODES
    )
    expected_node_ids = [
        str(node["node_id"]) for node in canonical_expected["nodes"]
    ]
    rolling_node_ids = [
        str(value)
        for value in canonical_observed.get("materialized_rolling_node_ids", ())
    ]
    if (
        len(rolling_node_ids) != len(expected_node_ids)
        or set(rolling_node_ids) != set(expected_node_ids)
    ):
        failures.append(
            {
                "field": f"{S.CANONICAL_NODES}.materialized_rolling_node_ids",
                "reason": "ROLLING_NODE_IDENTITY_NOT_PRESERVED",
            }
        )
    if canonical_observed.get("rolling_stage_counts") != canonical_expected.get(
        "stage_counts"
    ):
        failures.append(
            {
                "field": f"{S.CANONICAL_NODES}.rolling_stage_counts",
                "reason": "ROLLING_STAGE_COUNTS_NOT_PRESERVED",
            }
        )
    canonical_ids = [
        str(value)
        for value in canonical_observed.get("canonical_decision_node_ids", ())
    ]
    if len(set(canonical_ids)) != len(canonical_ids):
        failures.append(
            {
                "field": f"{S.CANONICAL_NODES}.canonical_decision_node_ids",
                "reason": "CANONICAL_NODE_ID_NOT_UNIQUE",
            }
        )
    expected_by_id = {
        str(node["node_id"]): node for node in canonical_expected["nodes"]
    }
    observed_by_id = {
        str(node["node_id"]): node for node in canonical_observed["nodes"]
    }
    for node_id in canonical_ids:
        if node_id not in expected_by_id:
            failures.append(
                {
                    "field": f"{S.CANONICAL_NODES}.nodes[{node_id!r}]",
                    "reason": "CANONICAL_NODE_NOT_FROM_ROLLING_BASELINE",
                }
            )
            continue
        if observed_by_id.get(node_id) != expected_by_id[node_id]:
            failures.append(
                {
                    "field": f"{S.CANONICAL_NODES}.nodes[{node_id!r}]",
                    "reason": "CANONICAL_NODE_PAYLOAD_CHANGED",
                }
            )
    if canonical_observed.get("materialization_scope") != canonical_expected.get(
        "materialization_scope"
    ):
        failures.append(
            {
                "field": f"{S.CANONICAL_NODES}.materialization_scope",
                "reason": "SCIENTIFIC_PAYLOAD_NOT_EXACTLY_EQUAL",
            }
        )
    if canonical_observed.get("node_count") != len(canonical_ids):
        failures.append(
            {
                "field": f"{S.CANONICAL_NODES}.node_count",
                "reason": "CANONICAL_NODE_COUNT_MISMATCH",
            }
        )
    intentional_orchestration_differences.append(
        {
            "field": f"{S.CANONICAL_NODES}.rolling_to_canonical_projection",
            "reason": "CANONICAL_STAGE_NODE_RECONCILIATION",
            "rolling_node_count": len(rolling_node_ids),
            "canonical_node_count": len(canonical_ids),
        }
    )

    state_observed = run.payload(S.STATE_VARIANTS)
    state_expected = _load_checkpoint_payload(baseline_root, S.STATE_VARIANTS)
    expected_variants = {
        str(block["variant"]): block for block in state_expected["variants"]
    }
    observed_variants = {
        str(block["variant"]): block for block in state_observed["variants"]
    }
    if list(observed_variants) != list(expected_variants):
        failures.append(
            {
                "field": f"{S.STATE_VARIANTS}.variants",
                "reason": "PRIMARY_VARIANT_ORDER_CHANGED",
            }
        )
    for variant, observed_block in observed_variants.items():
        expected_block = expected_variants.get(variant)
        if expected_block is None:
            failures.append(
                {
                    "field": f"{S.STATE_VARIANTS}.variants[{variant!r}]",
                    "reason": "PRIMARY_VARIANT_NOT_IN_BASELINE",
                }
            )
            continue
        expected_nodes = {
            str(node["node_id"]): node for node in expected_block["nodes"]
        }
        for node in observed_block["nodes"]:
            node_id = str(node["node_id"])
            if node_id not in expected_nodes:
                failures.append(
                    {
                        "field": (
                            f"{S.STATE_VARIANTS}.variants[{variant!r}].nodes["
                            f"{node_id!r}]"
                        ),
                        "reason": "STATE_NODE_NOT_FROM_ROLLING_BASELINE",
                    }
                )
            elif node != expected_nodes[node_id]:
                failures.append(
                    {
                        "field": (
                            f"{S.STATE_VARIANTS}.variants[{variant!r}].nodes["
                            f"{node_id!r}]"
                        ),
                        "reason": "STATE_NODE_PAYLOAD_CHANGED",
                    }
                )
    state_invariant_fields = {
        key: value
        for key, value in state_observed.items()
        if key not in {"node_count", "variants"}
    }
    state_expected_invariant_fields = {
        key: value
        for key, value in state_expected.items()
        if key not in {"node_count", "variants"}
    }
    if state_invariant_fields != state_expected_invariant_fields:
        failures.append(
            {
                "field": f"{S.STATE_VARIANTS}.invariant_fields",
                "reason": "STATE_REPRESENTATION_CONTRACT_CHANGED",
            }
        )

    consequence_observed = run.payload(S.CONSEQUENCE_VARIANTS)
    consequence_expected = _load_checkpoint_payload(
        baseline_root, S.CONSEQUENCE_VARIANTS
    )
    expected_consequence_rows = {
        _row_key(row): row for row in consequence_expected["rows"]
    }
    for row in consequence_observed["rows"]:
        key = _row_key(row)
        if key not in expected_consequence_rows:
            failures.append(
                {
                    "field": f"{S.CONSEQUENCE_VARIANTS}.rows[{key!r}]",
                    "reason": "CONSEQUENCE_NODE_NOT_FROM_ROLLING_BASELINE",
                }
            )
        elif row != expected_consequence_rows[key]:
            failures.append(
                {
                    "field": f"{S.CONSEQUENCE_VARIANTS}.rows[{key!r}]",
                    "reason": "CONSEQUENCE_NODE_PAYLOAD_CHANGED",
                }
            )
    consequence_invariant_fields = {
        key: value
        for key, value in consequence_observed.items()
        if key not in {"row_count", "rows", "included_row_count", "abstaining_row_count"}
    }
    consequence_expected_invariant_fields = {
        key: value
        for key, value in consequence_expected.items()
        if key not in {"row_count", "rows", "included_row_count", "abstaining_row_count"}
    }
    if consequence_invariant_fields != consequence_expected_invariant_fields:
        failures.append(
            {
                "field": f"{S.CONSEQUENCE_VARIANTS}.invariant_fields",
                "reason": "CONSEQUENCE_REPRESENTATION_CONTRACT_CHANGED",
            }
        )


    recovery_observed = run.payload(S.RECOVERY_DECISIONS)
    recovery_expected = _load_checkpoint_payload(
        baseline_root, S.RECOVERY_DECISIONS
    )
    attention_observed = run.payload(S.ATTENTION_DECISIONS)
    attention_rows = attention_observed.get("rows", [])
    actionable_stages = tuple(S.ACTIONABLE_STAGE_I_STAGES)
    if attention_observed.get("row_count") != len(attention_rows):
        failures.append(
            {
                "field": f"{S.ATTENTION_DECISIONS}.row_count",
                "reason": "ROW_COUNT_MISMATCH",
            }
        )
    if any(row.get("stage") not in actionable_stages for row in attention_rows):
        failures.append(
            {
                "field": f"{S.ATTENTION_DECISIONS}.rows",
                "reason": "NON_ACTIONABLE_STAGE_IN_STAGE1_QUEUE",
            }
        )
    if attention_observed.get("selector", {}).get("pooled_stage1_queue") is not False:
        failures.append(
            {
                "field": f"{S.ATTENTION_DECISIONS}.selector.pooled_stage1_queue",
                "reason": "POOLED_STAGE1_QUEUE_NOT_ALLOWED",
            }
        )
    reference_observed = run.payload(S.REFERENCE_RECOVERY_COHORT)
    if list(reference_observed.get("stage1_actionable_stages", [])) != list(
        actionable_stages
    ):
        failures.append(
            {
                "field": f"{S.REFERENCE_RECOVERY_COHORT}.stage1_actionable_stages",
                "reason": "STAGE1_STAGE_SCOPE_MISMATCH",
            }
        )
    shortlist_by_stage = reference_observed.get("shortlist_node_ids_by_stage", {})
    actionable_by_stage = reference_observed.get(
        "stage2_actionable_node_ids_by_stage", {}
    )
    if set(shortlist_by_stage) != set(actionable_stages) or set(
        actionable_by_stage
    ) != set(actionable_stages):
        failures.append(
            {
                "field": f"{S.REFERENCE_RECOVERY_COHORT}.stage_local_fields",
                "reason": "STAGE_LOCAL_KEYS_MISMATCH",
            }
        )
    flattened_shortlist = [
        node_id
        for stage in actionable_stages
        for node_id in shortlist_by_stage.get(stage, [])
    ]
    flattened_r_star = [
        node_id
        for stage in actionable_stages
        for node_id in actionable_by_stage.get(stage, [])
    ]
    if reference_observed.get("shortlist_node_ids") != flattened_shortlist:
        failures.append(
            {
                "field": f"{S.REFERENCE_RECOVERY_COHORT}.shortlist_node_ids",
                "reason": "FLATTENED_SHORTLIST_UNION_MISMATCH",
            }
        )
    if reference_observed.get("stage2_actionable_node_ids") != flattened_r_star:
        failures.append(
            {
                "field": f"{S.REFERENCE_RECOVERY_COHORT}.stage2_actionable_node_ids",
                "reason": "R_STAR_FLATTENED_UNION_MISMATCH",
            }
        )
    if set(flattened_r_star) - set(flattened_shortlist):
        failures.append(
            {
                "field": f"{S.REFERENCE_RECOVERY_COHORT}.stage2_actionable_node_ids",
                "reason": "R_STAR_NOT_SUBSET_OF_STAGE_LOCAL_SHORTLISTS",
            }
        )
    for field in (
        "a00_never_a_recommendation",
        "objective_perturbation",
        "primary_variants",
        "specification",
    ):
        if recovery_observed.get(field) != recovery_expected.get(field):
            intentional_orchestration_differences.append(
                {
                    "field": f"{S.RECOVERY_DECISIONS}.{field}",
                    "reason": "STAGE_MATCHED_ORCHESTRATION_PATCH",
                }
            )

    observed_rows = {_row_key(row): row for row in recovery_observed["rows"]}
    expected_rows = {_row_key(row): row for row in recovery_expected["rows"]}
    if set(observed_rows) != set(expected_rows):
        intentional_orchestration_differences.append(
            {
                "field": f"{S.RECOVERY_DECISIONS}.rows",
                "reason": "STAGE_MATCHED_REFERENCE_COHORT_CHANGED",
                "observed_count": len(observed_rows),
                "expected_count": len(expected_rows),
            }
        )
    for key in sorted(set(observed_rows) & set(expected_rows)):
        observed = observed_rows[key]
        expected = expected_rows[key]
        for field in ("actionable", "typed_state", "reason_codes"):
            if observed.get(field) != expected.get(field):
                failures.append(
                    {
                        "field": f"{S.RECOVERY_DECISIONS}.rows[{key!r}].{field}",
                        "reason": "SCIENTIFIC_PAYLOAD_NOT_EXACTLY_EQUAL",
                    }
                )
        if _decision_projection(observed) != _decision_projection(expected):
            failures.append(
                {
                    "field": f"{S.RECOVERY_DECISIONS}.rows[{key!r}].decision",
                    "reason": "SCIENTIFIC_DECISION_CHANGED",
                    "observed": _decision_projection(observed),
                    "expected": _decision_projection(expected),
                }
            )

    observed_objectives = recovery_observed.get("reference_objectives", {})
    expected_objectives = recovery_expected.get("reference_objectives", {})
    for node_id in sorted(set(observed_objectives) & set(expected_objectives)):
        if observed_objectives[node_id] != expected_objectives[node_id]:
            failures.append(
                {
                    "field": (
                        f"{S.RECOVERY_DECISIONS}.reference_objectives[{node_id!r}]"
                    ),
                    "reason": "SHARED_REFERENCE_OBJECTIVE_CHANGED",
                }
            )

    status = "PASS" if not failures else "FAIL"
    report = {
        "validator_id": "V2_PHASE7_GATE_B0A_SOLVER_AUTHORITY_EQUIVALENCE",
        "status": status,
        "gate": "PHASE_7_GATE_B0A_SOLVER_AUTHORITY_RECONCILIATION",
        "baseline_root": str(baseline_root),
        "current_root": str(current_root),
        "node_limit": node_limit,
        "scientific_exact_equality": not failures
        and not intentional_orchestration_differences,
        "scientific_contract_preserved": not failures,
        "stage_matched_orchestration_patch_applied": True,
        "intentional_orchestration_differences": (
            intentional_orchestration_differences
        ),
        "allowed_provenance_differences": [
            "stage2_primary_solver",
            "final_test_primary_solver",
            "highs_role",
            "highs_required_for_production_rows",
            "deterministic_tie_break",
            "solver_status_semantics",
            "formal_solver_compatibility_label",
            "parity_oracle_compatibility_label",
            "actionable_row_solver_status",
            "production_row_parity",
            "payload_and_file_hashes",
            "access_disclosure",
        ],
        "exact_equal_stages": list(exact_payload_stages),
        "recovery_decision_fields_compared": list(SCIENTIFIC_DECISION_FIELDS),
        "failures": failures,
        "current_stage_payload_hashes": {
            stage: run.record(stage).payload_hash
            for stage in S.SCIENCE_DAG_STAGES
        },
        "historical_final_test_access_total": (
            C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL
        ),
        "phase7_scientific_access_increment": 0,
        "final_test_paths_read": [],
    }
    if failures:
        raise TypedBlocker(
            "PHASE7_GATE_B0A_EQUIVALENCE_VIOLATION",
            failures,
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=DEFAULT_BASELINE_ROOT,
    )
    parser.add_argument("--current-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--node-limit", type=int, default=NODE_LIMIT)
    args = parser.parse_args(argv)

    try:
        report = validate_equivalence(
            baseline_root=args.baseline_root,
            current_root=args.current_root,
            node_limit=args.node_limit,
        )
    except TypedBlocker as error:
        report = {
            "validator_id": (
                "V2_PHASE7_GATE_B0A_SOLVER_AUTHORITY_EQUIVALENCE"
            ),
            "status": "TYPED_BLOCKER",
            "blocker": {"code": error.code, "detail": error.detail},
            "historical_final_test_access_total": (
                C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL
            ),
            "phase7_scientific_access_increment": 0,
        }
        _write_json_atomic(Path(args.output), report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    _write_json_atomic(Path(args.output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_BASELINE_ROOT",
    "DEFAULT_OUTPUT",
    "NODE_LIMIT",
    "validate_equivalence",
]
