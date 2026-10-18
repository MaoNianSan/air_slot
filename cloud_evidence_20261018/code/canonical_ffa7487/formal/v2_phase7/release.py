"""Gate-B release schema construction and validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from . import constants as C
from .authority import _instruction_sha256
from .errors import TypedBlocker, _require
from .materialization import _sha256_bytes


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
        C.INSTRUCTION_REPO_PATH.read_bytes()
    )
    return {
        "gate_a_commit": gate_a_commit,
        "instruction_sha256": instruction_hash,
        "freeze_tag_object": C.R2_TAG_OBJECT,
        "freeze_tag_target_commit": C.R2_TAG_TARGET_COMMIT,
        "cohort_authority_sha256": C.COHORT_AUTHORITY_FILE_SHA256,
        "cohort_manifest_sha256": C.EXECUTED_COHORT_MANIFEST_SHA256,
        "human_approved": True,
        "human_approval_timestamp": human_approval_timestamp,
    }


def validate_release_schema(release: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact Gate-B human-release schema."""

    keys = set(release)
    _require(
        keys == set(C.RELEASE_FIELDS),
        "GATE_B_RELEASE_SCHEMA_MISMATCH",
        sorted(keys),
    )
    _require(
        isinstance(release["gate_a_commit"], str)
        and (
            release["gate_a_commit"] == "RESOLVED_AFTER_GATE_A_COMMIT"
            or bool(C.COMMIT_RE.fullmatch(release["gate_a_commit"]))
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
            and bool(C.SHA256_RE.fullmatch(release[field])),
            "GATE_B_RELEASE_HASH_FIELD_INVALID",
            field,
        )
    _require(
        release["freeze_tag_object"] == C.R2_TAG_OBJECT,
        "GATE_B_RELEASE_FREEZE_TAG_OBJECT_MISMATCH",
        release["freeze_tag_object"],
    )
    _require(
        release["freeze_tag_target_commit"] == C.R2_TAG_TARGET_COMMIT,
        "GATE_B_RELEASE_FREEZE_TAG_TARGET_MISMATCH",
        release["freeze_tag_target_commit"],
    )
    _require(
        release["cohort_authority_sha256"] == C.COHORT_AUTHORITY_FILE_SHA256,
        "GATE_B_RELEASE_COHORT_AUTHORITY_MISMATCH",
        release["cohort_authority_sha256"],
    )
    _require(
        release["cohort_manifest_sha256"] == C.EXECUTED_COHORT_MANIFEST_SHA256,
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
        "schema_fields": list(C.RELEASE_FIELDS),
        "human_approved": True,
        "freeze_tag_object": release["freeze_tag_object"],
        "freeze_tag_target_commit": release["freeze_tag_target_commit"],
    }


__all__ = [
    "_json_iso",
    "make_release",
    "validate_release_schema",
]
