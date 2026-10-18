"""Frozen cohort reference validation."""

from __future__ import annotations

from typing import Any

from . import constants as C
from .errors import _require
from .materialization import (
    _read_json,
    _require_canonical_text_hash,
    _require_file_hash,
    _sha256_bytes,
)


def validate_cohort_reference() -> dict[str, Any]:
    """Validate the frozen pre-access cohort identity without reading Q4 data."""

    _require_file_hash(
        C.COHORT_AUTHORITY_PATH,
        C.COHORT_AUTHORITY_FILE_SHA256,
        "COHORT_AUTHORITY_FILE_HASH",
    )
    _require_canonical_text_hash(
        C.COHORT_MANIFEST_PATH,
        C.COHORT_MANIFEST_FILE_SHA256,
        C.COHORT_MANIFEST_DECLARED_WORKTREE_SHA256,
        "COHORT_MANIFEST_FILE_HASH",
    )
    authority = _read_json(C.COHORT_AUTHORITY_PATH)
    manifest = _read_json(C.COHORT_MANIFEST_PATH)

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
        payload_hash == C.SELECTED_EPISODE_HASH,
        "COHORT_MANIFEST_SELECTED_EPISODE_HASH_MISMATCH",
        payload_hash,
    )
    _require(
        manifest.get("selected_episode_hash") == C.SELECTED_EPISODE_HASH,
        "COHORT_MANIFEST_DECLARED_EPISODE_HASH_MISMATCH",
    )
    _require(
        manifest.get("selection_reused") is True
        and manifest.get("selection_reperformed") is False,
        "COHORT_MANIFEST_SELECTION_REUSE_INVALID",
    )
    _require(
        manifest.get("artifact_manifest_sha256")
        == C.EXECUTED_COHORT_MANIFEST_SHA256,
        "COHORT_MANIFEST_EXECUTED_HASH_MISMATCH",
    )
    return {
        "status": "PASS",
        "authority_path": str(C.COHORT_AUTHORITY_PATH.relative_to(C.ROOT)),
        "authority_file_sha256": C.COHORT_AUTHORITY_FILE_SHA256,
        "manifest_path": str(C.COHORT_MANIFEST_PATH.relative_to(C.ROOT)),
        "manifest_file_sha256": C.COHORT_MANIFEST_FILE_SHA256,
        "executed_manifest_sha256": C.EXECUTED_COHORT_MANIFEST_SHA256,
        "selected_episode_count": len(episode_ids),
        "selected_episode_hash": C.SELECTED_EPISODE_HASH,
        "final_test_cohort_reused": True,
        "final_test_cohort_reselected": False,
        "source_months": [10, 11, 12],
        "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
        "raw_q4_read": False,
    }


__all__ = ["validate_cohort_reference"]
