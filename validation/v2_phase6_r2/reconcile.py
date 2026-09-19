"""Freeze R2 formal-solver / exact-enumeration reconciliation.

The R2 correction changes only the Stage-II solver authority: the frozen
Pyomo one-hot model solved by HiGHS is the formal decision path, while exact
enumeration over the same finite action grid is the independent oracle. This
module runs the complete non-Test validation corpus and fails closed on any
action disagreement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.M3.solver import (  # noqa: E402
    M3_NUMERICAL_COMPARISON_TOLERANCE,
    solve_stage2_with_highs,
)
from model.M3.stage2 import (  # noqa: E402
    action_grid,
    enumerate_recovery_decision,
)
from model.common.decision_contracts import SolverStatus, TypedStatus  # noqa: E402

from validation.v2_phase6_r2.common import (  # noqa: E402
    PROJECT_ROOT,
    R2Error,
    RECONCILIATION_PATH,
    file_hash,
    payload_hash,
    read_json,
    write_json,
)
from validation.v2_phase6_r2.corpus import (  # noqa: E402
    Stage2CorpusCase,
    TypedCorpusCase,
    actionable_cases,
    corpus_manifest,
    typed_non_actionable_cases,
)


SCHEMA_VERSION = "V2_FREEZE_R2_AUTHORITY_RECONCILIATION_V1"
VALIDATOR_ID = "V2_FREEZE_R2_AUTHORITY_RECONCILIATION"
STATUS_PASS = "PASS"
STATUS_BLOCKED = "R2_TYPED_BLOCKER"
FORMAL_SOLVER = "PYOMO_HIGHS"
PARITY_ORACLE = "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID"
OBJECTIVE_PERTURBATION = "NONE"
TIE_RULE = "u*=min{u in U_i(theta): J_i(u)=min J_i}"
TOLERANCE_NAME = "M3_NUMERICAL_COMPARISON_TOLERANCE"
TOLERANCE = M3_NUMERICAL_COMPARISON_TOLERANCE


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise R2Error(f"{code}:{detail}")


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and float(value) == float(value) and abs(float(value)) != float("inf")


def _case_record(case: Stage2CorpusCase) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    formal = solve_stage2_with_highs(
        case.state_set,
        context=case.context,
        service=case.service,
        headroom_summary=case.headroom_summary,
        policy=case.policy,
    )
    oracle = enumerate_recovery_decision(
        case.state_set,
        context=case.context,
        service=case.service,
        headroom_summary=case.headroom_summary,
        policy=case.policy,
    )

    expected_grid = action_grid(
        case.headroom_summary.u_max,
        floor_to_minutes=case.headroom_summary.floor_to_minutes,
    )
    if formal.action_grid != expected_grid:
        failures.append("FORMAL_ACTION_GRID_MISMATCH")
    if oracle.action_grid != expected_grid:
        failures.append("ORACLE_ACTION_GRID_MISMATCH")
    if formal.u_star not in formal.action_grid:
        failures.append("FORMAL_U_STAR_OUTSIDE_SPECIFICATION_GRID")
    if oracle.u_star not in oracle.action_grid:
        failures.append("ORACLE_U_STAR_OUTSIDE_SPECIFICATION_GRID")
    if formal.solver_status is not SolverStatus.PYOMO_HIGHS:
        failures.append("FORMAL_SOLVER_STATUS_NOT_PYOMO_HIGHS")
    if oracle.solver_status is not SolverStatus.EXACT_ENUMERATION:
        failures.append("ORACLE_SOLVER_STATUS_NOT_EXACT_ENUMERATION")
    if formal.actionable_status is not TypedStatus.SUPPORTED:
        failures.append("FORMAL_ACTIONABLE_STATUS_NOT_SUPPORTED")
    if oracle.actionable_status is not TypedStatus.SUPPORTED:
        failures.append("ORACLE_ACTIONABLE_STATUS_NOT_SUPPORTED")

    if formal.u_star != oracle.u_star:
        failures.append("ACTION_DISAGREEMENT")

    if formal.j_star is None or oracle.j_star is None:
        failures.append("OBJECTIVE_OUTPUT_MISSING")
        objective_error = float("inf")
    else:
        objective_error = abs(float(formal.j_star) - float(oracle.j_star))
        if objective_error > TOLERANCE:
            failures.append("OBJECTIVE_DISAGREEMENT")

    if formal.recoverable_value is None or oracle.recoverable_value is None:
        failures.append("RECOVERABLE_VALUE_OUTPUT_MISSING")
        recoverable_error = float("inf")
    else:
        recoverable_error = abs(
            float(formal.recoverable_value) - float(oracle.recoverable_value)
        )
        if recoverable_error > TOLERANCE:
            failures.append("RECOVERABLE_VALUE_DISAGREEMENT")
        if float(formal.recoverable_value) < -TOLERANCE:
            failures.append("FORMAL_V_NEGATIVE_BEYOND_TOLERANCE")
        if float(oracle.recoverable_value) < -TOLERANCE:
            failures.append("ORACLE_V_NEGATIVE_BEYOND_TOLERANCE")

    if formal.j_zero is None or oracle.j_zero is None:
        failures.append("J_ZERO_OUTPUT_MISSING")
    else:
        if abs(float(formal.j_zero) - float(oracle.j_zero)) > TOLERANCE:
            failures.append("J_ZERO_DISAGREEMENT")
        if formal.j_star is not None and float(formal.j_star) > float(formal.j_zero) + TOLERANCE:
            failures.append("FORMAL_OPTIMUM_EXCEEDS_ZERO_ACTION")
        if oracle.j_star is not None and float(oracle.j_star) > float(oracle.j_zero) + TOLERANCE:
            failures.append("ORACLE_OPTIMUM_EXCEEDS_ZERO_ACTION")

    if not _finite(formal.u_star) or not _finite(oracle.u_star):
        failures.append("NONFINITE_ACTION")
    if formal.tie_break_applied != oracle.tie_break_applied:
        failures.append("TIE_DIAGNOSTIC_DISAGREEMENT")
    if formal.near_tie_candidate_count != oracle.near_tie_candidate_count:
        failures.append("NEAR_TIE_COUNT_DISAGREEMENT")

    record = {
        "case_id": case.case_id,
        "fixture_id": case.fixture_id,
        "stage": case.state_set.stage.value,
        "u_max": float(case.headroom_summary.u_max),
        "lambda_policy": float(case.policy.lambda_policy),
        "specification_action_grid": list(expected_grid),
        "formal": {
            "solver_status": formal.solver_status.value,
            "u_star": float(formal.u_star),
            "j_zero": None if formal.j_zero is None else float(formal.j_zero),
            "j_star": None if formal.j_star is None else float(formal.j_star),
            "recoverable_value": (
                None
                if formal.recoverable_value is None
                else float(formal.recoverable_value)
            ),
            "tie_break_applied": formal.tie_break_applied,
            "near_tie_candidate_count": formal.near_tie_candidate_count,
        },
        "oracle": {
            "solver_status": oracle.solver_status.value,
            "u_star": float(oracle.u_star),
            "j_zero": None if oracle.j_zero is None else float(oracle.j_zero),
            "j_star": None if oracle.j_star is None else float(oracle.j_star),
            "recoverable_value": (
                None
                if oracle.recoverable_value is None
                else float(oracle.recoverable_value)
            ),
            "tie_break_applied": oracle.tie_break_applied,
            "near_tie_candidate_count": oracle.near_tie_candidate_count,
        },
        "errors": {
            "objective_absolute_error": objective_error,
            "recoverable_value_absolute_error": recoverable_error,
        },
        "checks": {
            "u_star_exact_equal": formal.u_star == oracle.u_star,
            "objective_within_tolerance": objective_error <= TOLERANCE,
            "recoverable_value_within_tolerance": (
                recoverable_error <= TOLERANCE
            ),
            "u_star_in_specification_grid": (
                formal.u_star in expected_grid and oracle.u_star in expected_grid
            ),
            "v_nonnegative_within_tolerance": (
                formal.recoverable_value is not None
                and oracle.recoverable_value is not None
                and float(formal.recoverable_value) >= -TOLERANCE
                and float(oracle.recoverable_value) >= -TOLERANCE
            ),
        },
        "failure_codes": failures,
    }
    return record, failures


def _typed_record(case: TypedCorpusCase) -> tuple[dict[str, Any], list[str]]:
    decision = enumerate_recovery_decision(
        case.state_set,
        context=case.context,
        service=case.service,
    )
    failures: list[str] = []
    if decision.actionable_status is not TypedStatus.NOT_ACTIONABLE:
        failures.append("TYPED_STATUS_NOT_NOT_ACTIONABLE")
    if decision.solver_status is not SolverStatus.NOT_RUN:
        failures.append("TYPED_SOLVER_STATUS_NOT_NOT_RUN")
    if decision.action_grid != (0.0,):
        failures.append("TYPED_ACTION_GRID_NOT_SINGLETON_ZERO")
    if decision.u_star != 0.0:
        failures.append("TYPED_U_STAR_NOT_ZERO")
    if decision.recoverable_value is not None:
        failures.append("TYPED_RECOVERABLE_VALUE_MUST_BE_NONE")
    if case.expected_status != TypedStatus.NOT_ACTIONABLE.value:
        failures.append("TYPED_EXPECTED_STATUS_MISMATCH")
    return {
        "case_id": case.case_id,
        "stage": case.state_set.stage.value,
        "expected_status": case.expected_status,
        "actionable_status": decision.actionable_status.value,
        "solver_status": decision.solver_status.value,
        "action_grid": list(decision.action_grid),
        "u_star": float(decision.u_star),
        "recoverable_value": decision.recoverable_value,
        "failure_codes": failures,
    }, failures


def build_reconciliation_report() -> dict[str, Any]:
    """Run the complete non-Test corpus and build a deterministic report."""

    actionable = actionable_cases()
    typed_cases = typed_non_actionable_cases()
    records: list[dict[str, Any]] = []
    typed_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for case in actionable:
        record, case_failures = _case_record(case)
        records.append(record)
        if case_failures:
            failures.append(
                {"case_id": case.case_id, "failure_codes": case_failures}
            )

    for case in typed_cases:
        record, case_failures = _typed_record(case)
        typed_records.append(record)
        if case_failures:
            failures.append(
                {"case_id": case.case_id, "failure_codes": case_failures}
            )

    objective_errors = [
        float(record["errors"]["objective_absolute_error"]) for record in records
    ]
    recoverable_errors = [
        float(record["errors"]["recoverable_value_absolute_error"])
        for record in records
    ]
    tie_cases = sum(
        1 for record in records if bool(record["formal"]["tie_break_applied"])
    )
    near_tie_max = max(
        (
            int(record["formal"]["near_tie_candidate_count"])
            for record in records
            if record["formal"]["near_tie_candidate_count"] is not None
        ),
        default=0,
    )
    action_disagreements = sum(
        1
        for record in records
        if not bool(record["checks"]["u_star_exact_equal"])
    )
    status = STATUS_PASS if not failures else STATUS_BLOCKED
    manifest = corpus_manifest()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "validator_id": VALIDATOR_ID,
        "status": status,
        "authority": {
            "formal_solver": FORMAL_SOLVER,
            "parity_oracle": PARITY_ORACLE,
            "objective_perturbation": OBJECTIVE_PERTURBATION,
            "long_term_deviation": False,
            "tie_rule": TIE_RULE,
            "tie_rule_implementation": (
                "two-stage lexicographic HiGHS solve: primary objective J, "
                "then minimize u subject to J <= J* + tau"
            ),
            "numerical_comparison_tolerance": {
                "name": TOLERANCE_NAME,
                "value": TOLERANCE,
                "scientific_parameter": False,
                "role": "SOLVER_NUMERICAL_COMPARISON_ONLY",
            },
        },
        "scope": "ALL_AVAILABLE_NON_TEST_STAGE2_VALIDATION_CORPUS",
        "corpus": manifest,
        "counts": {
            "actionable_cases": len(records),
            "typed_non_actionable_cases": len(typed_records),
            "total_cases": len(records) + len(typed_records),
            "action_disagreements": action_disagreements,
            "tie_break_cases": tie_cases,
            "near_tie_candidate_count_max": near_tie_max,
        },
        "error_summary": {
            "objective_absolute_error_max": max(objective_errors, default=0.0),
            "objective_absolute_error_tolerance": TOLERANCE,
            "recoverable_value_absolute_error_max": max(
                recoverable_errors, default=0.0
            ),
            "recoverable_value_absolute_error_tolerance": TOLERANCE,
        },
        "records": records,
        "typed_non_actionable_records": typed_records,
        "failures": failures,
        "final_test_accounting": {
            "historical_access_total": 1,
            "phase7_increment": 0,
            "current_total": 1,
            "new_final_test_execution": False,
            "final_test_path_touched": False,
        },
        "source_hashes": {
            "registries/v2_scientific_freeze.json": file_hash(
                PROJECT_ROOT / "registries" / "v2_scientific_freeze.json"
            ),
            "model/M3/solver.py": file_hash(PROJECT_ROOT / "model" / "M3" / "solver.py"),
            "model/M3/stage2.py": file_hash(PROJECT_ROOT / "model" / "M3" / "stage2.py"),
            "validation/v2_phase6_r2/corpus.py": file_hash(
                PROJECT_ROOT / "validation" / "v2_phase6_r2" / "corpus.py"
            ),
        },
        "no_final_test_path_read": True,
        "final_test_access_count": 1,
        "current_freeze_run_increment": 0,
        "new_final_test_execution": False,
        "phase_7_entered": False,
    }
    report["artifact_hash"] = payload_hash(report)
    return report


def _report_matches(path: Path, report: Mapping[str, Any]) -> bool:
    if not path.is_file():
        return False
    observed = read_json(path)
    return observed == report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write reconciliation report")
    mode.add_argument("--check", action="store_true", help="check reconciliation report")
    args = parser.parse_args(argv)

    report = build_reconciliation_report()
    if args.write:
        write_json(RECONCILIATION_PATH, report)
    elif not _report_matches(RECONCILIATION_PATH, report):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "R2_RECONCILIATION_REPORT_MISMATCH_OR_MISSING",
                    "report_path": str(RECONCILIATION_PATH),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": report["status"],
                "mode": "WRITE" if args.write else "CHECK",
                "report_path": str(RECONCILIATION_PATH),
                "failures": report["failures"],
                "counts": report["counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FORMAL_SOLVER",
    "OBJECTIVE_PERTURBATION",
    "PARITY_ORACLE",
    "SCHEMA_VERSION",
    "STATUS_BLOCKED",
    "STATUS_PASS",
    "TIE_RULE",
    "TOLERANCE",
    "TOLERANCE_NAME",
    "build_reconciliation_report",
]
