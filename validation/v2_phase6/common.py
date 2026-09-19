"""Shared Phase 6 freeze constants and hash helpers.

Phase 6 activates the scientific freeze only. Nothing in this package reads or
writes ``artifacts/experiment/final_test``.
"""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from model.common.identity import content_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASELINE_COMMIT = "2d74af9ee5a1cb5db59e0e94fac83f2aa608db01"
BASELINE_TREE = "4bb3257666421c46e18bd17703c11d2a78d347d2"
ACTIVATION_TAG = "v2-scientific-freeze"
FREEZE_COMMIT_SEMANTICS = (
    "PRE_FREEZE_SCIENTIFIC_BASELINE_NOT_ACTIVATION_COMMIT"
)

DRAFT_PATH = PROJECT_ROOT / "registries" / "v2_scientific_freeze_draft.json"
ACTIVE_PATH = PROJECT_ROOT / "registries" / "v2_scientific_freeze.json"
REPORT_PATH = PROJECT_ROOT / "docs" / "V2_PHASE6_FREEZE_REPORT.md"
VALIDATION_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase6"
    / "FREEZE_LINEAGE_HASH_VALIDATION.json"
)

TRAIN_SUPPORT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase5_development"
    / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"
)
TRAIN_SAMPLES_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase5_development"
    / "TRAIN_TURNAROUND_HEADROOM_SAMPLES.npz"
)
M2_TURNAROUND_REFERENCE_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_v2_data_gate_a2"
    / "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
)
F_CONTINUITY_SCALE_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_freeze_precheck"
    / "M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json"
)
CU_REGISTRY_V5_PATH = PROJECT_ROOT / "registries" / "m2_data2_formal_cu_v5.json"
SUPERSESSION_V3_PATH = (
    PROJECT_ROOT / "registries" / "passenger_reference_supersession_v3.json"
)
FINAL_TEST_ROOT = PROJECT_ROOT / "artifacts" / "experiment" / "final_test"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    target = assert_not_final_test(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def file_hash(path: Path) -> str:
    return f"sha256:{sha256(Path(path).read_bytes()).hexdigest()}"


def payload_hash(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return content_id(body)


def assert_payload_hash(payload: Mapping[str, Any], label: str) -> str:
    declared = payload.get("artifact_hash")
    computed = payload_hash(payload)
    if declared != computed:
        raise ValueError(f"{label}_ARTIFACT_HASH_MISMATCH:{declared}:{computed}")
    return computed


def relative_path(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()


def assert_not_final_test(path: Path) -> Path:
    """Reject an explicit Final-Test path without enumerating that directory."""

    resolved = Path(path).resolve()
    forbidden = FINAL_TEST_ROOT.resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        raise ValueError(f"PHASE6_FINAL_TEST_PATH_FORBIDDEN:{resolved}")
    return resolved


def git_bytes(path: Path, *, commit: str = BASELINE_COMMIT) -> bytes:
    relative = relative_path(path)
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def git_text(path: Path, *, commit: str = BASELINE_COMMIT) -> str:
    return git_bytes(path, commit=commit).decode("utf-8")


def git_json(path: Path, *, commit: str = BASELINE_COMMIT) -> dict[str, Any]:
    return json.loads(git_text(path, commit=commit))


__all__ = [
    "ACTIVATION_TAG",
    "ACTIVE_PATH",
    "BASELINE_COMMIT",
    "BASELINE_TREE",
    "CU_REGISTRY_V5_PATH",
    "DRAFT_PATH",
    "FINAL_TEST_ROOT",
    "FREEZE_COMMIT_SEMANTICS",
    "F_CONTINUITY_SCALE_PATH",
    "M2_TURNAROUND_REFERENCE_PATH",
    "PROJECT_ROOT",
    "REPORT_PATH",
    "SUPERSESSION_V3_PATH",
    "TRAIN_SAMPLES_PATH",
    "TRAIN_SUPPORT_PATH",
    "VALIDATION_PATH",
    "assert_not_final_test",
    "assert_payload_hash",
    "file_hash",
    "git_bytes",
    "git_json",
    "git_text",
    "payload_hash",
    "read_json",
    "relative_path",
    "write_json",
]
