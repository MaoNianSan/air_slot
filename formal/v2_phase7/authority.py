"""Freeze R2, instruction, and authority validation."""

from __future__ import annotations

from typing import Any

from . import constants as C
from .errors import _require
from .materialization import (
    _file_sha256,
    _git,
    _payload_sha256,
    _read_json,
    _require_canonical_text_hash,
    _require_file_hash,
    _sha256_bytes,
)
from .stage2_authority import validate_stage2_production_authority


def _instruction_sha256() -> str:
    _require(
        C.INSTRUCTION_REPO_PATH.is_file(),
        "PHASE7_INSTRUCTION_REPO_COPY_MISSING",
        str(C.INSTRUCTION_REPO_PATH),
    )
    return _file_sha256(C.INSTRUCTION_REPO_PATH)


def validate_instruction_copies() -> dict[str, Any]:
    """Require byte-identical repository and Download_all instruction copies."""

    _require(
        C.INSTRUCTION_REPO_PATH.is_file(),
        "PHASE7_INSTRUCTION_REPO_COPY_MISSING",
        str(C.INSTRUCTION_REPO_PATH),
    )
    _require(
        C.INSTRUCTION_DOWNLOAD_PATH.is_file(),
        "PHASE7_INSTRUCTION_DOWNLOAD_COPY_MISSING",
        str(C.INSTRUCTION_DOWNLOAD_PATH),
    )
    repo_bytes = C.INSTRUCTION_REPO_PATH.read_bytes()
    download_bytes = C.INSTRUCTION_DOWNLOAD_PATH.read_bytes()
    _require(
        repo_bytes == download_bytes,
        "PHASE7_INSTRUCTION_COPIES_NOT_IDENTICAL",
    )
    return {
        "status": "PASS",
        "repo_path": str(C.INSTRUCTION_REPO_PATH),
        "download_path": str(C.INSTRUCTION_DOWNLOAD_PATH),
        "sha256": _sha256_bytes(repo_bytes),
        "byte_identical": True,
    }


