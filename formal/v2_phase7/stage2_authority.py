"""Active Stage-II solver authority after the immutable Freeze R2 registry.

Freeze R2 remains byte-identical and is treated as historical provenance. This
module validates the separately published post-R2 reconciliation overlay and
binds Gate-B production to exact enumeration. Pyomo+HiGHS is never selected as
a production backend here; the legacy parity helpers remain independent.
"""

from __future__ import annotations

from typing import Any, Mapping

from model.common.decision_contracts import SolverStatus
from model.common.enums import SupportState

from . import constants as C
from .errors import TypedBlocker, _require
from .materialization import _file_sha256, _payload_sha256, _read_json


EXPECTED_ACTIVE_CONTRACT = {
    "stage2_primary_solver": C.STAGE2_PRIMARY_SOLVER,
    "final_test_primary_solver": C.FINAL_TEST_PRIMARY_SOLVER,
    "highs_role": C.HIGHS_ROLE,
    "highs_required_for_production_rows": C.HIGHS_REQUIRED_FOR_PRODUCTION_ROWS,
    "deterministic_tie_break": C.DETERMINISTIC_TIE_BREAK,
    "solver_status_semantics": C.SOLVER_STATUS_SEMANTICS,
    "termination_condition_semantics": "SEPARATE_HIGHS_PARITY_DIAGNOSTIC",
    "parity_backend": C.PARITY_BACKEND,
    "parity_scope": C.PARITY_SCOPE,
}
EXPECTED_SOLVER_STATUS_VALUES = (
    SolverStatus.PYOMO_HIGHS.value,
    SolverStatus.EXACT_ENUMERATION.value,
    SolverStatus.NOT_RUN.value,
)


def _load_authority_overlay() -> dict[str, Any]:
    path = C.STAGE2_AUTHORITY_RECONCILIATION_PATH
    _require(
        path.is_file(),
        "PHASE7_STAGE2_AUTHORITY_OVERLAY_MISSING",
        str(path),
    )
    _require(
        _file_sha256(path) == C.STAGE2_AUTHORITY_RECONCILIATION_FILE_SHA256,
        "PHASE7_STAGE2_AUTHORITY_OVERLAY_FILE_HASH_MISMATCH",
        str(path),
    )
    payload = _read_json(path)
    _require(
        payload.get("artifact_hash")
        == C.STAGE2_AUTHORITY_RECONCILIATION_ARTIFACT_HASH
        == _payload_sha256(payload),
        "PHASE7_STAGE2_AUTHORITY_OVERLAY_PAYLOAD_HASH_MISMATCH",
    )
    return payload


def validate_solver_status_semantics() -> dict[str, Any]:
    """Fail closed if ``solver_status`` is no longer backend provenance."""

    values = tuple(member.value for member in SolverStatus)
    _require(
        values == EXPECTED_SOLVER_STATUS_VALUES,
        "PHASE7_SOLVER_STATUS_MEMBERS_CHANGED",
        values,
    )
    _require(
        not hasattr(SolverStatus, "OPTIMAL"),
        "PHASE7_SOLVER_STATUS_OPTIMAL_OVERLOAD_FORBIDDEN",
    )
    return {
        "status": "PASS",
        "field_role": "STAGE2_SOLUTION_PROVENANCE_BACKEND_IDENTITY",
        "member_values": list(values),
        "termination_condition_is_separate": True,
    }


