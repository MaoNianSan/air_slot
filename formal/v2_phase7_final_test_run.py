"""AirSlot V2 Phase-7 one-shot Final-Test runner.

This module separates the two Phase-7 gates:

* Gate A validates the active Freeze R2 authority, the frozen cohort
  identity, the R2 instruction copies, solver behavior, typed-state
  preservation, the release schema, and access-epoch idempotence.  It never
  reads Q4 raw data and never reads or writes the legacy
  ``artifacts/experiment/final_test`` tree.
* Gate B is deliberately release-gated.  The module contains the release
  validation and one-epoch access-ledger machinery, but it does not bind a
  scientific executor in Gate A.  A future Gate B invocation must provide an
  explicit executor after a human release exists.

The formal Stage-II authority is Pyomo + HiGHS.  Exact enumeration over the
same finite action grid is only an independent parity oracle.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.common.decision_contracts import (  # noqa: E402
    AttentionDecision,
    DecisionEvaluation,
    EvaluationFamily,
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import OperationalStage, SupportState  # noqa: E402
from model.common.identity import content_id  # noqa: E402


R2_TAG = "v2-scientific-freeze-r2"
R2_TAG_OBJECT = "2dcca6c159dedde3803e63cb48bd8bfefff574cf"
R2_TAG_TARGET_COMMIT = "3834eed33d4a2ea4bdba111fc29cca3529525a3a"
R2_REGISTRY_PATH = ROOT / "registries" / "v2_scientific_freeze_r2.json"
R2_REGISTRY_FILE_SHA256 = (
    "sha256:15c1e8bf5ec5fbb5ee783595a124b1255b550d7d7bc96e34b2cd3df0a4e88e6f"
)
R2_REGISTRY_ARTIFACT_HASH = (
    "sha256:4e7d3bb454e83779e6cbb592d4cf9d6ffddc0edf3435a7bc3d2822e4523417f2"
)
R2_RECONCILIATION_PATH = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase6_r2"
    / "R2_AUTHORITY_RECONCILIATION.json"
)

PARENT_TAG = "v2-scientific-freeze"
PARENT_TAG_OBJECT = "35d5fe1896dd9e17be92bec601f87ec33adb4d56"
PARENT_TAG_TARGET_COMMIT = "d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1"
PARENT_REGISTRY_PATH = ROOT / "registries" / "v2_scientific_freeze.json"
PARENT_REGISTRY_FILE_SHA256 = (
    "sha256:2b89976da5158f0fee87222daef33a8b3b617d61ece94ade00a001869134afdd"
)
PARENT_REGISTRY_BLOB_OID_FIELD = (
    "sha256:a8c43beffbdefaf2ca9c573ec7730ae9a2f55ce3"
)

M2_V5_REGISTRY_PATH = ROOT / "registries" / "m2_data2_formal_cu_v5.json"
M2_V5_REGISTRY_FILE_SHA256 = (
    "sha256:25ee9641abf72777d14af0711e7ad46db5de5779170396fb377049458d59b637"
)
PASSENGER_SUPERSESSION_V3_PATH = (
    ROOT / "registries" / "passenger_reference_supersession_v3.json"
)
PASSENGER_SUPERSESSION_V3_FILE_SHA256 = (
    "sha256:6d7a49d14d76484703b312ea8fe851679476bb5f135cd854d9c14dc52b8d80b1"
)
M2_REFERENCE_PATH = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_v2_data_gate_a2"
    / "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
)
M2_REFERENCE_FILE_SHA256 = (
    "sha256:4a75c326b5ac193eb9b65eefa4741eac8a6ed36d1fde66e542d5cbd8e053803f"
)
F_CONTINUITY_SCALE_PATH = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_freeze_precheck"
    / "M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json"
)
F_CONTINUITY_SCALE_FILE_SHA256 = (
    "sha256:b335b19564c1eaf827ed0d343405dc9e9871fd0284e546be28ab987884e507c0"
)
F_CONTINUITY_SCALE_DECLARED_WORKTREE_SHA256 = (
    "sha256:688560356d5c7fa292b59e5a7b45cf249619c35bf6620446b1166034a5a2e061"
)
TRAIN_SUPPORT_SUMMARY_PATH = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase5_development"
    / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"
)
TRAIN_SUPPORT_SUMMARY_FILE_SHA256 = (
    "sha256:27df8b4ea406b48ca7b494e48759edfeaf490a501ce2b6293638bbd7a2cce4c2"
)
TRAIN_SUPPORT_SUMMARY_DECLARED_WORKTREE_SHA256 = (
    "sha256:35e570a5b9f718d44f9b60d2c0525d53c756529a590865f511a7aef1be5436bc"
)
TRAIN_SUPPORT_SAMPLES_PATH = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase5_development"
    / "TRAIN_TURNAROUND_HEADROOM_SAMPLES.npz"
)
TRAIN_SUPPORT_SAMPLES_FILE_SHA256 = (
    "sha256:0dbbcc329f6c94fb02e734fd1414bb727a4341627b9141380f24e642db74b7a5"
)

COHORT_AUTHORITY_PATH = ROOT / "formal" / "FINAL_TEST_COHORT_AUTHORITY_V1.json"
COHORT_AUTHORITY_FILE_SHA256 = (
    "sha256:9832b198e221042bff6f40c718f07c82169885514030308b7d50d6172d7e0088"
)
COHORT_MANIFEST_PATH = ROOT / "formal" / "FINAL_TEST_COHORT_MANIFEST_V1.json"
COHORT_MANIFEST_FILE_SHA256 = (
    "sha256:5024f6b0af07d7a71b3d341921925617cfe40b0b1131322c319972521cb19073"
)
EXECUTED_COHORT_MANIFEST_SHA256 = (
    "sha256:3e10f0e125ed70f6487bda0f0864c9191ddde9ab2d539514a520879b0131d26f"
)
SELECTED_EPISODE_HASH = (
    "sha256:1208ea465a123a7a6333dc2fd95b182492d5636fb1d8add50845d2f716313d4f"
)

INSTRUCTION_REPO_PATH = (
    ROOT
    / "docs"
    / "AirSlot_V2_Phase7_Final_Test_OneShot_Instruction_R2_20260919.md"
)
INSTRUCTION_DOWNLOAD_PATH = Path(
    r"D:\Download_all\AirSlot_V2_Phase7_Final_Test_OneShot_Instruction_R2_20260919.md"
)
FINAL_TEST_V2_ROOT = ROOT / "artifacts" / "experiment" / "final_test_v2"
LEGACY_FINAL_TEST_ROOT = ROOT / "artifacts" / "experiment" / "final_test"
GATE_A_PREFLIGHT_PATH = FINAL_TEST_V2_ROOT / "GATE_A_PREFLIGHT.json"
GATE_A_DRY_RUN_PATH = FINAL_TEST_V2_ROOT / "GATE_A_DRY_RUN.json"
GATE_B_RELEASE_PATH = FINAL_TEST_V2_ROOT / "GATE_B_HUMAN_RELEASE.json"
PHASE7_ACCESS_AUDIT_PATH = FINAL_TEST_V2_ROOT / "PHASE7_ACCESS_AUDIT.json"

HISTORICAL_FINAL_TEST_ACCESS_TOTAL = 1
PHASE7_ACCESS_INCREMENT = 1
PHASE7_CURRENT_TOTAL = 2
M3_NUMERICAL_COMPARISON_TOLERANCE = 1e-6
NOMINAL_Q = 0.10
Q_GRID = (0.05, 0.10, 0.20, 0.30)
NOMINAL_LAMBDA = 0.25
NOMINAL_TURNAROUND_Q20 = 41.0
NOMINAL_U_MAX = 45.0
U_MAX_BY_SPECIFICATION = {"Q80": 25.0, "nominal": 45.0, "Q95": 75.0}
REFERENCE_REPRESENTATION_ID = "HISTORY_H16:JOINT"
REFERENCE_AUTHORITY = "H_CSTAR_EQUALS_H_HISTORY_JOINT"
STAGE2_INFORMATION_COHORT = "FIXED_REFERENCE_STAGE_II_COHORT"
TYPED_SCIENTIFIC_STATES = (
    "ABSTAIN_NO_COMMON_SUPPORT",
    "UNDEFINED_ZERO_RECOVERABLE_VALUE",
    "NOT_ACTIONABLE",
    "N/A_NOT_DEFINED",
)
RELEASE_FIELDS = (
    "gate_a_commit",
    "instruction_sha256",
    "freeze_tag_object",
    "freeze_tag_target_commit",
    "cohort_authority_sha256",
    "cohort_manifest_sha256",
    "human_approved",
    "human_approval_timestamp",
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class Phase7Error(RuntimeError):
    """Base error for the Phase-7 runner."""


class TypedBlocker(Phase7Error):
    """A fail-closed Phase-7 blocker with a stable code."""

    def __init__(self, code: str, detail: Any = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail is not None else code)


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise TypedBlocker(code, detail)


def _file_sha256(path: Path) -> str:
    data = Path(path).read_bytes()
    return "sha256:" + sha256(data).hexdigest()


def _canonical_text_sha256(path: Path) -> str:
    """Hash text content after normalizing CRLF to LF.

    Two frozen artifacts were materialized into the R2 compatibility
    worktree with CRLF endings, while the annotated tag stores their
    canonical LF bytes.  The JSON payload is identical.  Gate A binds the
    tag-canonical hash and records the legacy worktree hash separately.
    """

    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return "sha256:" + sha256(data).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return content_id(body)


def _read_json(path: Path) -> dict[str, Any]:
    target = Path(path)
    _assert_not_legacy_final_test(target)
    return json.loads(target.read_text(encoding="utf-8"))


def _assert_not_legacy_final_test(path: Path) -> None:
    resolved = Path(path).resolve()
    forbidden = LEGACY_FINAL_TEST_ROOT.resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        raise TypedBlocker(
            "LEGACY_FINAL_TEST_TREE_ACCESS_FORBIDDEN",
            str(resolved),
        )


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    _assert_not_legacy_final_test(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _require_file_hash(path: Path, expected: str, code: str) -> None:
    _require(Path(path).is_file(), f"{code}_MISSING", str(path))
    _require(_file_sha256(path) == expected, f"{code}_MISMATCH", str(path))


def _require_canonical_text_hash(
    path: Path,
    canonical_expected: str,
    declared_worktree_expected: str,
    code: str,
) -> dict[str, Any]:
    """Validate canonical LF text bytes and record legacy hash semantics."""

    _require(Path(path).is_file(), f"{code}_MISSING", str(path))
    canonical_hash = _canonical_text_sha256(path)
    raw_hash = _file_sha256(path)
    _require(
        canonical_hash == canonical_expected,
        f"{code}_CANONICAL_HASH_MISMATCH",
        {"actual": canonical_hash, "expected": canonical_expected},
    )
    _require(
        raw_hash in {canonical_expected, declared_worktree_expected},
        f"{code}_RAW_HASH_MISMATCH",
        {"actual": raw_hash, "accepted": [canonical_expected, declared_worktree_expected]},
    )
    return {
        "path": str(Path(path).relative_to(ROOT)),
        "canonical_lf_sha256": canonical_hash,
        "raw_sha256": raw_hash,
        "declared_worktree_sha256": declared_worktree_expected,
        "semantics": "LINE_ENDING_COMPATIBILITY_CRLF_TO_CANONICAL_LF_NUMERIC_PAYLOAD_UNCHANGED",
    }


def _json_iso(value: str, code: str) -> None:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise TypedBlocker(code, value) from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, code, value)


def make_release(
    *,
    gate_a_commit: str = "RESOLVED_AFTER_GATE_A_COMMIT",
    instruction_sha256: str | None = None,
    human_approval_timestamp: str = "2026-09-19T00:00:00+00:00",
) -> dict[str, Any]:
    """Build a schema-complete synthetic release for dry-run tests."""

    instruction_hash = instruction_sha256 or _sha256_bytes(
        INSTRUCTION_REPO_PATH.read_bytes()
    )
    return {
        "gate_a_commit": gate_a_commit,
        "instruction_sha256": instruction_hash,
        "freeze_tag_object": R2_TAG_OBJECT,
        "freeze_tag_target_commit": R2_TAG_TARGET_COMMIT,
        "cohort_authority_sha256": COHORT_AUTHORITY_FILE_SHA256,
        "cohort_manifest_sha256": EXECUTED_COHORT_MANIFEST_SHA256,
        "human_approved": True,
        "human_approval_timestamp": human_approval_timestamp,
    }


def validate_release_schema(release: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact Gate-B human-release schema."""

    keys = set(release)
    _require(
        keys == set(RELEASE_FIELDS),
        "GATE_B_RELEASE_SCHEMA_MISMATCH",
        sorted(keys),
    )
    _require(
        isinstance(release["gate_a_commit"], str)
        and (
            release["gate_a_commit"] == "RESOLVED_AFTER_GATE_A_COMMIT"
            or bool(COMMIT_RE.fullmatch(release["gate_a_commit"]))
        ),
        "GATE_B_RELEASE_GATE_A_COMMIT_INVALID",
        release["gate_a_commit"],
    )
    for field in (
        "instruction_sha256",
        "cohort_authority_sha256",
        "cohort_manifest_sha256",
    ):
        _require(
            isinstance(release[field], str)
            and bool(SHA256_RE.fullmatch(release[field])),
            "GATE_B_RELEASE_HASH_FIELD_INVALID",
            field,
        )
    _require(
        release["freeze_tag_object"] == R2_TAG_OBJECT,
        "GATE_B_RELEASE_FREEZE_TAG_OBJECT_MISMATCH",
        release["freeze_tag_object"],
    )
    _require(
        release["freeze_tag_target_commit"] == R2_TAG_TARGET_COMMIT,
        "GATE_B_RELEASE_FREEZE_TAG_TARGET_MISMATCH",
        release["freeze_tag_target_commit"],
    )
    _require(
        release["cohort_authority_sha256"] == COHORT_AUTHORITY_FILE_SHA256,
        "GATE_B_RELEASE_COHORT_AUTHORITY_MISMATCH",
        release["cohort_authority_sha256"],
    )
    _require(
        release["cohort_manifest_sha256"] == EXECUTED_COHORT_MANIFEST_SHA256,
        "GATE_B_RELEASE_COHORT_MANIFEST_MISMATCH",
        release["cohort_manifest_sha256"],
    )
    _require(
        release["instruction_sha256"] == _instruction_sha256(),
        "GATE_B_RELEASE_INSTRUCTION_HASH_MISMATCH",
        release["instruction_sha256"],
    )
    _require(
        release["human_approved"] is True,
        "GATE_B_RELEASE_HUMAN_APPROVAL_REQUIRED",
    )
    _require(
        isinstance(release["human_approval_timestamp"], str),
        "GATE_B_RELEASE_HUMAN_TIMESTAMP_REQUIRED",
    )
    _json_iso(
        release["human_approval_timestamp"],
        "GATE_B_RELEASE_HUMAN_TIMESTAMP_INVALID",
    )
    return {
        "status": "PASS",
        "schema_fields": list(RELEASE_FIELDS),
        "human_approved": True,
        "freeze_tag_object": release["freeze_tag_object"],
        "freeze_tag_target_commit": release["freeze_tag_target_commit"],
    }


