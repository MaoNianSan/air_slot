"""Activate the AirSlot V2 scientific freeze (Phase 6 only).

The activation registry is intentionally explicit about the difference between
the pre-freeze scientific baseline commit and the later activation commit. The
latter cannot be embedded in the registry before it exists, so the registry
records the placeholder ``RESOLVED_AFTER_COMMIT`` and the annotated tag is the
authority for the complete frozen repository state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.common.identity import content_id
from model.M2.scientific_registry import load_active_v2_cu_registry

from validation.v2_phase6.common import (
    ACTIVATION_TAG,
    ACTIVE_PATH,
    BASELINE_COMMIT,
    BASELINE_TREE,
    CU_REGISTRY_V5_PATH,
    DRAFT_PATH,
    F_CONTINUITY_SCALE_PATH,
    FREEZE_COMMIT_SEMANTICS,
    M2_TURNAROUND_REFERENCE_PATH,
    PROJECT_ROOT,
    REPORT_PATH,
    SUPERSESSION_V3_PATH,
    TRAIN_SAMPLES_PATH,
    TRAIN_SUPPORT_PATH,
    assert_not_final_test,
    file_hash,
    git_json,
    payload_hash,
    read_json,
    relative_path,
    write_json,
)


ACTIVE_SCHEMA_VERSION = "V2_SCIENTIFIC_FREEZE_V1"
ACTIVE_ARTIFACT_KIND = "SCIENTIFIC_FREEZE_SPECIFICATION"
ACTIVE_STATUS = "SCIENTIFIC_FREEZE_ACTIVE"

M2_SCOPE = "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY"
M3_SCOPE = "M3_STAGE2_FEASIBILITY_ONLY"
M2_REFERENCE_ID = (
    "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57"
)
M2_ARTIFACT_HASH = (
    "sha256:eff3da4508af5a597516db61e5f8ed45cb84b36c0a06698b43232c5cc76eed41"
)
M2_MANIFEST_FREEZE_ID = (
    "sha256:bfe4f24e40d554e874faac1d987b0126b393a7dd091068b8fd203aba3e06ae7b"
)
M2_FILE_SHA256 = (
    "sha256:4a75c326b5ac193eb9b65eefa4741eac8a6ed36d1fde66e542d5cbd8e053803f"
)
M3_Q20 = 41.0
M3_Q10 = 34.0
M3_Q30 = 47.0
F_CONTINUITY_ARTIFACT_HASH = (
    "sha256:4f6851fae1a3f24f3742b5049bdb9465932cb2fcb190cefe396ab773be6c967f"
)
F_CONTINUITY_MEDIAN = 44.0
F_CONTINUITY_POSITIVE_N = 186_742
F_CONTINUITY_POPULATION_ROWS = 2_668_531
TRAIN_ROTATION_COUNT = 2_668_531
TRAIN_SUMMARY_ARTIFACT_HASH = (
    "sha256:769b393f945b3a71dfd20a5b997f7f5c7d0b627d6fe035fad5b49e52121b73d4"
)
TRAIN_SUMMARY_FILE_SHA256 = (
    "sha256:35e570a5b9f718d44f9b60d2c0525d53c756529a590865f511a7aef1be5436bc"
)
TRAIN_SAMPLES_FILE_SHA256 = (
    "sha256:0dbbcc329f6c94fb02e734fd1414bb727a4341627b9141380f24e642db74b7a5"
)
DRAFT_FILE_SHA256 = (
    "sha256:416b6da3d733140a1c5d201a40f385f3dd68ad063e17e30bfc134e76e2674740"
)
CU_REGISTRY_FILE_SHA256 = (
    "sha256:03527e107da3635cd1e53c91ea89b0a92e32ed989b37ef15b8d38a68f2d70dc1"
)
SUPERSESSION_FILE_SHA256 = (
    "sha256:6d7a49d14d76484703b312ea8fe851679476bb5f135cd854d9c14dc52b8d80b1"
)
OLD_TRAIN_SCOPE = "STAGE_II_TRAIN_TURNAROUND_LOWER_TAIL_ONLY"


class Phase6ActivationError(RuntimeError):
    """Raised when the freeze activation contract cannot be satisfied."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase6ActivationError(message)


