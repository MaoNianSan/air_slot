from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import pyarrow.parquet as pq
except ModuleNotFoundError:
    pq = None

from .artifacts import (
    CORE_REQUIRED_ARTIFACT_IDS,
    validate_registry,
    write_artifact_registry,
)
from .config import RunConfig
from .failures import FormalRunBlocked
from .input import FORMAL_TARGET_COLUMN, FORMAL_TARGET_CONTRACT_VERSION
from .pipeline_checkpoint import assert_fast_acceptance, latest_run, requires_fast_acceptance
from .pipeline_data import resolve_pre_output
from .report import (
    generate_report,
    publication_required_files,
    publish_report,
    validate_publication,
)
from .utils import write_json


def rerun_report(cfg: RunConfig, run_id_value: str | None = None) -> Path:
    run_directory = (
        cfg.root / "output" / "runs" / run_id_value
        if run_id_value
        else latest_run(cfg, "full")
    )
    manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
    generate_report(run_directory, manifest)
    return run_directory


def _is_engineering_dev_summary(summary: dict[str, Any]) -> bool:
    return (
        summary.get("run_purpose") == "three_change_engineering_validation"
        and summary.get("publication_allowed") is False
        and summary.get("formal_baseline_replaced") is False
    )


def validate_mode(
    cfg: RunConfig,
    mode: str,
    *,
    pre_output: Path | None = None,
    override_fast_gate: bool = False,
) -> dict[str, Any]:
    m1_config = cfg.scientific.get("m1", {})
    if "target_candidates" in m1_config or m1_config.get("formal_target") != FORMAL_TARGET_COLUMN:
        raise FormalRunBlocked("FORMAL_TARGET_CONFIG_INVALID")
    if requires_fast_acceptance(
        cfg.mode_name, cfg.profile_contract, override_fast_gate=override_fast_gate
    ):
        assert_fast_acceptance(cfg.root)
    pre_root = resolve_pre_output(cfg, pre_output)
    required = [
        "episodes.parquet", "snapshots.parquet", "calibration.parquet",
        "rules.parquet", "evidence_audit.parquet", "run_summary.json",
    ]
    missing = [str(pre_root / name) for name in required if not (pre_root / name).exists()]
    if missing:
        raise FormalRunBlocked("PRE_CONTRACT_MISSING:" + ",".join(missing))
    if pq is None:
        raise FormalRunBlocked("PYARROW_REQUIRED_FOR_PRE_VALIDATION")
    schemas = {}
    for name in required[:-1]:
        parquet = pq.ParquetFile(pre_root / name)
        schemas[name] = {
            "rows": parquet.metadata.num_rows,
            "columns": parquet.schema_arrow.names,
        }
    pre_summary = json.loads((pre_root / "run_summary.json").read_text(encoding="utf-8"))
    if pre_summary.get("formal_target_column") != FORMAL_TARGET_COLUMN:
        raise FormalRunBlocked("PRE_FORMAL_TARGET_INVALID")
    if pre_summary.get("formal_target_contract_version") != FORMAL_TARGET_CONTRACT_VERSION:
        raise FormalRunBlocked("PRE_FORMAL_TARGET_CONTRACT_VERSION_INVALID")
    if not pre_summary.get("formal_target_definition_hash"):
        raise FormalRunBlocked("PRE_FORMAL_TARGET_DEFINITION_HASH_MISSING")
    if mode == "fast" and not pre_summary.get("downstream_fast_ready", False):
        raise FormalRunBlocked("PRE_FAST_NOT_READY")
    published = cfg.root / "output" / mode
    publication_status: dict[str, Any] | None = None
    if (published / "run_summary.json").exists():
        published_summary = json.loads((published / "run_summary.json").read_text(encoding="utf-8"))
        published_registry = json.loads((published / "artifact_registry.json").read_text(encoding="utf-8"))
        for source, metadata in (("SUMMARY", published_summary), ("REGISTRY", published_registry)):
            if metadata.get("formal_target_column") != FORMAL_TARGET_COLUMN:
                raise FormalRunBlocked(f"OVERALL_RUN_{source}_FORMAL_TARGET_INVALID")
            if metadata.get("label_identity_mismatch_count") != 0:
                raise FormalRunBlocked(f"OVERALL_RUN_{source}_LABEL_IDENTITY_MISMATCH")
        model_contract = json.loads((published / "model_contract.json").read_text(encoding="utf-8"))
        if not all(model_contract.get(key) for key in (
            "formal_target_definition_hash", "training_label_hash", "validation_label_hash",
            "test_label_hash", "model_parameter_hash", "feature_schema_hash",
        )):
            raise FormalRunBlocked("MODEL_TARGET_METADATA_INCOMPLETE")
        if published_summary.get("config_hash") != cfg.config_hash:
            raise FormalRunBlocked("OVERALL_RUN_PUBLISHED_CONFIG_HASH_MISMATCH")
        if _is_engineering_dev_summary(published_summary):
            try:
                validate_registry(
                    published,
                    expected_config_hash=cfg.config_hash,
                    expected_implementation_hash=str(
                        published_summary["implementation_hash"]
                    ),
                    expected_contract_version=cfg.contract_version,
                    allowed_scientific_statuses={"PASS", "STOP_AND_REVIEW"},
                    expected_registry_kind="core",
                    required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
                )
            except (FileNotFoundError, KeyError, ValueError) as exc:
                raise FormalRunBlocked(str(exc)) from exc
            publication_status = {
                "status": "NOT_ALLOWED",
                "engineering_core_registry_status": "PASS",
                "publication_allowed": False,
                "current_implementation_matches_run": (
                    published_summary.get("implementation_hash")
                    == cfg.implementation_hash
                ),
            }
        else:
            if published_summary.get("publication_status") != "PASS":
                raise FormalRunBlocked("OVERALL_RUN_PUBLICATION_NOT_PASS")
            try:
                publication_status = validate_publication(
                    published,
                    expected_run_id=str(published_summary["run_id"]),
                    expected_config_hash=cfg.config_hash,
                    expected_scientific_status=str(published_summary["scientific_status"]),
                    expected_publication_implementation_hash=cfg.implementation_hash,
                )
            except (FileNotFoundError, KeyError, ValueError) as exc:
                raise FormalRunBlocked(str(exc)) from exc
    return {
        "engineering_status": "PASS",
        "mode": mode,
        "config_hash": cfg.config_hash,
        "implementation_hash": cfg.implementation_hash,
        "contract_version": cfg.contract_version,
        "pre_output": str(pre_root),
        "pre_run_id": pre_summary.get("run_id"),
        "schemas": schemas,
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "overall_run_publication_status": publication_status["status"] if publication_status else "NOT_PUBLISHED",
        "engineering_core_registry_status": (
            publication_status.get("engineering_core_registry_status", "NOT_APPLICABLE")
            if publication_status else "NOT_PUBLISHED"
        ),
        "publication": publication_status,
    }


