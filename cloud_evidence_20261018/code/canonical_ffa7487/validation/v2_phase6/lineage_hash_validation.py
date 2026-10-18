"""Deterministic Phase 6 lineage and hash validation.

This module does three things without reading or writing the Final-Test
directory:

1. validate the active freeze registry against the baseline and adopted
   evidence;
2. prove that the Train-support correction is metadata-only by reconstructing
   the baseline and corrected payloads; and
3. re-hash the M2 node reference, the M3 Stage-II Q20 support, and the
   ``F_continuity`` CU scale that are recorded separately in the freeze.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.common.identity import content_id

from validation.v2_phase6.common import (
    ACTIVE_PATH,
    BASELINE_COMMIT,
    BASELINE_TREE,
    CU_REGISTRY_V5_PATH,
    DRAFT_PATH,
    F_CONTINUITY_SCALE_PATH,
    M2_TURNAROUND_REFERENCE_PATH,
    PROJECT_ROOT,
    SUPERSESSION_V3_PATH,
    TRAIN_SAMPLES_PATH,
    TRAIN_SUPPORT_PATH,
    VALIDATION_PATH,
    assert_not_final_test,
    file_hash,
    canonical_text_file_hash,
    git_bytes,
    git_json,
    payload_hash,
    read_json,
    relative_path,
    write_json,
)


SCHEMA_VERSION = "V2_PHASE6_LINEAGE_HASH_VALIDATION_V1"
M2_REFERENCE_ID = (
    "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57"
)
M2_ARTIFACT_HASH = (
    "sha256:eff3da4508af5a597516db61e5f8ed45cb84b36c0a06698b43232c5cc76eed41"
)
M2_FILE_SHA256 = (
    "sha256:4a75c326b5ac193eb9b65eefa4741eac8a6ed36d1fde66e542d5cbd8e053803f"
)
F_CONTINUITY_ARTIFACT_HASH = (
    "sha256:4f6851fae1a3f24f3742b5049bdb9465932cb2fcb190cefe396ab773be6c967f"
)
F_CONTINUITY_MEDIAN = 44.0
F_CONTINUITY_POSITIVE_N = 186_742
F_CONTINUITY_POPULATION_ROWS = 2_668_531
SUMMARY_ARTIFACT_HASH = (
    "sha256:769b393f945b3a71dfd20a5b997f7f5c7d0b627d6fe035fad5b49e52121b73d4"
)
SUMMARY_FILE_SHA256 = (
    "sha256:27df8b4ea406b48ca7b494e48759edfeaf490a501ce2b6293638bbd7a2cce4c2"
)
SAMPLES_FILE_SHA256 = (
    "sha256:0dbbcc329f6c94fb02e734fd1414bb727a4341627b9141380f24e642db74b7a5"
)
CU_REGISTRY_FILE_SHA256 = (
    "sha256:25ee9641abf72777d14af0711e7ad46db5de5779170396fb377049458d59b637"
)
SUPERSESSION_FILE_SHA256 = (
    "sha256:6d7a49d14d76484703b312ea8fe851679476bb5f135cd854d9c14dc52b8d80b1"
)
DRAFT_FILE_SHA256 = (
    "sha256:3a302801c5ebbd5f36e4afd81803b30cf3ed178d0fd824699880bb57a719041e"
)
M2_SCOPE = "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY"
M3_SCOPE = "M3_STAGE2_FEASIBILITY_ONLY"
OLD_SCOPE = "STAGE_II_TRAIN_TURNAROUND_LOWER_TAIL_ONLY"


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _read_guarded_json(path: Path, label: str) -> dict[str, Any]:
    resolved = assert_not_final_test(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"{label}:{resolved}")
    return read_json(resolved)


def _leaf_differences(
    old: Any,
    new: Any,
    path: str = "",
) -> Iterable[tuple[str, Any, Any]]:
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        for key in sorted(set(old) | set(new)):
            child = f"{path}.{key}" if path else str(key)
            if key not in old:
                yield child, "<missing>", new[key]
            elif key not in new:
                yield child, old[key], "<missing>"
            else:
                yield from _leaf_differences(old[key], new[key], child)
        return
    if isinstance(old, list) and isinstance(new, list):
        if old != new:
            yield path, old, new
        return
    if old != new:
        yield path, old, new


def _is_allowed_change(path: str) -> bool:
    if path == "artifact_hash":
        return True
    if path == "turnaround_count_authority.artifact_hash":
        return True
    if path.startswith("stage2_turnaround_lower_bound."):
        return True
    if path == "stage2_turnaround_lower_bound":
        return True
    if path in {
        "turnaround_reference.scope",
        "turnaround_reference.statistic_id",
        "turnaround_reference.applicability_scope",
        "turnaround_reference.cells_count",
        "turnaround_reference.distinct_from_stage2_lower_bound",
    }:
        return True
    return False


def _change_class(path: str) -> str:
    if path == "artifact_hash":
        return "SUMMARY_ARTIFACT_HASH"
    if path == "turnaround_count_authority.artifact_hash":
        return "DEPENDENT_REGISTRY_FILE_HASH"
    if path.startswith("stage2_turnaround_lower_bound."):
        return "ADDED_STAGE2_LOWER_BOUND_BLOCK"
    if path == "stage2_turnaround_lower_bound":
        return "ADDED_STAGE2_LOWER_BOUND_BLOCK"
    return "PROVENANCE_SCOPE_METADATA"


def _value_at(payload: Mapping[str, Any], dotted: str) -> Any:
    value: Any = payload
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return "<missing>"
        value = value[part]
    return value


def _array_hash(array: np.ndarray) -> str:
    return _sha256_bytes(np.ascontiguousarray(array).tobytes(order="C"))


def _npz_payload(source: bytes) -> dict[str, Any]:
    with np.load(io.BytesIO(source), allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    return arrays


def _compare_train_arrays() -> dict[str, Any]:
    baseline_bytes = git_bytes(TRAIN_SAMPLES_PATH, commit=BASELINE_COMMIT)
    current_bytes = TRAIN_SAMPLES_PATH.read_bytes()
    baseline_arrays = _npz_payload(baseline_bytes)
    current_arrays = _npz_payload(current_bytes)
    arrays: dict[str, Any] = {}
    failures: list[str] = []
    for name in sorted(set(baseline_arrays) | set(current_arrays)):
        if name not in baseline_arrays or name not in current_arrays:
            failures.append(f"ARRAY_MEMBERSHIP_MISMATCH:{name}")
            continue
        old = baseline_arrays[name]
        new = current_arrays[name]
        shape_equal = old.shape == new.shape
        dtype_equal = old.dtype == new.dtype
        exact_equal = bool(np.array_equal(old, new))
        sorted_equal = bool(np.array_equal(np.sort(old), np.sort(new)))
        membership_equal = bool(
            np.array_equal(np.unique(old), np.unique(new))
        )
        checks = {
            "shape_equal": shape_equal,
            "dtype_equal": dtype_equal,
            "exact_equal": exact_equal,
            "sorted_membership_equal": sorted_equal,
            "unique_membership_equal": membership_equal,
            "baseline_array_sha256": _array_hash(old),
            "current_array_sha256": _array_hash(new),
            "shape": list(old.shape),
            "dtype": str(old.dtype),
        }
        arrays[name] = checks
        if not all(
            (
                shape_equal,
                dtype_equal,
                exact_equal,
                sorted_equal,
                membership_equal,
            )
        ):
            failures.append(f"ARRAY_CONTENT_MISMATCH:{name}")
    return {
        "baseline_file_sha256": _sha256_bytes(baseline_bytes),
        "current_file_sha256": _sha256_bytes(current_bytes),
        "file_bytes_equal": baseline_bytes == current_bytes,
        "arrays": arrays,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def reconstruct_metadata_diff() -> dict[str, Any]:
    """Reconstruct baseline/corrected Train-support payloads and classify diff."""

    baseline = git_json(TRAIN_SUPPORT_PATH, commit=BASELINE_COMMIT)
    corrected = _read_guarded_json(TRAIN_SUPPORT_PATH, "train_support")
    differences = [
        (path, old, new)
        for path, old, new in _leaf_differences(baseline, corrected)
    ]
    allowed = []
    unexpected = []
    for path, old, new in differences:
        item = {
            "path": path,
            "kind": _change_class(path),
            "old": old,
            "new": new,
        }
        if _is_allowed_change(path):
            allowed.append(item)
        else:
            unexpected.append(item)

    preserved_paths = (
        "episode_count",
        "excluded_rotations",
        "rotation_count",
        "train_partition",
        "source_paths",
        "source_hashes",
        "population_gates",
        "quantile_rule",
        "turnaround.nominal_quantile",
        "turnaround.sensitivity_quantiles",
        "turnaround.quantile_minutes",
        "turnaround.median_minutes",
        "factual_headroom",
        "u_max",
        "action_grid",
        "stage1_capacity",
        "stage2_effort",
        "samples_artifact",
        "turnaround_reference_artifact",
        "turnaround_reference_source_hash",
        "turnaround_reference.path",
        "turnaround_reference.artifact_hash",
        "turnaround_reference.reference_id",
        "turnaround_reference.semantic_correction",
        "turnaround_reference.global_value_minutes",
        "turnaround_reference.global_sample_count",
        "turnaround_reference.superseded_uncorrected_reference",
        "turnaround_count_authority.path",
        "turnaround_count_authority.field",
        "turnaround_count_authority.population_rows",
        "turnaround_count_authority.role",
        "status",
        "artifact_scope",
        "schema_version",
        "final_test_access_count",
        "no_final_test_family_branch",
    )
    preserved = {}
    for path in preserved_paths:
        preserved[path] = _value_at(baseline, path) == _value_at(corrected, path)
    arrays = _compare_train_arrays()
    failures = [
        item["path"] for item in unexpected
    ] + list(arrays["failures"])
    return {
        "baseline_payload_artifact_hash": baseline.get("artifact_hash"),
        "corrected_payload_artifact_hash": corrected.get("artifact_hash"),
        "baseline_file_sha256": _sha256_bytes(
            git_bytes(TRAIN_SUPPORT_PATH, commit=BASELINE_COMMIT)
        ),
        "corrected_file_sha256": canonical_text_file_hash(TRAIN_SUPPORT_PATH),
        "allowed_differences": allowed,
        "unexpected_differences": unexpected,
        "preserved_fields": preserved,
        "preserved_all_required_fields": all(preserved.values()),
        "sample_arrays": arrays,
        "numeric_payload_unchanged": not any(
            not preserved[path]
            for path in preserved_paths
            if path not in {"turnaround_count_authority.artifact_hash"}
        ),
        "sample_membership_unchanged": arrays["status"] == "PASS",
        "scientific_statistics_unchanged": all(
            preserved[path]
            for path in (
                "turnaround.quantile_minutes",
                "turnaround.median_minutes",
                "factual_headroom",
                "u_max",
                "action_grid",
                "population_gates",
            )
        ),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def build_validation_report() -> dict[str, Any]:
    failures: list[str] = []
    checks: dict[str, Any] = {}

    def check(name: str, condition: bool, detail: Any = None) -> None:
        checks[name] = {"status": "PASS" if condition else "FAIL", "detail": detail}
        if not condition:
            failures.append(name)

    active = _read_guarded_json(ACTIVE_PATH, "active_freeze_registry")
    draft = _read_guarded_json(DRAFT_PATH, "phase5_draft")
    summary = _read_guarded_json(TRAIN_SUPPORT_PATH, "train_support")
    reference = _read_guarded_json(
        M2_TURNAROUND_REFERENCE_PATH, "m2_turnaround_reference"
    )
    scale = _read_guarded_json(
        F_CONTINUITY_SCALE_PATH, "f_continuity_cu_scale"
    )
    cu_registry = _read_guarded_json(CU_REGISTRY_V5_PATH, "cu_registry")
    supersession = _read_guarded_json(
        SUPERSESSION_V3_PATH, "passenger_reference_supersession"
    )

    check(
        "active_registry_payload_hash",
        active.get("artifact_hash") == payload_hash(active),
        active.get("artifact_hash"),
    )
    check(
        "pre_freeze_baseline_commit",
        active.get("pre_freeze_baseline_commit") == BASELINE_COMMIT,
        active.get("pre_freeze_baseline_commit"),
    )
    check(
        "pre_freeze_baseline_tree",
        active.get("pre_freeze_baseline_tree") == BASELINE_TREE,
        active.get("pre_freeze_baseline_tree"),
    )
    check(
        "freeze_commit_semantics",
        active.get("freeze_commit_semantics")
        == "PRE_FREEZE_SCIENTIFIC_BASELINE_NOT_ACTIVATION_COMMIT",
        active.get("freeze_commit_semantics"),
    )
    check(
        "activation_tag_target_placeholder",
        active.get("activation_tag_target") == "RESOLVED_AFTER_COMMIT",
        active.get("activation_tag_target"),
    )
    check(
        "activation_tag",
        active.get("activation_tag") == "v2-scientific-freeze",
        active.get("activation_tag"),
    )
    check(
        "active_status",
        active.get("status") == "SCIENTIFIC_FREEZE_ACTIVE",
        active.get("status"),
    )
    check(
        "active_not_a_formal_freeze_false",
        active.get("not_a_formal_freeze") is False,
        active.get("not_a_formal_freeze"),
    )
    check(
        "draft_unchanged",
        draft.get("status") == "DRAFT_NOT_ACTIVATED"
        and draft.get("freeze_commit") == "PENDING"
        and canonical_text_file_hash(DRAFT_PATH) == DRAFT_FILE_SHA256,
        {
            "status": draft.get("status"),
            "freeze_commit": draft.get("freeze_commit"),
            "file_sha256": canonical_text_file_hash(DRAFT_PATH),
        },
    )
    check(
        "m2_reference_identity",
        reference.get("reference_id") == M2_REFERENCE_ID
        and reference.get("artifact_hash") == M2_ARTIFACT_HASH
        and canonical_text_file_hash(M2_TURNAROUND_REFERENCE_PATH) == M2_FILE_SHA256,
        {
            "reference_id": reference.get("reference_id"),
            "artifact_hash": reference.get("artifact_hash"),
            "file_sha256": canonical_text_file_hash(M2_TURNAROUND_REFERENCE_PATH),
        },
    )
    check(
        "m2_reference_statistic",
        reference.get("statistic_id") == "MEDIAN"
        and reference.get("applicability_scope") == "AIRPORT_GROUP"
        and float(reference.get("global_value_minutes", float("nan"))) == 57.0,
        {
            "statistic_id": reference.get("statistic_id"),
            "applicability_scope": reference.get("applicability_scope"),
            "global_value_minutes": reference.get("global_value_minutes"),
        },
    )
    check(
        "m3_q20_support",
        summary.get("stage2_turnaround_lower_bound", {}).get("scope")
        == M3_SCOPE
        and float(
            summary.get("stage2_turnaround_lower_bound", {}).get(
                "value_minutes", float("nan")
            )
        )
        == 41.0
        and float(
            summary["stage2_turnaround_lower_bound"]["sensitivity_minutes"]["q10"]
        )
        == 34.0
        and float(
            summary["stage2_turnaround_lower_bound"]["sensitivity_minutes"]["q30"]
        )
        == 47.0,
        summary.get("stage2_turnaround_lower_bound"),
    )
    check(
        "m2_scope_corrected",
        summary.get("turnaround_reference", {}).get("scope") == M2_SCOPE,
        summary.get("turnaround_reference", {}).get("scope"),
    )
    check(
        "non_merge_flags",
        active.get("merge_forbidden") is True
        and active.get("41_is_not_the_m2_node_reference") is True
        and active.get("57_is_not_the_stage2_lower_bound") is True,
        {
            "merge_forbidden": active.get("merge_forbidden"),
            "41_is_not_the_m2_node_reference": active.get(
                "41_is_not_the_m2_node_reference"
            ),
            "57_is_not_the_stage2_lower_bound": active.get(
                "57_is_not_the_stage2_lower_bound"
            ),
        },
    )
    check(
        "f_continuity_scale",
        scale.get("artifact_hash") == F_CONTINUITY_ARTIFACT_HASH
        and float(scale.get("median", float("nan"))) == F_CONTINUITY_MEDIAN
        and int(scale.get("positive_n", -1)) == F_CONTINUITY_POSITIVE_N
        and int(scale.get("population_rows", -1))
        == F_CONTINUITY_POPULATION_ROWS
        and scale.get("scale_rule") == "Median_Train(q_k | q_k > 0)",
        {
            "artifact_hash": scale.get("artifact_hash"),
            "median": scale.get("median"),
            "positive_n": scale.get("positive_n"),
            "population_rows": scale.get("population_rows"),
            "scale_rule": scale.get("scale_rule"),
        },
    )
    check(
        "cu_registry_byte_identity",
        cu_registry.get("registry_id") == "M2_DATA2_FORMAL_CU_V5"
        and cu_registry.get("scientific_status")
        == "HUMAN_APPROVED_PENDING_FREEZE"
        and canonical_text_file_hash(CU_REGISTRY_V5_PATH) == CU_REGISTRY_FILE_SHA256,
        {
            "registry_id": cu_registry.get("registry_id"),
            "scientific_status": cu_registry.get("scientific_status"),
            "file_sha256": canonical_text_file_hash(CU_REGISTRY_V5_PATH),
        },
    )
    check(
        "supersession_byte_identity",
        supersession.get("activation_status") == "DRAFT_NOT_ACTIVATED"
        and canonical_text_file_hash(SUPERSESSION_V3_PATH) == SUPERSESSION_FILE_SHA256,
        {
            "activation_status": supersession.get("activation_status"),
            "file_sha256": canonical_text_file_hash(SUPERSESSION_V3_PATH),
        },
    )
    metadata = reconstruct_metadata_diff()
    check(
        "metadata_only_correction",
        metadata["status"] == "PASS",
        metadata,
    )
    check(
        "train_summary_hash",
        summary.get("artifact_hash") == SUMMARY_ARTIFACT_HASH
        and canonical_text_file_hash(TRAIN_SUPPORT_PATH) == SUMMARY_FILE_SHA256
        and file_hash(TRAIN_SAMPLES_PATH) == SAMPLES_FILE_SHA256,
        {
            "summary_artifact_hash": summary.get("artifact_hash"),
            "summary_file_sha256": canonical_text_file_hash(TRAIN_SUPPORT_PATH),
            "samples_file_sha256": file_hash(TRAIN_SAMPLES_PATH),
        },
    )
    accounting = active.get("final_test_accounting", {})
    check(
        "final_test_accounting",
        active.get("final_test_access_count") == 1
        and active.get("current_freeze_run_increment") == 0
        and active.get("new_final_test_execution") is False
        and active.get("phase_7_entered") is False
        and accounting.get("historical_access_total") == 1
        and accounting.get("current_freeze_run_increment") == 0
        and accounting.get("new_final_test_execution") is False
        and accounting.get("phase_7_entered") is False
        and accounting.get("final_test_path_touched") is False,
        accounting,
    )

    status = "PASS" if not failures else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "validator_id": "V2_PHASE6_LINEAGE_HASH_VALIDATION",
        "status": status,
        "baseline_commit": BASELINE_COMMIT,
        "baseline_tree": BASELINE_TREE,
        "active_registry": {
            "path": str(ACTIVE_PATH),
            "relative_path": relative_path(ACTIVE_PATH),
            "file_sha256": canonical_text_file_hash(ACTIVE_PATH),
            "artifact_hash": active.get("artifact_hash"),
        },
        "checks": checks,
        "metadata_diff": metadata,
        "final_test_accounting": {
            "historical_access_total": 1,
            "current_freeze_run_increment": 0,
            "new_final_test_execution": False,
            "phase_7_entered": False,
            "final_test_path_touched": False,
        },
        "final_test_access_count": 1,
        "current_freeze_run_increment": 0,
        "new_final_test_execution": False,
        "phase_7_entered": False,
        "no_final_test_path_read": True,
        "failures": failures,
    }


def _check_report_matches(report: Mapping[str, Any]) -> bool:
    if not VALIDATION_PATH.is_file():
        return False
    observed = read_json(VALIDATION_PATH)
    return observed == report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write validation report")
    mode.add_argument("--check", action="store_true", help="check validation report")
    args = parser.parse_args(argv)
    report = build_validation_report()
    if args.write:
        write_json(VALIDATION_PATH, report)
    else:
        if not _check_report_matches(report):
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "reason": "PHASE6_VALIDATION_REPORT_MISMATCH_OR_MISSING",
                        "report_path": str(VALIDATION_PATH),
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
                "report_path": str(VALIDATION_PATH),
                "failures": report["failures"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_validation_report",
    "reconstruct_metadata_diff",
]