def _read_guarded_json(path: Path, label: str) -> dict[str, Any]:
    resolved = assert_not_final_test(path)
    _require(resolved.is_file(), f"PHASE6_REQUIRED_FILE_MISSING:{label}:{resolved}")
    return read_json(resolved)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _git_blob_sha256(path: Path) -> str | None:
    """Return the SHA-256 of the baseline Git blob when the path is tracked."""

    try:
        result = subprocess.run(
            [
                "git",
                "show",
                f"{BASELINE_COMMIT}:{relative_path(path)}",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return _sha256_bytes(result.stdout)


def _absolute_and_relative(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "relative_path": relative_path(path),
    }


def _assert_payload_hash(payload: Mapping[str, Any], label: str) -> str:
    declared = payload.get("artifact_hash")
    computed = payload_hash(payload)
    _require(
        declared == computed,
        f"PHASE6_ARTIFACT_HASH_MISMATCH:{label}:{declared}:{computed}",
    )
    return str(declared)


def _materialize_reference_blocks(
    *,
    summary: Mapping[str, Any],
    reference: Mapping[str, Any],
    scale: Mapping[str, Any],
) -> dict[str, Any]:
    m2_path = M2_TURNAROUND_REFERENCE_PATH
    scale_path = F_CONTINUITY_SCALE_PATH
    m2_file_hash = file_hash(m2_path)
    scale_file_hash = file_hash(scale_path)

    _require(
        m2_file_hash == M2_FILE_SHA256,
        f"PHASE6_M2_REFERENCE_FILE_HASH_MISMATCH:{m2_file_hash}",
    )
    _require(
        reference.get("reference_id") == M2_REFERENCE_ID,
        "PHASE6_M2_REFERENCE_ID_MISMATCH",
    )
    _require(
        reference.get("artifact_hash") == M2_ARTIFACT_HASH,
        "PHASE6_M2_DECLARED_ARTIFACT_HASH_MISMATCH",
    )
    _require(
        reference.get("manifest_freeze_id") == M2_MANIFEST_FREEZE_ID,
        "PHASE6_M2_MANIFEST_FREEZE_ID_MISMATCH",
    )
    _require(
        reference.get("statistic_id") == "MEDIAN",
        "PHASE6_M2_STATISTIC_MISMATCH",
    )
    _require(
        reference.get("applicability_scope") == "AIRPORT_GROUP",
        "PHASE6_M2_APPLICABILITY_SCOPE_MISMATCH",
    )
    _require(
        float(reference.get("global_value_minutes", float("nan"))) == 57.0,
        "PHASE6_M2_GLOBAL_MEDIAN_MISMATCH",
    )
    _require(
        int(reference.get("global_sample_count", -1)) == 2_668_529,
        "PHASE6_M2_GLOBAL_SAMPLE_COUNT_MISMATCH",
    )
    _require(
        int(reference.get("cells_count", -1)) == 349,
        "PHASE6_M2_CELL_COUNT_MISMATCH",
    )
    _require(
        reference.get("semantic_correction")
        == "BTS_SIGNED_DELAY_SEMANTIC_CORRECTION",
        "PHASE6_M2_SEMANTIC_CORRECTION_MISMATCH",
    )
    _assert_payload_hash(scale, "M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5")
    _require(
        scale.get("artifact_hash") == F_CONTINUITY_ARTIFACT_HASH,
        "PHASE6_F_CONTINUITY_ARTIFACT_HASH_MISMATCH",
    )
    _require(
        float(scale.get("median", float("nan"))) == F_CONTINUITY_MEDIAN,
        "PHASE6_F_CONTINUITY_MEDIAN_MISMATCH",
    )
    _require(
        int(scale.get("positive_n", -1)) == F_CONTINUITY_POSITIVE_N,
        "PHASE6_F_CONTINUITY_POSITIVE_N_MISMATCH",
    )
    _require(
        int(scale.get("population_rows", -1)) == F_CONTINUITY_POPULATION_ROWS,
        "PHASE6_F_CONTINUITY_POPULATION_MISMATCH",
    )

    stage2 = dict(summary["stage2_turnaround_lower_bound"])
    _require(
        summary["turnaround_reference"]["scope"] == M2_SCOPE,
        "PHASE6_SUMMARY_M2_SCOPE_NOT_CORRECTED",
    )
    _require(
        stage2["scope"] == M3_SCOPE,
        "PHASE6_SUMMARY_M3_SCOPE_NOT_SEPARATE",
    )
    _require(
        float(stage2["value_minutes"]) == M3_Q20,
        "PHASE6_SUMMARY_M3_Q20_MISMATCH",
    )
    _require(
        float(stage2["sensitivity_minutes"]["q10"]) == M3_Q10,
        "PHASE6_SUMMARY_M3_Q10_MISMATCH",
    )
    _require(
        float(stage2["sensitivity_minutes"]["q30"]) == M3_Q30,
        "PHASE6_SUMMARY_M3_Q30_MISMATCH",
    )

    m2_block = {
        "object_id": "M2_TYPICAL_TURNAROUND_REFERENCE",
        "role": "M2_NODE_REFERENCE_BUNDLE_INPUT",
        "scope": M2_SCOPE,
        "identity": M2_REFERENCE_ID,
        "reference_id": M2_REFERENCE_ID,
        "declared_artifact_hash": M2_ARTIFACT_HASH,
        "artifact_hash": M2_ARTIFACT_HASH,
        "manifest_freeze_id": M2_MANIFEST_FREEZE_ID,
        "file_sha256": m2_file_hash,
        "repository_blob_sha256": _git_blob_sha256(m2_path),
        "statistic": "MEDIAN",
        "statistic_id": "MEDIAN",
        "applicability_scope": "AIRPORT_GROUP",
        "global_value_minutes": 57.0,
        "fallback": "GLOBAL_FALLBACK",
        "global_sample_count": 2_668_529,
        "cells_count": 349,
        "fit_period": "2019-H1",
        "semantic_correction": "BTS_SIGNED_DELAY_SEMANTIC_CORRECTION",
        "source_lineage": {
            "artifact": _absolute_and_relative(m2_path),
            "active_call_path": [
                "exp.exp2.development_inputs._reference_payloads",
                "model.M2.context.load_data2_reference_bundle",
                "validation.v2_phase5.common.build_node_binding",
                "model.M2.consequence_service.M2ConsequenceService",
                "F_continuity = max(0, R_IB - turnaround_reference)",
            ],
            "active_definition": "max(0, R_IB - turnaround_reference)",
            "superseded_reference_id": (
                "sha256:7c6ac01673f200260fc925eb4c0b57f143fcc34532832375124945252b69707c"
            ),
            "superseded_status": "SUPERSEDED_PROVENANCE_ONLY",
        },
    }

    m3_block = {
        "object_id": "M3_STAGE2_TURNAROUND_LOWER_BOUND_Q20",
        "role": "M3_STAGE2_FEASIBILITY_ONLY",
        "scope": M3_SCOPE,
        "identity": "M3_STAGE2_TURNAROUND_LOWER_BOUND_Q20",
        "definition": "T^{turn,lb} = Q20(T^{turn} | Train)",
        "nominal_quantile": 0.20,
        "value_minutes": M3_Q20,
        "nominal_value_minutes": M3_Q20,
        "sensitivity_quantiles": [0.10, 0.30],
        "sensitivity_minutes": {"q10": M3_Q10, "q30": M3_Q30},
        "quantile_rule": summary["quantile_rule"],
        "population_rows": int(summary["rotation_count"]),
        "source_lineage": {
            "summary_artifact": {
                "path": str(TRAIN_SUPPORT_PATH),
                "relative_path": relative_path(TRAIN_SUPPORT_PATH),
                "artifact_hash": summary["artifact_hash"],
                "file_sha256": file_hash(TRAIN_SUPPORT_PATH),
            },
            "samples_artifact": {
                "path": str(TRAIN_SAMPLES_PATH),
                "relative_path": relative_path(TRAIN_SAMPLES_PATH),
                "file_sha256": file_hash(TRAIN_SAMPLES_PATH),
                "arrays": ["turnaround_minutes", "headroom_nominal_minutes"],
            },
            "active_computation": "M3_STAGE2_FEASIBILITY_ONLY",
        },
    }

    scale_block = {
        "object_id": "F_CONTINUITY_CU_SCALE",
        "role": "M2_CONSEQUENCE_UNIT_NORMALIZATION",
        "scope": "M2_F_CONTINUITY_CU_SCALE",
        "identity": scale.get("schema_version"),
        "component": "F_continuity",
        "declared_artifact_hash": F_CONTINUITY_ARTIFACT_HASH,
        "artifact_hash": F_CONTINUITY_ARTIFACT_HASH,
        "file_sha256": scale_file_hash,
        "repository_blob_sha256": _git_blob_sha256(scale_path),
        "statistic": "MEDIAN_TRAIN_POSITIVE",
        "median": F_CONTINUITY_MEDIAN,
        "positive_n": F_CONTINUITY_POSITIVE_N,
        "population_rows": F_CONTINUITY_POPULATION_ROWS,
        "fit_partition": scale.get("fit_partition"),
        "fit_period": scale.get("fit_period"),
        "fit_months": scale.get("fit_months"),
        "scale_rule": scale.get("scale_rule"),
        "native_unit": scale.get("native_unit"),
        "source_lineage": scale.get("reference_lineage"),
    }
    return {
        "m2_typical_turnaround_reference": m2_block,
        "m2_node_reference_bundle": m2_block,
        "m3_stage2_turnaround_lower_bound": m3_block,
        "m3_turnaround_lower_bound_reference": m3_block,
        "f_continuity_cu_scale": scale_block,
        "f_continuity_scale": scale_block,
        "artifact_identity_contract": {
            "m2_typical_turnaround_reference": {
                "identity": M2_REFERENCE_ID,
                "declared_artifact_hash": M2_ARTIFACT_HASH,
                "file_sha256": m2_file_hash,
                "statistic": "MEDIAN",
                "scope": M2_SCOPE,
            },
            "m3_stage2_turnaround_lower_bound": {
                "identity": "M3_STAGE2_TURNAROUND_LOWER_BOUND_Q20",
                "value_minutes": M3_Q20,
                "statistic": "Q20",
                "scope": M3_SCOPE,
            },
            "f_continuity_cu_scale": {
                "identity": scale.get("schema_version"),
                "declared_artifact_hash": F_CONTINUITY_ARTIFACT_HASH,
                "file_sha256": scale_file_hash,
                "statistic": "MEDIAN_TRAIN_POSITIVE",
                "scope": "M2_F_CONTINUITY_CU_SCALE",
            },
        },
    }


def build_active_registry() -> dict[str, Any]:
    """Build the deterministic Phase 6 activation registry."""

    draft = _read_guarded_json(DRAFT_PATH, "phase5_draft")
    summary = _read_guarded_json(TRAIN_SUPPORT_PATH, "train_support")
    reference = _read_guarded_json(
        M2_TURNAROUND_REFERENCE_PATH, "m2_turnaround_reference"
    )
    scale = _read_guarded_json(
        F_CONTINUITY_SCALE_PATH, "f_continuity_cu_scale"
    )
    cu_registry = _read_guarded_json(CU_REGISTRY_V5_PATH, "cu_registry_v5")
    supersession = _read_guarded_json(
        SUPERSESSION_V3_PATH, "passenger_reference_supersession_v3"
    )
    baseline_summary = git_json(TRAIN_SUPPORT_PATH, commit=BASELINE_COMMIT)

    _require(
        draft.get("status") == "DRAFT_NOT_ACTIVATED",
        "PHASE6_DRAFT_STATUS_CHANGED",
    )
    _require(
        draft.get("freeze_commit") == "PENDING",
        "PHASE6_DRAFT_FREEZE_COMMIT_CHANGED",
    )
    _require(
        file_hash(DRAFT_PATH) == DRAFT_FILE_SHA256,
        "PHASE6_DRAFT_FILE_NO_LONGER_BYTE_IDENTICAL",
    )
    _require(
        baseline_summary.get("turnaround_reference", {}).get("scope")
        == OLD_TRAIN_SCOPE,
        "PHASE6_BASELINE_TRAIN_SCOPE_UNEXPECTED",
    )
    _assert_payload_hash(summary, "TRAIN_TURNAROUND_HEADROOM_SUMMARY")
    _require(
        summary.get("artifact_hash") == TRAIN_SUMMARY_ARTIFACT_HASH,
        "PHASE6_TRAIN_SUMMARY_ARTIFACT_HASH_MISMATCH",
    )
    _require(
        file_hash(TRAIN_SUPPORT_PATH) == TRAIN_SUMMARY_FILE_SHA256,
        "PHASE6_TRAIN_SUMMARY_FILE_HASH_MISMATCH",
    )
    _require(
        file_hash(TRAIN_SAMPLES_PATH) == TRAIN_SAMPLES_FILE_SHA256,
        "PHASE6_TRAIN_SAMPLES_FILE_HASH_MISMATCH",
    )
    _require(
        int(summary.get("rotation_count", -1)) == TRAIN_ROTATION_COUNT,
        "PHASE6_TRAIN_ROTATION_COUNT_MISMATCH",
    )
    _require(
        int(summary.get("episode_count", -1)) == TRAIN_ROTATION_COUNT,
        "PHASE6_TRAIN_EPISODE_COUNT_MISMATCH",
    )
    _require(
        int(summary.get("excluded_rotations", -1)) == 0,
        "PHASE6_TRAIN_EXCLUDED_ROTATIONS_NONZERO",
    )
    _require(
        float(summary["turnaround"]["median_minutes"]) == 57.0,
        "PHASE6_TRAIN_MEDIAN_MISMATCH",
    )

    cu_model = load_active_v2_cu_registry(CU_REGISTRY_V5_PATH)
    _require(
        cu_model.registry_hash == cu_registry.get("registry_hash"),
        "PHASE6_CU_REGISTRY_PAYLOAD_HASH_MISMATCH",
    )
    _require(
        cu_registry.get("registry_id") == "M2_DATA2_FORMAL_CU_V5",
        "PHASE6_CU_REGISTRY_ID_MISMATCH",
    )
    _require(
        cu_registry.get("registry_hash")
        == "sha256:fd3ccfa0c56ba64d840ab163b5a133a5b0d6a662249d89af38c7377f6f24b030",
        "PHASE6_CU_REGISTRY_HASH_MISMATCH",
    )
    _require(
        cu_registry.get("scientific_status") == "HUMAN_APPROVED_PENDING_FREEZE",
        "PHASE6_CU_INTERNAL_STATUS_CHANGED",
    )
    _require(
        file_hash(CU_REGISTRY_V5_PATH) == CU_REGISTRY_FILE_SHA256,
        "PHASE6_CU_REGISTRY_FILE_HASH_MISMATCH",
    )
    _require(
        supersession.get("activation_status") == "DRAFT_NOT_ACTIVATED",
        "PHASE6_SUPERSESSION_INTERNAL_STATUS_CHANGED",
    )
    _require(
        file_hash(SUPERSESSION_V3_PATH) == SUPERSESSION_FILE_SHA256,
        "PHASE6_SUPERSESSION_FILE_HASH_MISMATCH",
    )

    reference_blocks = _materialize_reference_blocks(
        summary=summary, reference=reference, scale=scale
    )
    active = json.loads(json.dumps(draft))
    active.update(
        {
            "schema_version": ACTIVE_SCHEMA_VERSION,
            "artifact_kind": ACTIVE_ARTIFACT_KIND,
            "status": ACTIVE_STATUS,
            "not_a_formal_freeze": False,
            "freeze_commit": BASELINE_COMMIT,
            "freeze_commit_semantics": FREEZE_COMMIT_SEMANTICS,
            "pre_freeze_baseline_commit": BASELINE_COMMIT,
            "pre_freeze_baseline_tree": BASELINE_TREE,
            "complete_frozen_repository_state": "ANNOTATED_TAG_RESOLUTION",
            "activation_tag": ACTIVATION_TAG,
            "activation_tag_target": "RESOLVED_AFTER_COMMIT",
            "activation_owner": "PHASE_6_SCIENTIFIC_FREEZE",
            "phase": "PHASE_6",
            "activation_requirements": [
                "explicit human release of Phase 6",
                "pre-freeze scientific baseline recorded",
                "annotated activation tag created after activation commit",
            ],
            "activation_state": {
                "baseline_commit": BASELINE_COMMIT,
                "baseline_tree": BASELINE_TREE,
                "baseline_semantics": FREEZE_COMMIT_SEMANTICS,
                "complete_state_authority": "ANNOTATED_TAG_RESOLUTION",
                "activation_tag": ACTIVATION_TAG,
                "activation_tag_target": "RESOLVED_AFTER_COMMIT",
                "phase7_entered": False,
                "m1_retrained": False,
                "scientific_outputs_recomputed": False,
                "metadata_correction_only": True,
            },
            "phase6_activation": {
                "phase": "PHASE_6_SCIENTIFIC_FREEZE",
                "status": ACTIVE_STATUS,
                "baseline_commit": BASELINE_COMMIT,
                "baseline_tree": BASELINE_TREE,
                "baseline_semantics": FREEZE_COMMIT_SEMANTICS,
                "complete_frozen_repository_state": "ANNOTATED_TAG_RESOLUTION",
                "activation_tag": ACTIVATION_TAG,
                "activation_tag_target": "RESOLVED_AFTER_COMMIT",
                "final_test_access_total": 1,
                "current_freeze_run_increment": 0,
                "new_final_test_execution": False,
                "phase_7_entered": False,
                "m1_retrained": False,
                "scientific_outputs_recomputed": False,
                "metadata_correction_only": True,
            },
            "phase5_draft": {
                "path": str(DRAFT_PATH),
                "relative_path": relative_path(DRAFT_PATH),
                "file_sha256": file_hash(DRAFT_PATH),
                "artifact_hash": draft.get("artifact_hash"),
                "status": draft.get("status"),
                "freeze_commit": draft.get("freeze_commit"),
                "role": "HISTORICAL_EVIDENCE_BYTE_IDENTICAL",
            },
            "new_final_test_statement": (
                "No new Final-Test run was executed in Phase 6. The historical "
                "Final-Test access total remains 1, and the current freeze-run "
                "increment is 0."
            ),
            "split_definitions": {
                **dict(draft.get("split_definitions") or {}),
                "final_test": {
                    "window": "2019-10-01 onward",
                    "role": "sealed; Phase 7 only",
                    "new_access_requested": False,
                    "historical_access_total": 1,
                    "final_test_access_count_this_round": 0,
                    "current_freeze_run_increment": 0,
                    "new_final_test_execution": False,
                    "phase_7_entered": False,
                },
            },
            "final_test_access_count": 1,
            "historical_final_test_access_total": 1,
            "final_test_run_increment": 0,
            "current_freeze_run_increment": 0,
            "new_final_test_execution": False,
            "phase_7_entered": False,
            "final_test_accounting": {
                "historical_access_total": 1,
                "current_freeze_run_increment": 0,
                "new_final_test_execution": False,
                "phase_7_entered": False,
                "final_test_path_touched": False,
                "final_test_path": "artifacts/experiment/final_test",
                "sealed": True,
            },
            "final_test_path_touched": False,
            "adopted_registries": {
                "m2_data2_formal_cu_v5": {
                    "path": str(CU_REGISTRY_V5_PATH),
                    "relative_path": relative_path(CU_REGISTRY_V5_PATH),
                    "file_sha256": file_hash(CU_REGISTRY_V5_PATH),
                    "repository_blob_sha256": _git_blob_sha256(
                        CU_REGISTRY_V5_PATH
                    ),
                    "registry_id": cu_registry.get("registry_id"),
                    "registry_hash": cu_registry.get("registry_hash"),
                    "declared_internal_status": cu_registry.get(
                        "scientific_status"
                    ),
                    "internal_status_rewritten": False,
                    "adopted_by_top_level_registry": True,
                },
                "passenger_reference_supersession_v3": {
                    "path": str(SUPERSESSION_V3_PATH),
                    "relative_path": relative_path(SUPERSESSION_V3_PATH),
                    "file_sha256": file_hash(SUPERSESSION_V3_PATH),
                    "repository_blob_sha256": _git_blob_sha256(
                        SUPERSESSION_V3_PATH
                    ),
                    "registry_id": supersession.get("registry_id"),
                    "declared_internal_status": supersession.get(
                        "activation_status"
                    ),
                    "internal_status_rewritten": False,
                    "adopted_by_top_level_registry": True,
                },
            },
            "evidence_artifacts": {
                **dict(draft.get("evidence_artifacts") or {}),
                "train_support": {
                    "path": str(TRAIN_SUPPORT_PATH),
                    "relative_path": relative_path(TRAIN_SUPPORT_PATH),
                    "hash": file_hash(TRAIN_SUPPORT_PATH),
                    "file_sha256": file_hash(TRAIN_SUPPORT_PATH),
                    "artifact_hash": summary.get("artifact_hash"),
                    "rotation_count": int(summary["rotation_count"]),
                    "summary_schema_version": summary.get("schema_version"),
                },
                "train_support_samples": {
                    "path": str(TRAIN_SAMPLES_PATH),
                    "relative_path": relative_path(TRAIN_SAMPLES_PATH),
                    "hash": file_hash(TRAIN_SAMPLES_PATH),
                    "file_sha256": file_hash(TRAIN_SAMPLES_PATH),
                    "arrays": summary["samples_artifact"]["arrays"],
                },
            },
            "train_support": {
                **dict(summary),
                "summary_path": str(TRAIN_SUPPORT_PATH),
                "summary_relative_path": relative_path(TRAIN_SUPPORT_PATH),
                "summary_file_sha256": file_hash(TRAIN_SUPPORT_PATH),
                "samples_path": str(TRAIN_SAMPLES_PATH),
                "samples_relative_path": relative_path(TRAIN_SAMPLES_PATH),
                "samples_file_sha256": file_hash(TRAIN_SAMPLES_PATH),
            },
            "metadata_correction": {
                "scope": "TRAIN_SUPPORT_PROVENANCE_ONLY",
                "old_turnaround_reference_scope": OLD_TRAIN_SCOPE,
                "corrected_m2_scope": M2_SCOPE,
                "new_m3_scope": M3_SCOPE,
                "numeric_payload_unchanged": True,
                "sample_membership_unchanged": True,
                "scientific_statistics_unchanged": True,
                "rotation_count_unchanged": True,
                "quantiles_unchanged": True,
                "headroom_unchanged": True,
                "u_max_unchanged": True,
                "action_grid_unchanged": True,
                "allowed_differences": [
                    "provenance_scope_fields",
                    "stage2_turnaround_lower_bound_block",
                    "train_support_summary_artifact_hash",
                    "dependent_registry_file_hash",
                ],
            },
            "non_merge": {
                "merge_forbidden": True,
                "41_is_not_the_m2_node_reference": True,
                "57_is_not_the_stage2_lower_bound": True,
            },
            "merge_forbidden": True,
            "41_is_not_the_m2_node_reference": True,
            "57_is_not_the_stage2_lower_bound": True,
            **reference_blocks,
        }
    )
    active["artifact_hash"] = payload_hash(active)
    _validate_active_registry(active)
    return active


def _validate_active_registry(payload: Mapping[str, Any]) -> None:
    _require(
        payload.get("artifact_hash") == payload_hash(payload),
        "PHASE6_ACTIVE_REGISTRY_ARTIFACT_HASH_MISMATCH",
    )
    _require(
        payload.get("schema_version") == ACTIVE_SCHEMA_VERSION,
        "PHASE6_ACTIVE_SCHEMA_VERSION_MISMATCH",
    )
    _require(
        payload.get("artifact_kind") == ACTIVE_ARTIFACT_KIND,
        "PHASE6_ACTIVE_ARTIFACT_KIND_MISMATCH",
    )
    _require(
        payload.get("status") == ACTIVE_STATUS,
        "PHASE6_ACTIVE_STATUS_MISMATCH",
    )
    _require(
        payload.get("not_a_formal_freeze") is False,
        "PHASE6_ACTIVE_NOT_A_FORMAL_FREEZE",
    )
    _require(
        payload.get("freeze_commit") == BASELINE_COMMIT,
        "PHASE6_ACTIVE_FREEZE_COMMIT_MISMATCH",
    )
    _require(
        payload.get("freeze_commit_semantics") == FREEZE_COMMIT_SEMANTICS,
        "PHASE6_ACTIVE_FREEZE_COMMIT_SEMANTICS_MISMATCH",
    )
    _require(
        payload.get("pre_freeze_baseline_commit") == BASELINE_COMMIT,
        "PHASE6_ACTIVE_BASELINE_COMMIT_MISMATCH",
    )
    _require(
        payload.get("pre_freeze_baseline_tree") == BASELINE_TREE,
        "PHASE6_ACTIVE_BASELINE_TREE_MISMATCH",
    )
    _require(
        payload.get("complete_frozen_repository_state")
        == "ANNOTATED_TAG_RESOLUTION",
        "PHASE6_ACTIVE_COMPLETE_STATE_MISMATCH",
    )
    _require(
        payload.get("activation_tag") == ACTIVATION_TAG,
        "PHASE6_ACTIVE_TAG_NAME_MISMATCH",
    )
    _require(
        payload.get("activation_tag_target") == "RESOLVED_AFTER_COMMIT",
        "PHASE6_ACTIVE_TAG_TARGET_MUST_REMAIN_RESOLVED_AFTER_COMMIT",
    )
    _require(
        payload.get("final_test_access_count") == 1,
        "PHASE6_ACTIVE_HISTORICAL_FINAL_ACCESS_MISMATCH",
    )
    _require(
        payload.get("current_freeze_run_increment") == 0,
        "PHASE6_ACTIVE_CURRENT_FINAL_INCREMENT_MISMATCH",
    )
    _require(
        payload.get("new_final_test_execution") is False,
        "PHASE6_ACTIVE_NEW_FINAL_TEST_FLAG_MISMATCH",
    )
    _require(
        payload.get("phase_7_entered") is False,
        "PHASE6_ACTIVE_PHASE7_FLAG_MISMATCH",
    )
    _require(
        payload.get("final_test_path_touched") is False,
        "PHASE6_ACTIVE_FINAL_TEST_PATH_FLAG_MISMATCH",
    )
    _require(
        payload.get("merge_forbidden") is True,
        "PHASE6_ACTIVE_MERGE_FORBIDDEN_MISSING",
    )
    _require(
        payload.get("41_is_not_the_m2_node_reference") is True,
        "PHASE6_ACTIVE_M2_M3_SEPARATION_MISSING",
    )
    _require(
        payload.get("57_is_not_the_stage2_lower_bound") is True,
        "PHASE6_ACTIVE_M2_M3_REVERSE_SEPARATION_MISSING",
    )
    m2 = payload["m2_typical_turnaround_reference"]
    m3 = payload["m3_stage2_turnaround_lower_bound"]
    scale = payload["f_continuity_cu_scale"]
    _require(m2["scope"] == M2_SCOPE, "PHASE6_ACTIVE_M2_SCOPE_MISMATCH")
    _require(m3["scope"] == M3_SCOPE, "PHASE6_ACTIVE_M3_SCOPE_MISMATCH")
    _require(
        float(m2["global_value_minutes"]) == 57.0,
        "PHASE6_ACTIVE_M2_MEDIAN_MISMATCH",
    )
    _require(
        float(m3["value_minutes"]) == M3_Q20,
        "PHASE6_ACTIVE_M3_Q20_MISMATCH",
    )
    _require(
        scale["declared_artifact_hash"] == F_CONTINUITY_ARTIFACT_HASH,
        "PHASE6_ACTIVE_F_SCALE_HASH_MISMATCH",
    )
    _require(
        float(scale["median"]) == F_CONTINUITY_MEDIAN,
        "PHASE6_ACTIVE_F_SCALE_MEDIAN_MISMATCH",
    )
    _require(
        int(scale["positive_n"]) == F_CONTINUITY_POSITIVE_N,
        "PHASE6_ACTIVE_F_SCALE_POSITIVE_N_MISMATCH",
    )
    _require(
        int(scale["population_rows"]) == F_CONTINUITY_POPULATION_ROWS,
        "PHASE6_ACTIVE_F_SCALE_POPULATION_MISMATCH",
    )
    _require(
        payload["adopted_registries"]["m2_data2_formal_cu_v5"][
            "internal_status_rewritten"
        ]
        is False,
        "PHASE6_ACTIVE_CU_INTERNAL_STATUS_REWRITTEN",
    )
    _require(
        payload["adopted_registries"]["passenger_reference_supersession_v3"][
            "internal_status_rewritten"
        ]
        is False,
        "PHASE6_ACTIVE_SUPERSESSION_INTERNAL_STATUS_REWRITTEN",
    )


def render_freeze_report(payload: Mapping[str, Any]) -> str:
    """Render the Phase 6 freeze report, including the tag resolution note."""

    m2 = payload["m2_typical_turnaround_reference"]
    m3 = payload["m3_stage2_turnaround_lower_bound"]
    scale = payload["f_continuity_cu_scale"]
    lines = [
        "# AirSlot V2 Phase 6 Scientific Freeze Report",
        "",
        "## 1. Activation state",
        "",
        f"- active registry: `{relative_path(ACTIVE_PATH)}`",
        f"- active registry artifact hash: `{payload['artifact_hash']}`",
        f"- status: `{payload['status']}`",
        "- formal freeze: `YES`",
        f"- freeze_commit: `{payload['freeze_commit']}`",
        f"- freeze_commit semantics: `{payload['freeze_commit_semantics']}`",
        f"- pre-freeze scientific baseline commit: `{payload['pre_freeze_baseline_commit']}`",
        f"- pre-freeze scientific baseline tree: `{payload['pre_freeze_baseline_tree']}`",
        "- complete frozen repository state: `ANNOTATED_TAG_RESOLUTION`",
        f"- activation tag: `{payload['activation_tag']}`",
        f"- activation tag target: `{payload['activation_tag_target']}`",
        "",
        "The pre-freeze baseline commit is a scientific/numerical baseline. It",
        "does **not** contain the Phase 6 activation metadata and is not the final",
        "repository snapshot. The complete Phase 6 frozen repository state is the",
        "state resolved by the annotated activation tag after the activation",
        "commit exists. The resolved target is reported in the final Phase 6",
        "handoff and in the post-tag report update.",
        "",
        "## 2. Independent artifact identities",
        "",
        "### M2 typical turnaround reference",
        "",
        f"- identity: `{m2['identity']}`",
        f"- scope: `{m2['scope']}`",
        f"- declared artifact hash: `{m2['declared_artifact_hash']}`",
        f"- manifest freeze id: `{m2['manifest_freeze_id']}`",
        f"- file SHA-256: `{m2['file_sha256']}`",
        f"- statistic: `{m2['statistic']}`",
        f"- applicability: `{m2['applicability_scope']}`, global value "
        f"`{m2['global_value_minutes']}`, global sample count "
        f"`{m2['global_sample_count']}`, cells `{m2['cells_count']}`",
        f"- semantic correction: `{m2['semantic_correction']}`",
        "",
        "### M3 Stage-II turnaround lower-bound reference",
        "",
        f"- identity: `{m3['identity']}`",
        f"- scope: `{m3['scope']}`",
        f"- definition: `{m3['definition']}`",
        f"- nominal Q20: `{m3['value_minutes']}` minutes; Q10/Q30: "
        f"`{m3['sensitivity_minutes']['q10']}` / "
        f"`{m3['sensitivity_minutes']['q30']}` minutes",
        f"- population rows: `{m3['population_rows']}`",
        "",
        "### F_continuity CU scale",
        "",
        f"- identity: `{scale['identity']}`",
        f"- scope: `{scale['scope']}`",
        f"- declared artifact hash: `{scale['declared_artifact_hash']}`",
        f"- file SHA-256: `{scale['file_sha256']}`",
        f"- statistic: `{scale['statistic']}`",
        f"- median: `{scale['median']}`",
        f"- positive n: `{scale['positive_n']}`",
        f"- population rows: `{scale['population_rows']}`",
        f"- fit partition/period: `{scale['fit_partition']}` / `{scale['fit_period']}`",
        "",
        "## 3. Non-merge contract",
        "",
        f"- `merge_forbidden = {payload['merge_forbidden']}`",
        f"- `41_is_not_the_m2_node_reference = "
        f"{payload['41_is_not_the_m2_node_reference']}`",
        f"- `57_is_not_the_stage2_lower_bound = "
        f"{payload['57_is_not_the_stage2_lower_bound']}`",
        "",
        "The M2 reference is the airport-cell median node-reference bundle input",
        "with global fallback 57. The M3 quantity is the scalar Train Q20 lower",
        "bound 41 used only for Stage-II feasibility. They are not merged.",
        "",
        "## 4. Provenance correction",
        "",
        "The corrected Train-support summary changes only provenance/scope",
        "metadata, the added Stage-II lower-bound block, the summary artifact",
        "hash, and the dependent registry file hash. The two sample arrays,",
        "sample membership, rotation and episode counts, quantiles, median 57,",
        "headroom statistics, U_max and action grid are unchanged. The metadata",
        "diff is validated by `validation/v2_phase6/lineage_hash_validation.py`.",
        "",
        "## 5. Final-Test accounting",
        "",
        "- historical Final-Test access total: `1`",
        "- current freeze-run increment: `0`",
        "- new Final-Test execution: `false`",
        "- Phase 7 entered: `false`",
        "- Final-Test path touched: `false`",
        "",
        "No Final-Test artifact was read or written by Phase 6.",
        "",
        "## 6. Validation gates",
        "",
        "- focused pytest: reported in the Phase 6 handoff",
        "- split isolation: reported in the Phase 6 handoff",
        "- enumeration/HiGHS parity: reported in the Phase 6 handoff",
        "- lineage/hash validation: "
        "`artifacts/diagnostics/v2_phase6/FREEZE_LINEAGE_HASH_VALIDATION.json`",
        "",
    ]
    return "\n".join(lines)


def write_activation() -> dict[str, Any]:
    payload = build_active_registry()
    write_json(ACTIVE_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(REPORT_PATH.suffix + ".tmp")
    temporary.write_text(render_freeze_report(payload), encoding="utf-8")
    temporary.replace(REPORT_PATH)
    return payload


def check_activation() -> dict[str, Any]:
    expected = build_active_registry()
    _require(ACTIVE_PATH.is_file(), "PHASE6_ACTIVE_REGISTRY_MISSING")
    observed = read_json(ACTIVE_PATH)
    _require(
        observed == expected,
        "PHASE6_ACTIVE_REGISTRY_DOES_NOT_MATCH_DETERMINISTIC_BUILD",
    )
    _validate_active_registry(observed)
    return {
        "status": "PASS",
        "registry_path": str(ACTIVE_PATH),
        "artifact_hash": observed["artifact_hash"],
        "freeze_commit": observed["freeze_commit"],
        "freeze_commit_semantics": observed["freeze_commit_semantics"],
        "activation_tag": observed["activation_tag"],
        "activation_tag_target": observed["activation_tag_target"],
        "final_test_access_count": observed["final_test_access_count"],
        "current_freeze_run_increment": observed["current_freeze_run_increment"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write activation")
    mode.add_argument("--check", action="store_true", help="check activation")
    args = parser.parse_args(argv)
    try:
        if args.write:
            payload = write_activation()
            result = {
                "status": "PASS",
                "mode": "WRITE",
                "registry_path": str(ACTIVE_PATH),
                "artifact_hash": payload["artifact_hash"],
                "report_path": str(REPORT_PATH),
            }
        else:
            result = {"mode": "CHECK", **check_activation()}
    except Phase6ActivationError as error:
        print(json.dumps({"status": "FAIL", "reason": str(error)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