def _instruction_sha256() -> str:
    _require(
        INSTRUCTION_REPO_PATH.is_file(),
        "PHASE7_INSTRUCTION_REPO_COPY_MISSING",
        str(INSTRUCTION_REPO_PATH),
    )
    return _file_sha256(INSTRUCTION_REPO_PATH)


def validate_instruction_copies() -> dict[str, Any]:
    """Require byte-identical repository and Download_all instruction copies."""

    _require(
        INSTRUCTION_REPO_PATH.is_file(),
        "PHASE7_INSTRUCTION_REPO_COPY_MISSING",
        str(INSTRUCTION_REPO_PATH),
    )
    _require(
        INSTRUCTION_DOWNLOAD_PATH.is_file(),
        "PHASE7_INSTRUCTION_DOWNLOAD_COPY_MISSING",
        str(INSTRUCTION_DOWNLOAD_PATH),
    )
    repo_bytes = INSTRUCTION_REPO_PATH.read_bytes()
    download_bytes = INSTRUCTION_DOWNLOAD_PATH.read_bytes()
    _require(
        repo_bytes == download_bytes,
        "PHASE7_INSTRUCTION_COPIES_NOT_IDENTICAL",
    )
    return {
        "status": "PASS",
        "repo_path": str(INSTRUCTION_REPO_PATH),
        "download_path": str(INSTRUCTION_DOWNLOAD_PATH),
        "sha256": _sha256_bytes(repo_bytes),
        "byte_identical": True,
    }


