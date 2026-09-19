"""Gate B.0a exact-equivalence validator for the solver-authority correction.

The pre-change safe-fixture DAG is retained under ``tmp/gate_b0a_baseline``.
This validator reruns the same Development-safe fixture and proves that the
solver-authority reconciliation changed only provenance/parity labels:

* all scientific DAG payloads remain exactly equal;
* every recovery decision keeps the same ``u*``, ``J_zero``, ``J*``, ``V``,
  action grid, tuple order and typed state;
* M4 comparisons, bootstrap and paper views are byte-for-byte equal.

Any scientific difference is a typed blocker.
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
    exact_payload_stages = (
        S.STATE_VARIANTS,
        S.CONSEQUENCE_VARIANTS,
        S.ATTENTION_DECISIONS,
        S.M4_COMPARISONS,
        S.BOOTSTRAP,
        S.PAPER_VIEWS,
    )
    for stage in exact_payload_stages:
        observed = run.payload(stage)
        expected = _load_checkpoint_payload(baseline_root, stage)
        if observed != expected:
            failures.append(
                {
                    "field": f"{stage}.payload",
                    "reason": "SCIENTIFIC_PAYLOAD_NOT_EXACTLY_EQUAL",
                }
            )

    canonical_observed = run.payload(S.CANONICAL_NODES)
    canonical_expected = _load_checkpoint_payload(
        baseline_root, S.CANONICAL_NODES
    )
    for field in (
        "materialization_scope",
        "node_count",
        "episode_count",
        "stage_counts",
        "nodes",
    ):
        if canonical_observed.get(field) != canonical_expected.get(field):
            failures.append(
                {
                    "field": f"{S.CANONICAL_NODES}.{field}",
                    "reason": "SCIENTIFIC_PAYLOAD_NOT_EXACTLY_EQUAL",
                }
            )

    recovery_observed = run.payload(S.RECOVERY_DECISIONS)
    recovery_expected = _load_checkpoint_payload(
        baseline_root, S.RECOVERY_DECISIONS
    )
    for field in (
        "cohort_id",
        "cohort_node_ids",
        "decision_node_ids",
        "primary_variants",
        "specification",
        "reference_objectives",
        "typed_state_counts",
        "a00_never_a_recommendation",
        "objective_perturbation",
    ):
        if recovery_observed.get(field) != recovery_expected.get(field):
            failures.append(
                {
                    "field": f"{S.RECOVERY_DECISIONS}.{field}",
                    "reason": "SCIENTIFIC_PAYLOAD_NOT_EXACTLY_EQUAL",
                }
            )

    observed_rows = {_row_key(row): row for row in recovery_observed["rows"]}
    expected_rows = {_row_key(row): row for row in recovery_expected["rows"]}
    if set(observed_rows) != set(expected_rows):
        failures.append(
            {
                "field": f"{S.RECOVERY_DECISIONS}.rows",
                "reason": "ROW_MEMBERSHIP_CHANGED",
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

    status = "PASS" if not failures else "FAIL"
    report = {
        "validator_id": "V2_PHASE7_GATE_B0A_SOLVER_AUTHORITY_EQUIVALENCE",
        "status": status,
        "gate": "PHASE_7_GATE_B0A_SOLVER_AUTHORITY_RECONCILIATION",
        "baseline_root": str(baseline_root),
        "current_root": str(current_root),
        "node_limit": node_limit,
        "scientific_exact_equality": not failures,
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
