from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .build_context import CoreBuildResult, create_build_context
from .build_stages import (
    events_and_chains,
    inventory,
    membership,
    observations,
    publication,
    references_and_evidence,
    requests_and_resume_identity,
    validation,
)
from .contracts import core_output_root
from .validation import validate_existing_bundle


BUILD_STAGES = (
    inventory,
    events_and_chains,
    requests_and_resume_identity,
    observations,
    membership,
    references_and_evidence,
    validation,
    publication,
)


def build_core(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> CoreBuildResult:
    context = create_build_context(cfg, output_override)
    for stage in BUILD_STAGES:
        stage(context)
    return CoreBuildResult(
        context.output,
        context.manifest,
        context.validation,
        context.readiness,
        context.publication_status,
    )


def _read_existing(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = core_output_root(cfg, output_override)
    manifest = json.loads((root / "pre_manifest.json").read_text(encoding="utf-8"))
    validation_result = json.loads(
        (root / "reports" / "core_validation.json").read_text(encoding="utf-8")
    )
    readiness = json.loads(
        (root / "reports" / "core_readiness.json").read_text(encoding="utf-8")
    )
    return root, manifest, validation_result, readiness


def core_validate_existing(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> dict[str, Any]:
    root = core_output_root(cfg, output_override)
    result = validate_existing_bundle(root, cfg, write_report=True)
    manifest_path = root / "pre_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = {
            "manifest_core_data_hash": manifest.get("core_data_hash"),
            **result,
        }
    return result


def core_readiness_existing(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> dict[str, Any]:
    return _read_existing(cfg, output_override)[3]


def core_report_existing(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> str:
    root = _read_existing(cfg, output_override)[0]
    return (root / "reports" / "PRE_CORE_RUN_REPORT.md").read_text(
        encoding="utf-8"
    )