def validate_r2_authority() -> dict[str, Any]:
    """Validate the immutable Freeze R2 tag, registry and artifact identities."""

    tag_object = _git("rev-parse", f"{R2_TAG}^{{tag}}")
    tag_target = _git("rev-parse", f"{R2_TAG}^{{commit}}")
    _require(tag_object == R2_TAG_OBJECT, "R2_TAG_OBJECT_MISMATCH", tag_object)
    _require(
        tag_target == R2_TAG_TARGET_COMMIT,
        "R2_TAG_TARGET_MISMATCH",
        tag_target,
    )

    _require_file_hash(
        R2_REGISTRY_PATH,
        R2_REGISTRY_FILE_SHA256,
        "R2_REGISTRY_FILE_HASH",
    )
    registry = _read_json(R2_REGISTRY_PATH)
    _require(
        registry.get("status") == "SCIENTIFIC_FREEZE_R2_ACTIVE",
        "R2_REGISTRY_STATUS_INVALID",
        registry.get("status"),
    )
    _require(
        registry.get("artifact_hash") == R2_REGISTRY_ARTIFACT_HASH,
        "R2_REGISTRY_ARTIFACT_HASH_MISMATCH",
        registry.get("artifact_hash"),
    )
    _require(
        _payload_sha256(registry) == R2_REGISTRY_ARTIFACT_HASH,
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
        and float(tolerance.get("value")) == M3_NUMERICAL_COMPARISON_TOLERANCE
        and tolerance.get("scientific_parameter") is False,
        "R2_NUMERICAL_TOLERANCE_CONTRACT_INVALID",
        tolerance,
    )

    _require_file_hash(
        PARENT_REGISTRY_PATH,
        PARENT_REGISTRY_FILE_SHA256,
        "PARENT_REGISTRY_FILE_HASH",
    )
    parent = registry.get("parent_freeze", {})
    _require(
        registry.get("activation_state", {}).get("parent_tag_object")
        == PARENT_TAG_OBJECT,
        "R2_PARENT_TAG_OBJECT_MISMATCH",
    )
    _require(
        registry.get("activation_state", {}).get("parent_tag_target_commit")
        == PARENT_TAG_TARGET_COMMIT,
        "R2_PARENT_TAG_TARGET_MISMATCH",
    )
    _require(
        parent.get("registry_file_sha256") == PARENT_REGISTRY_FILE_SHA256,
        "R2_PARENT_REGISTRY_DECLARED_HASH_MISMATCH",
    )
    parent_blob_oid = _git(
        "hash-object",
        PARENT_REGISTRY_PATH.relative_to(ROOT).as_posix(),
    )
    _require(
        parent.get("registry_blob_sha256") == PARENT_REGISTRY_BLOB_OID_FIELD,
        "R2_PARENT_REGISTRY_BLOB_FIELD_MISMATCH",
        parent.get("registry_blob_sha256"),
    )
    _require(
        parent_blob_oid == PARENT_REGISTRY_BLOB_OID_FIELD.removeprefix("sha256:"),
        "R2_PARENT_REGISTRY_BLOB_OID_MISMATCH",
        parent_blob_oid,
    )
    parent_actual_sha256 = _file_sha256(PARENT_REGISTRY_PATH)
    _require(
        parent_actual_sha256 != PARENT_REGISTRY_BLOB_OID_FIELD,
        "R2_PARENT_REGISTRY_BLOB_LABEL_UNEXPECTEDLY_SHA256",
    )

    _require_file_hash(
        R2_RECONCILIATION_PATH,
        registry.get("r2_authority_reconciliation", {})
        .get("artifact", {})
        .get("file_sha256", ""),
        "R2_RECONCILIATION_FILE_HASH",
    )
    reconciliation = _read_json(R2_RECONCILIATION_PATH)
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
        <= M3_NUMERICAL_COMPARISON_TOLERANCE
        and float(
            reconciliation.get("error_summary", {}).get(
                "recoverable_value_absolute_error_max", float("inf")
            )
        )
        <= M3_NUMERICAL_COMPARISON_TOLERANCE,
        "R2_RECONCILIATION_ERROR_BOUND_INVALID",
        reconciliation.get("error_summary"),
    )

    _require_file_hash(
        M2_V5_REGISTRY_PATH,
        M2_V5_REGISTRY_FILE_SHA256,
        "M2_V5_REGISTRY_FILE_HASH",
    )
    _require_file_hash(
        PASSENGER_SUPERSESSION_V3_PATH,
        PASSENGER_SUPERSESSION_V3_FILE_SHA256,
        "PASSENGER_SUPERSESSION_V3_FILE_HASH",
    )
    _require_file_hash(
        M2_REFERENCE_PATH,
        M2_REFERENCE_FILE_SHA256,
        "M2_REFERENCE_FILE_HASH",
    )
    f_continuity_hash = _require_canonical_text_hash(
        F_CONTINUITY_SCALE_PATH,
        F_CONTINUITY_SCALE_FILE_SHA256,
        F_CONTINUITY_SCALE_DECLARED_WORKTREE_SHA256,
        "F_CONTINUITY_SCALE_FILE_HASH",
    )
    train_support_hash = _require_canonical_text_hash(
        TRAIN_SUPPORT_SUMMARY_PATH,
        TRAIN_SUPPORT_SUMMARY_FILE_SHA256,
        TRAIN_SUPPORT_SUMMARY_DECLARED_WORKTREE_SHA256,
        "TRAIN_SUPPORT_SUMMARY_FILE_HASH",
    )
    _require_file_hash(
        TRAIN_SUPPORT_SAMPLES_PATH,
        TRAIN_SUPPORT_SAMPLES_FILE_SHA256,
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
        == NOMINAL_TURNAROUND_Q20,
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
        == HISTORICAL_FINAL_TEST_ACCESS_TOTAL
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
        "tag": R2_TAG,
        "tag_object": tag_object,
        "tag_target_commit": tag_target,
        "registry_file_sha256": R2_REGISTRY_FILE_SHA256,
        "registry_artifact_hash": R2_REGISTRY_ARTIFACT_HASH,
        "formal_solver": "PYOMO_HIGHS",
        "parity_oracle": "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
        "objective_perturbation": "NONE",
        "long_term_deviation": False,
        "numerical_tolerance": {
            "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
            "value": M3_NUMERICAL_COMPARISON_TOLERANCE,
            "scientific_parameter": False,
        },
        "parent_registry": {
            "tag": PARENT_TAG,
            "tag_object": PARENT_TAG_OBJECT,
            "tag_target_commit": PARENT_TAG_TARGET_COMMIT,
            "registry_file_sha256": PARENT_REGISTRY_FILE_SHA256,
            "registry_blob_oid": parent_blob_oid,
            "registry_blob_oid_field": PARENT_REGISTRY_BLOB_OID_FIELD,
            "blob_field_semantics": "GIT_BLOB_OID_WITH_SHA256_PREFIX_COMPATIBILITY_LABEL",
            "actual_file_sha256": parent_actual_sha256,
        },
        "historical_ruling_r3": {
            "text": r3_text,
            "status": "SUPERSEDED_BY_TOP_LEVEL_R2_AUTHORITY",
            "authoritative_top_level_formal_solver": "PYOMO_HIGHS",
        },
        "reconciliation": {
            "path": str(R2_RECONCILIATION_PATH.relative_to(ROOT)),
            "counts": counts,
            "error_summary": reconciliation.get("error_summary"),
        },
        "artifact_identities": {
            "m2_typical_turnaround_reference": {
                "identity": "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57",
                "file_sha256": M2_REFERENCE_FILE_SHA256,
                "statistic": "MEDIAN",
                "scope": "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY",
                "global_fallback_minutes": 57.0,
            },
            "m3_stage2_turnaround_lower_bound": {
                "identity": "M3_STAGE2_TURNAROUND_LOWER_BOUND_Q20",
                "value_minutes": NOMINAL_TURNAROUND_Q20,
                "scope": "M3_STAGE2_FEASIBILITY_ONLY",
            },
            "f_continuity_cu_scale": {
                "identity": "M2_V5_F_CONTINUITY_SCALE_CORRECTION_V1",
                "file_sha256": F_CONTINUITY_SCALE_FILE_SHA256,
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
            "historical_access_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
    }


def validate_cohort_reference() -> dict[str, Any]:
    """Validate the frozen pre-access cohort identity without reading Q4 data."""

    _require_file_hash(
        COHORT_AUTHORITY_PATH,
        COHORT_AUTHORITY_FILE_SHA256,
        "COHORT_AUTHORITY_FILE_HASH",
    )
    _require_file_hash(
        COHORT_MANIFEST_PATH,
        COHORT_MANIFEST_FILE_SHA256,
        "COHORT_MANIFEST_FILE_HASH",
    )
    authority = _read_json(COHORT_AUTHORITY_PATH)
    manifest = _read_json(COHORT_MANIFEST_PATH)

    _require(
        authority.get("authority_status") == "FINAL_TEST_COHORT_AUTHORITY_LOCKED",
        "COHORT_AUTHORITY_STATUS_INVALID",
    )
    _require(
        int(authority.get("final_test_episode_count", -1)) == 128,
        "COHORT_AUTHORITY_EPISODE_COUNT_INVALID",
    )
    selection = authority.get("selection", {})
    _require(
        selection.get("seed") == 20260813
        and selection.get("rng_scope") == "FINAL_TEST_ONLY_FRESH_SEED"
        and selection.get("selection_pre_outcome") is True
        and selection.get("replacement_policy") == "NO_REPLACEMENT_AFTER_SELECTION",
        "COHORT_AUTHORITY_SELECTION_INVALID",
        selection,
    )
    _require(
        authority.get("source_window", {}).get("months") == [10, 11, 12],
        "COHORT_AUTHORITY_SOURCE_WINDOW_INVALID",
    )
    _require(
        manifest.get("authority_status") == "FINAL_TEST_COHORT_AUTHORITY_LOCKED",
        "COHORT_MANIFEST_STATUS_INVALID",
    )
    episode_ids = tuple(str(value) for value in manifest.get("selected_episode_ids", ()))
    _require(
        len(episode_ids) == 128 and len(set(episode_ids)) == 128,
        "COHORT_MANIFEST_EPISODE_IDS_INVALID",
    )
    payload_hash = _sha256_bytes("\n".join(sorted(episode_ids)).encode("utf-8"))
    _require(
        payload_hash == SELECTED_EPISODE_HASH,
        "COHORT_MANIFEST_SELECTED_EPISODE_HASH_MISMATCH",
        payload_hash,
    )
    _require(
        manifest.get("selected_episode_hash") == SELECTED_EPISODE_HASH,
        "COHORT_MANIFEST_DECLARED_EPISODE_HASH_MISMATCH",
    )
    _require(
        manifest.get("selection_reused") is True
        and manifest.get("selection_reperformed") is False,
        "COHORT_MANIFEST_SELECTION_REUSE_INVALID",
    )
    _require(
        manifest.get("artifact_manifest_sha256")
        == EXECUTED_COHORT_MANIFEST_SHA256,
        "COHORT_MANIFEST_EXECUTED_HASH_MISMATCH",
    )
    return {
        "status": "PASS",
        "authority_path": str(COHORT_AUTHORITY_PATH.relative_to(ROOT)),
        "authority_file_sha256": COHORT_AUTHORITY_FILE_SHA256,
        "manifest_path": str(COHORT_MANIFEST_PATH.relative_to(ROOT)),
        "manifest_file_sha256": COHORT_MANIFEST_FILE_SHA256,
        "executed_manifest_sha256": EXECUTED_COHORT_MANIFEST_SHA256,
        "selected_episode_count": len(episode_ids),
        "selected_episode_hash": SELECTED_EPISODE_HASH,
        "final_test_cohort_reused": True,
        "final_test_cohort_reselected": False,
        "source_months": [10, 11, 12],
        "historical_access_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
        "raw_q4_read": False,
    }


def _release_fingerprint(release: Mapping[str, Any]) -> str:
    body = json.dumps(release, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_bytes(body.encode("utf-8"))


def _access_epoch_id(release: Mapping[str, Any]) -> str:
    return _release_fingerprint(release)


def open_access_epoch(
    audit_path: Path,
    release: Mapping[str, Any],
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Open the one Phase-7 access epoch or return the existing same epoch."""

    validate_release_schema(release)
    target = Path(audit_path)
    _assert_not_legacy_final_test(target)
    release_hash = _release_fingerprint(release)
    if target.exists():
        payload = _read_json(target)
        _require(
            payload.get("access_epoch_id") == _access_epoch_id(release),
            "PHASE7_ACCESS_EPOCH_ID_MISMATCH",
            payload.get("access_epoch_id"),
        )
        _require(
            payload.get("release_binding_sha256") == release_hash,
            "PHASE7_ACCESS_RELEASE_BINDING_MISMATCH",
        )
        _require(
            payload.get("phase7_increment") == PHASE7_ACCESS_INCREMENT
            and payload.get("current_total") == PHASE7_CURRENT_TOTAL,
            "PHASE7_ACCESS_INCREMENT_INVALID",
            payload,
        )
        updated = dict(payload)
        updated["retry_within_same_epoch"] = True
        updated["retry_count"] = int(payload.get("retry_count", 0)) + 1
        _write_json_atomic(target, updated)
        return updated

    opened = timestamp or datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "AIR_SLOT_V2_PHASE7_ACCESS_AUDIT_V1",
        "status": "PHASE7_ACCESS_EPOCH_OPEN",
        "access_epoch_id": _access_epoch_id(release),
        "access_epoch_opened": opened,
        "raw_read_started": False,
        "raw_read_completed": False,
        "retry_within_same_epoch": False,
        "retry_count": 0,
        "historical_access_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
        "phase7_increment": PHASE7_ACCESS_INCREMENT,
        "current_total": PHASE7_CURRENT_TOTAL,
        "new_final_test_execution": True,
        "release_binding_sha256": release_hash,
        "release": dict(release),
        "same_epoch_retry_policy": "BINDING_AND_IO_FIXES_ONLY",
        "scientific_definition_change_closes_epoch": True,
        "cohort_change_closes_epoch": True,
        "parameter_selection_change_closes_epoch": True,
        "reporting_choice_change_closes_epoch": True,
    }
    _write_json_atomic(target, payload)
    return payload


def mark_access_read_started(
    audit_path: Path,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = _read_json(Path(audit_path))
    _require(
        payload.get("status") == "PHASE7_ACCESS_EPOCH_OPEN",
        "PHASE7_ACCESS_EPOCH_NOT_OPEN",
    )
    payload["raw_read_started"] = True
    payload["raw_read_started_at"] = timestamp or datetime.now(timezone.utc).isoformat()
    _write_json_atomic(Path(audit_path), payload)
    return payload


def mark_access_read_completed(
    audit_path: Path,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = _read_json(Path(audit_path))
    _require(
        payload.get("raw_read_started") is True,
        "PHASE7_RAW_READ_NOT_STARTED",
    )
    payload["raw_read_completed"] = True
    payload["raw_read_completed_at"] = (
        timestamp or datetime.now(timezone.utc).isoformat()
    )
    payload["status"] = "PHASE7_ACCESS_EPOCH_COMPLETE"
    _write_json_atomic(Path(audit_path), payload)
    return payload


def _dry_run_attention() -> dict[str, Any]:
    from model.M3.stage1 import attention_capacity_k, select_paired_attention

    candidates = (
        ("episode-a", "chain-a", "node-a"),
        ("episode-b", "chain-b", "node-b"),
        ("episode-c", "chain-c", "node-c"),
        ("episode-d", "chain-d", "node-d"),
        ("episode-e", "chain-e", "node-e"),
    )
    delay = tuple(
        PrioritySignal(
            signal_type=SignalKind.DELAY,
            episode_id=episode_id,
            chain_id=chain_id,
            node_id=node_id,
            representation_id=REFERENCE_REPRESENTATION_ID,
            score=float(index),
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.95,
            comparison_support_threshold=0.90,
        )
        for index, (episode_id, chain_id, node_id) in enumerate(candidates, start=1)
    )
    consequence = tuple(
        PrioritySignal(
            signal_type=SignalKind.CONSEQUENCE,
            episode_id=episode_id,
            chain_id=chain_id,
            node_id=node_id,
            representation_id=REFERENCE_REPRESENTATION_ID,
            score=float(6 - index),
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.95,
            comparison_support_threshold=0.90,
        )
        for index, (episode_id, chain_id, node_id) in enumerate(candidates, start=1)
    )
    rows = []
    for q in Q_GRID:
        delay_decision, consequence_decision = select_paired_attention(
            delay,
            consequence,
            q=q,
        )
        _require(
            delay_decision.k == consequence_decision.k
            == attention_capacity_k(q, len(candidates)),
            "GATE_A_STAGE1_CAPACITY_MISMATCH",
            q,
        )
        rows.append(
            {
                "q": q,
                "k": delay_decision.k,
                "delay_selected": [
                    item.node_id for item in delay_decision.entries if item.selected
                ],
                "consequence_selected": [
                    item.node_id
                    for item in consequence_decision.entries
                    if item.selected
                ],
            }
        )

    abstaining = PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id="episode-z",
        chain_id="chain-z",
        node_id="node-z",
        representation_id=REFERENCE_REPRESENTATION_ID,
        score=None,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        comparison_support_mass=0.20,
        comparison_support_threshold=0.90,
        reason_codes=("M2_COMMON_SUPPORT_BELOW_THRESHOLD",),
    )
    mixed = select_paired_attention(
        tuple(delay) + (
            PrioritySignal(
                signal_type=SignalKind.DELAY,
                episode_id="episode-z",
                chain_id="chain-z",
                node_id="node-z",
                representation_id=REFERENCE_REPRESENTATION_ID,
                score=None,
                support=SupportState.ABSTAIN,
                status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
                comparison_support_mass=0.20,
                comparison_support_threshold=0.90,
            ),
        ),
        tuple(consequence) + (abstaining,),
        q=NOMINAL_Q,
    )[1]
    _require(
        all(entry.node_id != "node-z" for entry in mixed.entries),
        "GATE_A_ABSTAINING_NODE_NOT_EXCLUDED",
    )
    return {
        "status": "PASS",
        "q_grid": list(Q_GRID),
        "nominal_q": NOMINAL_Q,
        "capacity_rows": rows,
        "abstaining_node_typed": True,
    }


def _dry_run_stage2_and_typed() -> dict[str, Any]:
    from model.M2.consequence_service import (
        ConsequenceReferenceBinding,
        M2ConsequenceService,
    )
    from model.M2.scientific_registry import load_active_v2_cu_registry
    from model.M3.solver import solve_with_highs
    from model.M3.stage2 import action_grid, solve_recovery
    from model.M3.transition import TransitionContext
    from model.common.decision_contracts import (
        HeadroomSummary,
        HistoryScope,
        StateRepresentationSpec,
        StateScenario,
        StateScenarioSet,
        TemporalKind,
        UncertaintyKind,
    )

    registry = load_active_v2_cu_registry()
    binding = ConsequenceReferenceBinding(
        reference_id="GATE_A_SYNTHETIC_NODE",
        turnaround_reference_minutes=NOMINAL_TURNAROUND_Q20,
        taxi_reference_minutes=0.0,
        expected_pax=150.0,
        connection_share=0.35,
        downstream_exposure=1.2,
    )
    service = M2ConsequenceService(registry, {"gate-a-node": binding})
    representation = StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )
    scenarios = (
        StateScenario(
            scenario_id=0,
            scenario_weight=0.5,
            stage=OperationalStage.PRE_IB,
            t_ib_minutes=620.0,
            d_ob_minutes=90.0,
            d_tx_minutes=15.0,
            d_to_minutes=105.0,
        ),
        StateScenario(
            scenario_id=1,
            scenario_weight=0.5,
            stage=OperationalStage.PRE_IB,
            t_ib_minutes=650.0,
            d_ob_minutes=110.0,
            d_tx_minutes=20.0,
            d_to_minutes=130.0,
        ),
    )
    state_set = StateScenarioSet(
        episode_id="gate-a-episode",
        chain_id="gate-a-chain",
        node_id="gate-a-node",
        stage=OperationalStage.PRE_IB,
        representation=representation,
        scenarios=scenarios,
    )
    context = TransitionContext(
        sobt_minutes=600.0,
        turnaround_lower_bound_minutes=NOMINAL_TURNAROUND_Q20,
    )
    headroom = HeadroomSummary(
        u_max=NOMINAL_U_MAX,
        turnaround_lower_bound_q=NOMINAL_TURNAROUND_Q20,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=10,
        source_id="GATE_A_SYNTHETIC_NOT_SCIENTIFIC_SUPPORT",
        floor_to_minutes=5.0,
    )
    parity = solve_with_highs(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom,
    )
    _require(parity.u_star_parity, "GATE_A_HIGHS_ENUMERATION_ACTION_DISAGREEMENT")
    _require(parity.objective_parity, "GATE_A_HIGHS_ENUMERATION_OBJECTIVE_DISAGREEMENT")
    _require(
        parity.recoverable_value_parity,
        "GATE_A_HIGHS_ENUMERATION_VALUE_DISAGREEMENT",
    )
    _require(
        parity.recoverable_value_formal >= -M3_NUMERICAL_COMPARISON_TOLERANCE,
        "GATE_A_NEGATIVE_RECOVERABLE_VALUE",
    )
    _require(
        parity.u_star_formal in action_grid(NOMINAL_U_MAX),
        "GATE_A_ACTION_OUTSIDE_SPECIFICATION_GRID",
    )

    action_grid_contracts = {
        name: list(action_grid(u_max))
        for name, u_max in U_MAX_BY_SPECIFICATION.items()
    }
    _require(
        action_grid_contracts["Q80"][-1] == 25.0
        and action_grid_contracts["nominal"][-1] == 45.0
        and action_grid_contracts["Q95"][-1] == 75.0,
        "GATE_A_SPECIFICATION_DEPENDENT_GRID_INVALID",
    )

    non_actionable = solve_recovery(
        StateScenarioSet(
            episode_id="gate-a-taxi",
            chain_id="gate-a-taxi-chain",
            node_id="gate-a-taxi",
            stage=OperationalStage.POST_OB_PRE_TO,
            representation=representation,
            scenarios=(
                StateScenario(
                    scenario_id=0,
                    scenario_weight=1.0,
                    stage=OperationalStage.POST_OB_PRE_TO,
                    t_ib_minutes=10.0,
                    d_ob_minutes=5.0,
                    d_tx_minutes=0.0,
                    d_to_minutes=5.0,
                ),
            ),
        ),
        context=context,
        service=service,
    )
    _require(
        non_actionable.actionable_status is TypedStatus.NOT_ACTIONABLE,
        "GATE_A_TAXI_COMP_NOT_ACTIONABLE",
    )
    _require(non_actionable.u_star == 0.0, "GATE_A_TAXI_COMP_POSITIVE_ACTION")
    _require(
        non_actionable.recoverable_value is None,
        "GATE_A_TAXI_COMP_UNDEFINED_VALUE_NOT_TYPED",
    )

    undefined = DecisionEvaluation(
        reference_id="reference",
        comparator_id="comparator",
        cohort_id="empty-or-zero",
        family=EvaluationFamily.RECOVERY,
        delta_recovery_objective=0.0,
        reference_recoverable_value=0.0,
        L_rec=None,
        A0=None,
        A5=None,
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE,
    )
    _require(
        undefined.value_status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE
        and undefined.L_rec is None,
        "GATE_A_TYPED_UNDEFINED_NOT_PRESERVED",
    )
    empty_attention = DecisionEvaluation(
        reference_id="reference",
        comparator_id="comparator",
        cohort_id="empty-reference-cohort",
        family=EvaluationFamily.ATTENTION,
        delta_attention_value=0.0,
        reference_attention_value=0.0,
        L_att=None,
        support_status=SupportState.ABSTAIN,
        value_status=TypedStatus.N_A_NOT_DEFINED,
    )
    _require(
        empty_attention.value_status is TypedStatus.N_A_NOT_DEFINED,
        "GATE_A_EMPTY_COHORT_TYPED_STATE_MISSING",
    )

    reference_attention = DecisionEvaluation(
        reference_id="reference",
        comparator_id="reference",
        cohort_id="reference",
        family=EvaluationFamily.ATTENTION,
        delta_attention_value=0.0,
        reference_attention_value=1.0,
        L_att=0.0,
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.SUPPORTED,
    )
    reference_recovery = DecisionEvaluation(
        reference_id="reference",
        comparator_id="reference",
        cohort_id="reference",
        family=EvaluationFamily.RECOVERY,
        delta_recovery_objective=0.0,
        reference_recoverable_value=1.0,
        L_rec=0.0,
        A0=1.0,
        A5=1.0,
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.SUPPORTED,
    )
    _require(
        reference_attention.L_att == 0.0
        and reference_recovery.L_rec == 0.0
        and reference_recovery.A0 == reference_recovery.A5 == 1.0,
        "GATE_A_REFERENCE_INVARIANTS_NOT_PRESERVED",
    )

    return {
        "status": "PASS",
        "formal_solver": parity.formal_solver,
        "parity_oracle": parity.parity_oracle,
        "u_star_formal": parity.u_star_formal,
        "u_star_oracle": parity.u_star_oracle,
        "objective_absolute_error": parity.objective_absolute_error,
        "recoverable_value_absolute_error": parity.recoverable_value_absolute_error,
        "recoverable_value_formal": parity.recoverable_value_formal,
        "tie_break_applied": parity.tie_break_applied,
        "near_tie_candidate_count": parity.near_tie_candidate_count,
        "action_grid_by_specification": action_grid_contracts,
        "typed_states": {
            "NOT_ACTIONABLE": True,
            "UNDEFINED_ZERO_RECOVERABLE_VALUE": True,
            "N/A_NOT_DEFINED": True,
        },
        "reference_invariants": {
            "L_att": reference_attention.L_att,
            "L_rec": reference_recovery.L_rec,
            "A0": reference_recovery.A0,
            "A5": reference_recovery.A5,
        },
        "reference_authority": {
            "reference_representation_id": REFERENCE_REPRESENTATION_ID,
            "H_C_STAR": REFERENCE_AUTHORITY,
            "R_STAR": STAGE2_INFORMATION_COHORT,
        },
    }


def run_dry_run() -> dict[str, Any]:
    """Run the Gate-A synthetic and Development-safe scientific smoke."""

    try:
        from validation.m3_enumeration_highs_parity import run_cases as parity_cases
    except Exception as error:  # pragma: no cover - environment failure path
        raise TypedBlocker("GATE_A_ENVIRONMENT_IMPORT_FAILED", str(error)) from error

    parity = parity_cases()
    _require(
        parity.get("status") == "PASS",
        "GATE_A_M3_PARITY_DRY_RUN_FAILED",
        parity,
    )
    attention = _dry_run_attention()
    stage2 = _dry_run_stage2_and_typed()
    with tempfile.TemporaryDirectory(prefix="air_slot_phase7_gate_a_") as directory:
        audit_path = Path(directory) / "PHASE7_ACCESS_AUDIT.json"
        release = make_release()
        first = open_access_epoch(
            audit_path,
            release,
            timestamp="2026-09-19T00:00:00+00:00",
        )
        second = open_access_epoch(
            audit_path,
            release,
            timestamp="2026-09-19T00:00:01+00:00",
        )
        _require(
            first["access_epoch_id"] == second["access_epoch_id"],
            "GATE_A_ACCESS_EPOCH_ID_NOT_STABLE",
        )
        _require(
            second["retry_within_same_epoch"] is True
            and second["phase7_increment"] == 1
            and second["current_total"] == 2,
            "GATE_A_ACCESS_EPOCH_RETRY_INCREMENTED",
        )
    return {
        "status": "PASS",
        "scope": "SYNTHETIC_AND_DEVELOPMENT_SAFE_FIXTURES_ONLY",
        "final_test_data_read": False,
        "q4_raw_read": False,
        "legacy_final_test_result_tree_read": False,
        "parity": parity,
        "attention": attention,
        "stage2": stage2,
        "release_schema": validate_release_schema(make_release()),
        "access_epoch_idempotence": {
            "status": "PASS",
            "same_epoch_retry_increment": 0,
            "epoch_increment": PHASE7_ACCESS_INCREMENT,
            "current_total": PHASE7_CURRENT_TOTAL,
            "one_epoch_per_release": True,
        },
    }


def _gate_a_commit_value() -> str:
    head = _git("rev-parse", "HEAD")
    if head == R2_TAG_TARGET_COMMIT:
        return "RESOLVED_AFTER_GATE_A_COMMIT"
    return head


def build_gate_a_preflight() -> dict[str, Any]:
    """Build the Gate-A preflight object without writing it."""

    r2 = validate_r2_authority()
    cohort = validate_cohort_reference()
    instruction = validate_instruction_copies()
    dry_run = run_dry_run()
    gate_b_release_present = GATE_B_RELEASE_PATH.exists()
    _require(
        gate_b_release_present is False,
        "GATE_A_GATE_B_RELEASE_ALREADY_PRESENT",
        str(GATE_B_RELEASE_PATH),
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
            "historical_access_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
        "release_schema": {
            "path": str(GATE_B_RELEASE_PATH.relative_to(ROOT)),
            "required_fields": list(RELEASE_FIELDS),
            "human_release_required": True,
        },
        "nominal_specification": {
            "q": NOMINAL_Q,
            "q_grid": list(Q_GRID),
            "lambda": NOMINAL_LAMBDA,
            "turnaround_q20_minutes": NOMINAL_TURNAROUND_Q20,
            "u_max_minutes": NOMINAL_U_MAX,
            "history_capacity": 16,
            "m_cs": 0.90,
        },
        "reference_authority": {
            "H_C_STAR": REFERENCE_AUTHORITY,
            "R_STAR": STAGE2_INFORMATION_COHORT,
            "reference_representation_id": REFERENCE_REPRESENTATION_ID,
            "alternative_representations_may_define_H_r_for_L_att": True,
            "stage2_information_comparison_uses_fixed_R_star": True,
        },
        "typed_scientific_states": list(TYPED_SCIENTIFIC_STATES),
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
            "gate_b_release_present": GATE_B_RELEASE_PATH.exists(),
            "phase7_access_epoch_opened": False,
        },
        "final_test_accounting": {
            "historical_access_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "current_freeze_run_increment": 0,
            "current_total": HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
            "new_final_test_execution": False,
            "phase_7_entered": False,
        },
    }


def run_gate_a(
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Run Gate A and atomically write its preflight and dry-run artifacts."""

    root = Path(output_root) if output_root is not None else FINAL_TEST_V2_ROOT
    preflight_path = root / GATE_A_PREFLIGHT_PATH.name
    dry_run_path = root / GATE_A_DRY_RUN_PATH.name
    try:
        payload = build_gate_a_preflight()
        _write_json_atomic(dry_run_path, payload["dry_run"])
        _write_json_atomic(preflight_path, payload)
        return payload
    except TypedBlocker as error:
        payload = _blocked_payload(error.code, error.detail)
        _write_json_atomic(preflight_path, payload)
        return payload


def execute_gate_b(
    *,
    release_path: Path,
    audit_path: Path | None = None,
    pipeline: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate a human release and run an explicitly supplied executor.

    Gate A deliberately leaves ``pipeline`` unbound.  This prevents an
    accidental Gate-B run from opening the access epoch without a human
    release and a separately reviewed scientific executor.
    """

    release = _read_json(Path(release_path))
    validated = validate_release_schema(release)
    target_audit = (
        Path(audit_path) if audit_path is not None else PHASE7_ACCESS_AUDIT_PATH
    )
    if pipeline is None:
        raise TypedBlocker(
            "GATE_B_SCIENTIFIC_EXECUTOR_NOT_BOUND",
            "human release validated, but no sealed Phase-7 executor was supplied",
        )
    epoch = open_access_epoch(target_audit, release)
    mark_access_read_started(target_audit)
    result = pipeline(
        {
            "release": release,
            "release_validation": validated,
            "access_epoch": epoch,
        }
    )
    mark_access_read_completed(target_audit)
    return {
        "status": "PASS",
        "release_validation": validated,
        "access_epoch": epoch,
        "result": result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gate-a", action="store_true", help="run Phase-7 Gate A")
    mode.add_argument("--gate-b", action="store_true", help="run Phase-7 Gate B")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)

    if args.gate_b:
        if args.release is None:
            raise SystemExit("--release is required with --gate-b")
        try:
            result = execute_gate_b(release_path=args.release)
        except TypedBlocker as error:
            print(json.dumps({"status": "TYPED_BLOCKER", "blocker": error.code}))
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    result = run_gate_a(output_root=args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "READY_FOR_GATE_B" else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "COHORT_AUTHORITY_FILE_SHA256",
    "COHORT_MANIFEST_FILE_SHA256",
    "EXECUTED_COHORT_MANIFEST_SHA256",
    "FINAL_TEST_V2_ROOT",
    "GATE_A_PREFLIGHT_PATH",
    "GATE_B_RELEASE_PATH",
    "F_CONTINUITY_SCALE_CANONICAL_LF_SHA256",
    "F_CONTINUITY_SCALE_DECLARED_WORKTREE_SHA256",
    "HISTORICAL_FINAL_TEST_ACCESS_TOTAL",
    "TRAIN_SUPPORT_SUMMARY_CANONICAL_LF_SHA256",
    "TRAIN_SUPPORT_SUMMARY_DECLARED_WORKTREE_SHA256",
    "NOMINAL_TURNAROUND_Q20",
    "NOMINAL_U_MAX",
    "PHASE7_ACCESS_INCREMENT",
    "Q_GRID",
    "R2_REGISTRY_ARTIFACT_HASH",
    "R2_REGISTRY_FILE_SHA256",
    "R2_TAG_OBJECT",
    "R2_TAG_TARGET_COMMIT",
    "RELEASE_FIELDS",
    "SELECTED_EPISODE_HASH",
    "TypedBlocker",
    "build_gate_a_preflight",
    "execute_gate_b",
    "make_release",
    "mark_access_read_completed",
    "mark_access_read_started",
    "open_access_epoch",
    "run_dry_run",
    "run_gate_a",
    "validate_cohort_reference",
    "validate_instruction_copies",
    "validate_r2_authority",
    "validate_release_schema",
]
