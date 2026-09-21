"""Shared Freeze R2 paths and hash helpers."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from model.common.identity import content_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_TAG = "v2-scientific-freeze"
R2_TAG = "v2-scientific-freeze-r2"
BASE_REGISTRY_PATH = PROJECT_ROOT / "registries" / "v2_scientific_freeze.json"
R2_REGISTRY_PATH = PROJECT_ROOT / "registries" / "v2_scientific_freeze_r2.json"
REPORT_PATH = (
    PROJECT_ROOT / "docs" / "V2_SCIENTIFIC_FREEZE_R2_CORRECTION_REPORT.md"
)
RECONCILIATION_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase6_r2"
    / "R2_AUTHORITY_RECONCILIATION.json"
)
FINAL_TEST_ROOT = PROJECT_ROOT / "artifacts" / "experiment" / "final_test"


class R2Error(RuntimeError):
    """Raised when the R2 authority contract cannot be satisfied."""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    target = assert_not_final_test(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode(
            "utf-8"
        )
    )
    temporary.replace(target)
    return target


def file_hash(path: Path) -> str:
    return f"sha256:{sha256(Path(path).read_bytes()).hexdigest()}"


def canonical_text_file_hash(path: Path) -> str:
    """Hash canonical LF text bytes independent of checkout line endings."""

    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return f"sha256:{sha256(data).hexdigest()}"


def payload_hash(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return content_id(body)


def relative_path(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()


def assert_not_final_test(path: Path) -> Path:
    """Reject any explicit old Final-Test result-tree path."""

    resolved = Path(path).resolve()
    forbidden = FINAL_TEST_ROOT.resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        raise R2Error(f"R2_FINAL_TEST_PATH_FORBIDDEN:{resolved}")
    return resolved


def git_text(relative: str, *, ref: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def git_json(relative: str, *, ref: str) -> dict[str, Any]:
    return json.loads(git_text(relative, ref=ref))


__all__ = [
    "BASE_REGISTRY_PATH",
    "BASE_TAG",
    "FINAL_TEST_ROOT",
    "PROJECT_ROOT",
    "R2_REGISTRY_PATH",
    "R2_TAG",
    "RECONCILIATION_PATH",
    "REPORT_PATH",
    "R2Error",
    "assert_not_final_test",
    "file_hash",
    "git_json",
    "git_text",
    "payload_hash",
    "read_json",
    "relative_path",
    "write_json",
]