def report_mode(cfg: RunConfig, mode: str) -> dict[str, Any]:
    root = cfg.root / "output" / mode
    summary_path = root / "run_summary.json"
    if not summary_path.exists():
        raise FormalRunBlocked(f"RUN_SUMMARY_MISSING:{summary_path}")
    manifest_path = root / "run_manifest.json"
    registry_path = root / "artifact_registry.json"
    if not manifest_path.exists() or not registry_path.exists():
        raise FormalRunBlocked("PUBLICATION_UPSTREAM_METADATA_MISSING")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if summary.get("config_hash") != cfg.config_hash or manifest.get("config_hash") != cfg.config_hash:
        raise FormalRunBlocked("PUBLICATION_CONFIG_HASH_MISMATCH")
    scientific_status = str(summary.get("scientific_status"))
    if scientific_status != "STOP_AND_REVIEW" or summary.get("full_recommended") is not False:
        raise FormalRunBlocked("PUBLICATION_SCIENTIFIC_BOUNDARY_MISMATCH")
    scientific_implementation_hash = str(summary.get("implementation_hash"))
    publication = publish_report(
        root,
        manifest={**manifest, "scientific_status": scientific_status},
        scientific=cfg.scientific,
        publication_implementation_hash=cfg.implementation_hash,
    )
    summary.update({
        "publication_status": "PASS",
        "scientific_implementation_hash": scientific_implementation_hash,
        "publication_implementation_hash": cfg.implementation_hash,
        "publication_source_policy": "FROZEN_ARTIFACTS_ONLY",
        "five_figure_triplets_status": "PASS",
        "scientific_status": "STOP_AND_REVIEW",
        "full_recommended": False,
    })
    write_json(summary_path, summary)
    artifact_names = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.name != "artifact_registry.json"
        and not path.name.endswith(".tmp")
    )
    metadata = {
        key: value
        for key, value in existing_registry.items()
        if key in {
            "formal_target_column", "formal_target_contract_version",
            "formal_target_definition_hash", "sensitivity_target_column",
            "training_label_hash", "validation_label_hash", "test_label_hash",
            "model_parameter_hash", "feature_schema_hash", "quantile_grid_hash",
            "m2_unit_scales", "m3_parameter_hash", "m3_sample_hash",
            "label_identity_mismatch_count", "observed_outcome_source",
        }
    }
    metadata.update({
        "scientific_implementation_hash": scientific_implementation_hash,
        "publication_implementation_hash": cfg.implementation_hash,
        "publication_status": "PASS",
        "five_figure_triplets_status": "PASS",
        "scientific_values_modified": False,
    })
    write_artifact_registry(
        root,
        mode=mode,
        run_id=str(summary["run_id"]),
        config_hash=cfg.config_hash,
        implementation_hash=scientific_implementation_hash,
        contract_version=str(summary["contract_version"]),
        upstream_artifact_hashes=dict(existing_registry.get("upstream_artifact_hashes", {})),
        scientific_status="STOP_AND_REVIEW",
        artifact_names=artifact_names,
        registry_kind="publication",
        required_artifact_ids=sorted(
            set(CORE_REQUIRED_ARTIFACT_IDS) | set(publication_required_files())
        ),
        metadata=metadata,
    )
    validation = validate_publication(
        root,
        expected_run_id=str(summary["run_id"]),
        expected_config_hash=cfg.config_hash,
        expected_scientific_status="STOP_AND_REVIEW",
        expected_publication_implementation_hash=cfg.implementation_hash,
    )
    return {
        "overall_run_publication_status": "PASS",
        "overall_run_scientific_status": "STOP_AND_REVIEW",
        "full_recommended": False,
        "run_id": summary["run_id"],
        "config_hash": cfg.config_hash,
        "scientific_implementation_hash": scientific_implementation_hash,
        "publication_implementation_hash": cfg.implementation_hash,
        "source_hash_count": len(publication["source_hashes"]),
        **validation,
    }
