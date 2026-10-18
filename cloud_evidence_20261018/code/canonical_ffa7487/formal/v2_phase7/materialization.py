"""Safe materialization, hashing, and Git helpers for Phase 7."""

from __future__ import annotations

import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from model.common.identity import content_id

from .constants import LEGACY_FINAL_TEST_ROOT, ROOT
from .errors import TypedBlocker, _require


def _file_sha256(path: Path) -> str:
    data = Path(path).read_bytes()
    return "sha256:" + sha256(data).hexdigest()


def _canonical_text_sha256(path: Path) -> str:
    """Hash text content after normalizing CRLF to LF."""

    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return "sha256:" + sha256(data).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return content_id(body)


def _assert_not_legacy_final_test(path: Path) -> None:
    resolved = Path(path).resolve()
    forbidden = LEGACY_FINAL_TEST_ROOT.resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        raise TypedBlocker(
            "LEGACY_FINAL_TEST_TREE_ACCESS_FORBIDDEN",
            str(resolved),
        )


def _read_json(path: Path) -> dict[str, Any]:
    target = Path(path)
    _assert_not_legacy_final_test(target)
    return json.loads(target.read_text(encoding="utf-8"))


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


__all__ = [
    "_assert_not_legacy_final_test",
    "_canonical_text_sha256",
    "_file_sha256",
    "_git",
    "_payload_sha256",
    "_read_json",
    "_require_canonical_text_hash",
    "_require_file_hash",
    "_sha256_bytes",
    "_write_json_atomic",
]
