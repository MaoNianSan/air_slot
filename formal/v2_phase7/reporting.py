"""Gate-A reporting payloads."""

from __future__ import annotations

from typing import Any

from . import constants as C
from .authority import (
    validate_instruction_copies,
    validate_r2_authority,
)
from .cohort import validate_cohort_reference
from .dry_run import run_dry_run
from .errors import _require
from .materialization import _git


def _gate_a_commit_value() -> str:
    head = _git("rev-parse", "HEAD")
    if head == C.R2_TAG_TARGET_COMMIT:
        return "RESOLVED_AFTER_GATE_A_COMMIT"
    return head


def build_gate_a_preflight() -> dict[str, Any]:
    """Build the Gate-A preflight object without writing it."""

    r2 = validate_r2_authority()
    cohort = validate_cohort_reference()
    instruction = validate_instruction_copies()
    dry_run = run_dry_run()
    gate_b_release_present = C.GATE_B_RELEASE_PATH.exists()
    _require(
        gate_b_release_present is False,
        "GATE_A_GATE_B_RELEASE_ALREADY_PRESENT",
        str(C.GATE_B_RELEASE_PATH),
    )
    return {
        "schema_version": "AIR_SLOT_V2_PHASE7_GATE_A_PREFLIGHT_V1",
        "status": "READY_FOR_GATE_B",
        "gate": "PHASE_7_GATE_A",
        "gate_b_authorized": False,
        "gate_a_commit": _gate_a_commit_value(),
        "authority": {
            "freeze_r2": r2,
            "instruction": instruction,
            "cohort": cohort,
        },
        "dry_run": dry_run,
        "access_boundary": {
            "q4_raw_reads": 0,
            "old_final_test_result_tree_reads": 0,
            "final_test_data_reads": 0,
            "legacy_final_test_writes": 0,
            "allow_final_test_true_occurrences": 0,
            "gate_b_release_present": False,
            "phase7_access_epoch_opened": False,
        },
        "final_test_accounting": {
            "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
        "release_schema": {
            "path": str(C.GATE_B_RELEASE_PATH.relative_to(C.ROOT)),
            "required_fields": list(C.RELEASE_FIELDS),
            "human_release_required": True,
        },
        "nominal_specification": {
            "q": C.NOMINAL_Q,
            "q_grid": list(C.Q_GRID),
            "lambda": C.NOMINAL_LAMBDA,
            "turnaround_q20_minutes": C.NOMINAL_TURNAROUND_Q20,
            "u_max_minutes": C.NOMINAL_U_MAX,
            "history_capacity": 16,
            "m_cs": 0.90,
        },
        "reference_authority": {
            "H_C_STAR": C.REFERENCE_AUTHORITY,
            "R_STAR": C.STAGE2_INFORMATION_COHORT,
            "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
            "alternative_representations_may_define_H_r_for_L_att": True,
            "stage2_information_comparison_uses_fixed_R_star": True,
        },
        "typed_scientific_states": list(C.TYPED_SCIENTIFIC_STATES),
    }


def _blocked_payload(code: str, detail: Any = None) -> dict[str, Any]:
    return {
        "schema_version": "AIR_SLOT_V2_PHASE7_GATE_A_PREFLIGHT_V1",
        "status": "TYPED_BLOCKER",
        "gate": "PHASE_7_GATE_A",
        "gate_b_authorized": False,
        "blocker": {"code": code, "detail": detail},
        "access_boundary": {
            "q4_raw_reads": 0,
            "old_final_test_result_tree_reads": 0,
            "final_test_data_reads": 0,
            "legacy_final_test_writes": 0,
            "allow_final_test_true_occurrences": 0,
            "gate_b_release_present": C.GATE_B_RELEASE_PATH.exists(),
            "phase7_access_epoch_opened": False,
        },
        "final_test_accounting": {
            "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
    }


__all__ = [
    "_blocked_payload",
    "_gate_a_commit_value",
    "build_gate_a_preflight",
]
