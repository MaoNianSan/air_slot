"""Gate-A reporting payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import constants as C
from .authority import (
    validate_instruction_copies,
    validate_phase7_authority,
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


def _relative_repo_path(path: Path) -> str:
    try:
        return str(Path(path).relative_to(C.ROOT))
    except ValueError:
        return str(path)


def _access_boundary_disclosure(
    epoch_paths: C.EpochPaths | None = None,
    historical_paths: C.EpochPaths | None = None,
) -> dict[str, Any]:
    """Return the pre-open access disclosure, including the incidental audit read.

    A repository-level ``rg`` audit necessarily traversed legacy Final-Test
    paths. That incidental read is disclosed explicitly and is not used for
    scientific computation, cohort selection, or a Phase-7 access increment.
    """

    current = epoch_paths or C.stage_matched_epoch_paths()
    historical = historical_paths or C.historical_epoch_paths()
    release_present = current.gate_b_release_path.exists()
    audit_present = current.access_audit_path.exists()
    historical_release_present = (
        historical.gate_b_release_path.exists()
    )
    historical_audit_present = (
        historical.access_audit_path.exists()
    )
    return {
        "q4_raw_reads": 0,
        "repository_level_rg_incidental_audit_reads": 1,
        "legacy_final_test_result_tree_incidental_audit_reads": 1,
        "legacy_final_test_result_tree_scientific_reads": 0,
        "legacy_final_test_result_tree_reads_used_for_scientific_computation": 0,
        "legacy_final_test_result_tree_reads_used_for_selection": 0,
        "phase7_scientific_access_increment": 0,
        "final_test_data_reads": 0,
        "legacy_final_test_writes": 0,
        "allow_final_test_true_occurrences": 0,
        "gate_b_release_present": release_present,
        "current_epoch_root": str(current.root),
        "current_epoch_release_present": release_present,
        "current_epoch_access_audit_present": audit_present,
        "current_epoch_access_count": 1 if audit_present else 0,
        "historical_epoch_root": str(historical.root),
        "historical_epoch_present": historical.root.exists(),
        "historical_epoch_release_present": historical_release_present,
        "historical_epoch_access_audit_present": historical_audit_present,
        "historical_epoch_used_for_scientific_computation": False,
        "historical_epoch_used_for_selection": False,
        "phase7_access_epoch_opened": False,
    }


def build_gate_a_preflight(
    *,
    epoch_paths: C.EpochPaths | None = None,
    historical_paths: C.EpochPaths | None = None,
) -> dict[str, Any]:
    """Build the Gate-A preflight object without writing it."""

    current = epoch_paths or C.stage_matched_epoch_paths()
    historical = historical_paths or C.historical_epoch_paths()
    phase7_authority = validate_phase7_authority()
    r2 = phase7_authority["freeze_r2"]
    cohort = validate_cohort_reference()
    instruction = validate_instruction_copies()
    dry_run = run_dry_run()
    gate_b_release_present = current.gate_b_release_path.exists()
    _require(
        gate_b_release_present is False,
        "GATE_A_GATE_B_RELEASE_ALREADY_PRESENT",
        str(current.gate_b_release_path),
    )
    return {
        "schema_version": "AIR_SLOT_V2_PHASE7_GATE_A_PREFLIGHT_V1",
        "status": "READY_FOR_GATE_B",
        "gate": "PHASE_7_GATE_A",
        "gate_b_authorized": False,
        "gate_a_commit": _gate_a_commit_value(),
        "authority": {
            "freeze_r2": r2,
            "stage2_production_authority": phase7_authority[
                "stage2_production_authority"
            ],
            "instruction": instruction,
            "cohort": cohort,
        },
        "dry_run": dry_run,
        "access_boundary": _access_boundary_disclosure(
            current,
            historical,
        ),
        "final_test_accounting": {
            "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
        "release_schema": {
            "path": _relative_repo_path(current.gate_b_release_path),
            "current_epoch_root": str(current.root),
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


def _blocked_payload(
    code: str,
    detail: Any = None,
    *,
    epoch_paths: C.EpochPaths | None = None,
    historical_paths: C.EpochPaths | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "AIR_SLOT_V2_PHASE7_GATE_A_PREFLIGHT_V1",
        "status": "TYPED_BLOCKER",
        "gate": "PHASE_7_GATE_A",
        "gate_b_authorized": False,
        "blocker": {"code": code, "detail": detail},
        "access_boundary": _access_boundary_disclosure(
            epoch_paths,
            historical_paths,
        ),
        "final_test_accounting": {
            "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
    }


__all__ = [
    "_access_boundary_disclosure",
    "_blocked_payload",
    "_gate_a_commit_value",
    "_relative_repo_path",
    "build_gate_a_preflight",
]