def validate_r2_authority() -> dict[str, Any]:
    """Validate the immutable Freeze R2 tag, registry and artifact identities."""

    tag_object = _git("rev-parse", f"{C.R2_TAG}^{{tag}}")
    tag_target = _git("rev-parse", f"{C.R2_TAG}^{{commit}}")
    _require(
        tag_object == C.R2_TAG_OBJECT,
        "R2_TAG_OBJECT_MISMATCH",
        tag_object,
    )
    _require(
        tag_target == C.R2_TAG_TARGET_COMMIT,
        "R2_TAG_TARGET_MISMATCH",
        tag_target,
    )

    _require_file_hash(
        C.R2_REGISTRY_PATH,
        C.R2_REGISTRY_FILE_SHA256,
        "R2_REGISTRY_FILE_HASH",
    )
    registry = _read_json(C.R2_REGISTRY_PATH)
    _require(
        registry.get("status") == "SCIENTIFIC_FREEZE_R2_ACTIVE",
        "R2_REGISTRY_STATUS_INVALID",
        registry.get("status"),
    )
    _require(
        registry.get("artifact_hash") == C.R2_REGISTRY_ARTIFACT_HASH,
        "R2_REGISTRY_ARTIFACT_HASH_MISMATCH",
        registry.get("artifact_hash"),
    )
    _require(
        _payload_sha256(registry) == C.R2_REGISTRY_ARTIFACT_HASH,
        "R2_REGISTRY_PAYLOAD_HASH_MISMATCH",
    )
    _require(
        registry.get("formal_solver") == "PYOMO_HIGHS",
        "R2_FORMAL_SOLVER_MISMATCH",
        registry.get("formal_solver"),
    )
    _require(
        registry.get("parity_oracle")
        == "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
        "R2_PARITY_ORACLE_MISMATCH",
        registry.get("parity_oracle"),
    )
    _require(
        registry.get("objective_perturbation") == "NONE",
        "R2_OBJECTIVE_PERTURBATION_MISMATCH",
        registry.get("objective_perturbation"),
    )
    _require(
        registry.get("long_term_deviation") is False,
        "R2_LONG_TERM_DEVIATION_INVALID",
    )
    stage2 = registry.get("stage2_solver", {})
    _require(
        stage2.get("formal_path") == "PYOMO_HIGHS"
        and stage2.get("formal_solver") == "PYOMO_HIGHS",
        "R2_STAGE2_FORMAL_AUTHORITY_MISMATCH",
        stage2,
    )
    _require(
        stage2.get("parity_oracle")
        == "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
        "R2_STAGE2_PARITY_ORACLE_MISMATCH",
        stage2,
    )
    tolerance = stage2.get("numerical_comparison_tolerance", {})
    _require(
        tolerance.get("name") == "M3_NUMERICAL_COMPARISON_TOLERANCE"
        and float(tolerance.get("value")) == C.M3_NUMERICAL_COMPARISON_TOLERANCE
        and tolerance.get("scientific_parameter") is False,
        "R2_NUMERICAL_TOLERANCE_CONTRACT_INVALID",
        tolerance,
    )

    _require_file_hash(
        C.PARENT_REGISTRY_PATH,
        C.PARENT_REGISTRY_FILE_SHA256,
        "PARENT_REGISTRY_FILE_HASH",
    )
    parent = registry.get("parent_freeze", {})
    _require(
        registry.get("activation_state", {}).get("parent_tag_object")
        == C.PARENT_TAG_OBJECT,
        "R2_PARENT_TAG_OBJECT_MISMATCH",
    )
    _require(
        registry.get("activation_state", {}).get("parent_tag_target_commit")
        == C.PARENT_TAG_TARGET_COMMIT,
        "R2_PARENT_TAG_TARGET_MISMATCH",
    )
    _require(
        parent.get("registry_file_sha256") == C.PARENT_REGISTRY_FILE_SHA256,
        "R2_PARENT_REGISTRY_DECLARED_HASH_MISMATCH",
    )
    parent_blob_oid = _git(
        "hash-object",
        C.PARENT_REGISTRY_PATH.relative_to(C.ROOT).as_posix(),
    )
    _require(
        parent.get("registry_blob_sha256") == C.PARENT_REGISTRY_BLOB_OID_FIELD,
        "R2_PARENT_REGISTRY_BLOB_FIELD_MISMATCH",
        parent.get("registry_blob_sha256"),
    )
    _require(
        parent_blob_oid == C.PARENT_REGISTRY_BLOB_OID_FIELD.removeprefix("sha256:"),
        "R2_PARENT_REGISTRY_BLOB_OID_MISMATCH",
        parent_blob_oid,
    )
    parent_actual_sha256 = _file_sha256(C.PARENT_REGISTRY_PATH)
    _require(
        parent_actual_sha256 != C.PARENT_REGISTRY_BLOB_OID_FIELD,
        "R2_PARENT_REGISTRY_BLOB_LABEL_UNEXPECTEDLY_SHA256",
    )

    _require_file_hash(
        C.R2_RECONCILIATION_PATH,
        registry.get("r2_authority_reconciliation", {})
        .get("artifact", {})
        .get("file_sha256", ""),
        "R2_RECONCILIATION_FILE_HASH",
    )
    reconciliation = _read_json(C.R2_RECONCILIATION_PATH)
    _require(
        reconciliation.get("status") == "PASS",
        "R2_RECONCILIATION_STATUS_NOT_PASS",
        reconciliation.get("status"),
    )
    counts = reconciliation.get("counts", {})
    _require(
        int(counts.get("actionable_cases", -1)) == 720
        and int(counts.get("typed_non_actionable_cases", -1)) == 2
        and int(counts.get("action_disagreements", -1)) == 0,
        "R2_RECONCILIATION_COUNTS_INVALID",
        counts,
    )
    _require(
        float(
            reconciliation.get("error_summary", {}).get(
                "objective_absolute_error_max", float("inf")
            )
        )
        <= C.M3_NUMERICAL_COMPARISON_TOLERANCE
        and float(
            reconciliation.get("error_summary", {}).get(
                "recoverable_value_absolute_error_max", float("inf")
            )
        )
        <= C.M3_NUMERICAL_COMPARISON_TOLERANCE,
        "R2_RECONCILIATION_ERROR_BOUND_INVALID",
        reconciliation.get("error_summary"),
    )

    _require_file_hash(
        C.M2_V5_REGISTRY_PATH,
        C.M2_V5_REGISTRY_FILE_SHA256,
        "M2_V5_REGISTRY_FILE_HASH",
    )
    _require_file_hash(
        C.PASSENGER_SUPERSESSION_V3_PATH,
        C.PASSENGER_SUPERSESSION_V3_FILE_SHA256,
        "PASSENGER_SUPERSESSION_V3_FILE_HASH",
    )
    _require_file_hash(
        C.M2_REFERENCE_PATH,
        C.M2_REFERENCE_FILE_SHA256,
        "M2_REFERENCE_FILE_HASH",
    )
    f_continuity_hash = _require_canonical_text_hash(
        C.F_CONTINUITY_SCALE_PATH,
        C.F_CONTINUITY_SCALE_FILE_SHA256,
        C.F_CONTINUITY_SCALE_DECLARED_WORKTREE_SHA256,
        "F_CONTINUITY_SCALE_FILE_HASH",
    )
    train_support_hash = _require_canonical_text_hash(
        C.TRAIN_SUPPORT_SUMMARY_PATH,
        C.TRAIN_SUPPORT_SUMMARY_FILE_SHA256,
        C.TRAIN_SUPPORT_SUMMARY_DECLARED_WORKTREE_SHA256,
        "TRAIN_SUPPORT_SUMMARY_FILE_HASH",
    )
    _require_file_hash(
        C.TRAIN_SUPPORT_SAMPLES_PATH,
        C.TRAIN_SUPPORT_SAMPLES_FILE_SHA256,
        "TRAIN_SUPPORT_SAMPLES_FILE_HASH",
    )

    identity = registry.get("artifact_identity_contract", {})
    _require(
        identity.get("m2_typical_turnaround_reference", {}).get("identity")
        == "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57",
        "R2_M2_TURNAROUND_IDENTITY_MISMATCH",
    )
    _require(
        identity.get("m3_stage2_turnaround_lower_bound", {}).get(
            "value_minutes"
        )
        == C.NOMINAL_TURNAROUND_Q20,
        "R2_M3_Q20_IDENTITY_MISMATCH",
    )
    _require(
        identity.get("f_continuity_cu_scale", {}).get("declared_artifact_hash")
        == "sha256:4f6851fae1a3f24f3742b5049bdb9465932cb2fcb190cefe396ab773be6c967f",
        "R2_F_CONTINUITY_IDENTITY_MISMATCH",
    )
    _require(
        registry.get("41_is_not_the_m2_node_reference") is True
        and registry.get("57_is_not_the_stage2_lower_bound") is True,
        "R2_REFERENCE_NON_MERGE_CONTRACT_MISSING",
    )
    _require(
        registry.get("r2_final_test_accounting", {}).get(
            "historical_access_total"
        )
        == C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL
        and registry.get("r2_final_test_accounting", {}).get(
            "current_freeze_run_increment"
        )
        == 0
        and registry.get("r2_final_test_accounting", {}).get(
            "phase_7_entered"
        )
        is False,
        "R2_FINAL_TEST_ACCOUNTING_INVALID",
        registry.get("r2_final_test_accounting"),
    )

    historical_rulings = {
        item.get("id"): item
        for item in registry.get("rulings_this_round", ())
        if isinstance(item, dict)
    }
    r3_text = str(historical_rulings.get("R3", {}).get("ruling", ""))
    stale_historical_ruling = (
        "exact enumeration" in r3_text.lower()
        and "parity" in r3_text.lower()
        and "formal path" in r3_text.lower()
    )
    _require(
        stale_historical_ruling,
        "R2_EXPECTED_HISTORICAL_RULING_TEXT_NOT_FOUND",
        r3_text,
    )

    return {
        "status": "PASS",
        "tag": C.R2_TAG,
        "tag_object": tag_object,
        "tag_target_commit": tag_target,
        "registry_file_sha256": C.R2_REGISTRY_FILE_SHA256,
        "registry_artifact_hash": C.R2_REGISTRY_ARTIFACT_HASH,
        "formal_solver": "PYOMO_HIGHS",
        "parity_oracle": "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
        "objective_perturbation": "NONE",
        "long_term_deviation": False,
        "numerical_tolerance": {
            "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
            "value": C.M3_NUMERICAL_COMPARISON_TOLERANCE,
            "scientific_parameter": False,
        },
        "parent_registry": {
            "tag": C.PARENT_TAG,
            "tag_object": C.PARENT_TAG_OBJECT,
            "tag_target_commit": C.PARENT_TAG_TARGET_COMMIT,
            "registry_file_sha256": C.PARENT_REGISTRY_FILE_SHA256,
            "registry_blob_oid": parent_blob_oid,
            "registry_blob_oid_field": C.PARENT_REGISTRY_BLOB_OID_FIELD,
            "blob_field_semantics": "GIT_BLOB_OID_WITH_SHA256_PREFIX_COMPATIBILITY_LABEL",
            "actual_file_sha256": parent_actual_sha256,
        },
        "historical_ruling_r3": {
            "text": r3_text,
            "status": "SUPERSEDED_BY_TOP_LEVEL_R2_AUTHORITY",
            "authoritative_top_level_formal_solver": "PYOMO_HIGHS",
        },
        "reconciliation": {
            "path": str(C.R2_RECONCILIATION_PATH.relative_to(C.ROOT)),
            "counts": counts,
            "error_summary": reconciliation.get("error_summary"),
        },
        "artifact_identities": {
            "m2_typical_turnaround_reference": {
                "identity": "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57",
                "file_sha256": C.M2_REFERENCE_FILE_SHA256,
                "statistic": "MEDIAN",
                "scope": "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY",
                "global_fallback_minutes": 57.0,
            },
            "m3_stage2_turnaround_lower_bound": {
                "identity": "M3_STAGE2_TURNAROUND_LOWER_BOUND_Q20",
                "value_minutes": C.NOMINAL_TURNAROUND_Q20,
                "scope": "M3_STAGE2_FEASIBILITY_ONLY",
            },
            "f_continuity_cu_scale": {
                "identity": "M2_V5_F_CONTINUITY_SCALE_CORRECTION_V1",
                "file_sha256": C.F_CONTINUITY_SCALE_FILE_SHA256,
                "median_minutes": 44.0,
                "positive_n": 186742,
                "population_rows": 2668531,
                "scope": "M2_F_CONTINUITY_CU_SCALE",
            },
        },
        "text_artifact_hash_compatibility": {
            "f_continuity_cu_scale": f_continuity_hash,
            "train_support_summary": train_support_hash,
        },
        "merge_forbidden": True,
        "41_is_not_the_m2_node_reference": True,
        "57_is_not_the_stage2_lower_bound": True,
        "final_test_accounting": {
            "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
    }


__all__ = [
    "_instruction_sha256",
    "validate_instruction_copies",
    "validate_r2_authority",
    "validate_phase7_authority",
]


def validate_phase7_authority() -> dict[str, Any]:
    """Return immutable Freeze-R2 authority plus the active post-R2 overlay.

    The historical R2 validator is intentionally left byte-for-byte and
    semantics-for-semantics unchanged. The active Stage-II solver authority
    is the separately published post-R2 reconciliation overlay, so callers
    must consume both blocks instead of treating the historical HiGHS labels
    in R2 as the current production contract.
    """

    return {
        "freeze_r2": validate_r2_authority(),
        "stage2_production_authority": validate_stage2_production_authority(),
    }