def validate_stage2_production_authority() -> dict[str, Any]:
    """Validate the post-R2 overlay and the active production contract."""

    overlay = _load_authority_overlay()
    _require(
        overlay.get("status") == "ACTIVE_POST_R2_STAGE2_SOLVER_AUTHORITY",
        "PHASE7_STAGE2_AUTHORITY_OVERLAY_STATUS_INVALID",
        overlay.get("status"),
    )
    _require(
        overlay.get("scientific_definition_change") is False,
        "PHASE7_STAGE2_AUTHORITY_SCIENTIFIC_DEFINITION_CHANGE_FORBIDDEN",
    )
    parent = overlay.get("parent_freeze", {})
    _require(
        parent.get("tag") == C.R2_TAG
        and parent.get("tag_object") == C.R2_TAG_OBJECT
        and parent.get("tag_target_commit") == C.R2_TAG_TARGET_COMMIT
        and parent.get("registry_file_sha256") == C.R2_REGISTRY_FILE_SHA256
        and parent.get("registry_payload_sha256") == C.R2_REGISTRY_ARTIFACT_HASH,
        "PHASE7_STAGE2_AUTHORITY_PARENT_FREEZE_MISMATCH",
        parent,
    )
    active = overlay.get("active_contract", {})
    _require(
        active == EXPECTED_ACTIVE_CONTRACT,
        "PHASE7_STAGE2_AUTHORITY_ACTIVE_CONTRACT_MISMATCH",
        active,
    )
    _require(
        active.get("stage2_primary_solver") == C.STAGE2_PRIMARY_SOLVER
        and active.get("final_test_primary_solver")
        == C.FINAL_TEST_PRIMARY_SOLVER
        and active.get("highs_role") == C.HIGHS_ROLE
        and active.get("highs_required_for_production_rows")
        is C.HIGHS_REQUIRED_FOR_PRODUCTION_ROWS
        and active.get("deterministic_tie_break") == C.DETERMINISTIC_TIE_BREAK,
        "PHASE7_STAGE2_AUTHORITY_CONSTANT_MISMATCH",
    )
    status_contract = validate_solver_status_semantics()
    overlay_status = overlay.get("solver_status_contract", {})
    _require(
        overlay_status.get("field_role")
        == "STAGE2_SOLUTION_PROVENANCE_BACKEND_IDENTITY"
        and tuple(overlay_status.get("member_values", ()))
        == EXPECTED_SOLVER_STATUS_VALUES
        and overlay_status.get("termination_condition_is_separate") is True,
        "PHASE7_SOLVER_STATUS_OVERLAY_CONTRACT_MISMATCH",
        overlay_status,
    )
    return {
        "status": "PASS",
        "overlay_path": str(
            C.STAGE2_AUTHORITY_RECONCILIATION_PATH.relative_to(C.ROOT)
        ),
        "overlay_file_sha256": C.STAGE2_AUTHORITY_RECONCILIATION_FILE_SHA256,
        "overlay_artifact_hash": C.STAGE2_AUTHORITY_RECONCILIATION_ARTIFACT_HASH,
        "historical_registry_labels": dict(
            overlay.get("historical_registry_labels", {})
        ),
        "active_contract": dict(active),
        "solver_status_contract": status_contract,
        "scientific_definition_change": False,
    }


def production_solver_metadata() -> dict[str, Any]:
    """Return the exact authority fields copied into production reports."""

    contract = validate_stage2_production_authority()["active_contract"]
    return {
        "stage2_primary_solver": contract["stage2_primary_solver"],
        "final_test_primary_solver": contract["final_test_primary_solver"],
        "highs_role": contract["highs_role"],
        "highs_required_for_production_rows": contract[
            "highs_required_for_production_rows"
        ],
        "deterministic_tie_break": contract["deterministic_tie_break"],
        "solver_status_semantics": contract["solver_status_semantics"],
        "parity_backend": contract["parity_backend"],
        "parity_scope": contract["parity_scope"],
    }


def require_enumeration_primary(primary_solver: str) -> None:
    """Reject any attempt to make HiGHS the production primary solver."""

    _require(
        primary_solver == C.STAGE2_PRIMARY_SOLVER,
        "PHASE7_STAGE2_PRIMARY_SOLVER_VIOLATION",
        primary_solver,
    )


def solve_production_recovery(
    state_set: Any,
    *,
    context: Any,
    service: Any,
    headroom_summary: Any = None,
    policy: Any = None,
) -> Any:
    """Solve one production row through the frozen enumeration service."""

    contract = production_solver_metadata()
    require_enumeration_primary(contract["stage2_primary_solver"])
    from model.M3.stage2 import enumerate_recovery_decision

    return enumerate_recovery_decision(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom_summary,
        policy=policy,
    )


def has_abstaining_scenario(state_set: Any) -> bool:
    """Return whether any scenario is typed-abstaining."""

    return any(
        scenario.support is SupportState.ABSTAIN
        for scenario in state_set.scenarios
    )


__all__ = [
    "EXPECTED_ACTIVE_CONTRACT",
    "EXPECTED_SOLVER_STATUS_VALUES",
    "has_abstaining_scenario",
    "production_solver_metadata",
    "require_enumeration_primary",
    "solve_production_recovery",
    "validate_solver_status_semantics",
    "validate_stage2_production_authority",
]
