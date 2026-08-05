from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file
from .build_context import BuildContext
from .contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
    contract_hashes,
    frozen_config_hash,
    frozen_research_config,
    git_metadata,
    implementation_hash,
    schema_hash,
)
from .report import build_run_report
from .writer import (
    publish_staging,
    write_core_metadata,
    write_core_tables,
)


def build_manifest(
    cfg: dict[str, Any],
    raw_inventory: pd.DataFrame,
    registry_hash: str,
    table_hashes: dict[str, str],
    observation_hash: str,
    row_counts: dict[str, int],
    partition_counts: dict[str, Any],
    membership_dataset_hash: str | None = None,
    membership_partition_manifest_hash: str | None = None,
    membership_partition_count: int = 0,
    membership_row_count: int = 0,
    membership_pass_empty_count: int = 0,
    file_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    artifact_hashes = {**table_hashes, "observations": observation_hash}
    if membership_dataset_hash:
        artifact_hashes["observation_membership"] = membership_dataset_hash
    source_records = (
        raw_inventory[["source", "relative_path", "sha256", "size_bytes"]]
        .astype(str)
        .to_dict("records")
    )
    implementation = implementation_hash(cfg.get("project_root"))
    git = git_metadata(cfg.get("project_root"))
    return {
        "contract_id": CONTRACT_ID,
        "schema_version": SCHEMA_VERSION,
        "research_code_revision": RESEARCH_CODE_REVISION,
        "source_manifest_hash": object_hash(source_records),
        "source_schema_hash": object_hash(cfg["sources"]),
        "frozen_config_hash": frozen_config_hash(cfg),
        "column_registry_hash": registry_hash,
        **contract_hashes(cfg),
        "pre_code_hash": implementation["hash"],
        "implementation_hash": implementation["hash"],
        "implementation_hash_status": implementation["status"],
        "implementation_file_count": implementation["file_count"],
        "git_commit": git["git_commit"],
        "git_dirty": git["git_dirty"],
        "created_at": str(pd.Timestamp.now(tz="UTC")),
        "mode": cfg["mode"],
        "row_counts": row_counts,
        "partition_counts": partition_counts,
        "membership_partition_count": membership_partition_count,
        "membership_row_count": membership_row_count,
        "membership_pass_empty_count": membership_pass_empty_count,
        "membership_partition_manifest_hash": membership_partition_manifest_hash,
        "membership_dataset_hash": membership_dataset_hash,
        "artifact_hashes": artifact_hashes,
        "file_hashes": file_hashes or {},
        "core_data_hash": object_hash(artifact_hashes),
        "core_schema_hash": schema_hash(cfg),
    }


def finalize_and_publish(context: BuildContext) -> None:
    assert context.staging is not None
    staging = context.staging
    cfg = context.cfg
    (staging / "frozen_research_config.json").write_text(
        json.dumps(
            frozen_research_config(cfg),
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    table_hashes = write_core_tables(
        staging, context.tables, context.registry, cfg["core_schema"]
    )
    file_hashes = {
        name: sha256_file(staging / f"{name}.parquet")
        for name in context.tables
    }
    file_hashes["column_registry"] = sha256_file(staging / "column_registry.yaml")
    observation_manifest = (
        staging / "observations" / "observation_partition_manifest.json"
    )
    if observation_manifest.exists():
        file_hashes["observation_partition_manifest"] = sha256_file(
            observation_manifest
        )
    membership_manifest = (
        staging
        / "observation_membership"
        / "observation_membership_partition_manifest.json"
    )
    file_hashes["membership_partition_manifest"] = sha256_file(
        membership_manifest
    )
    row_counts = {name: len(frame) for name, frame in context.tables.items()}
    row_counts["observations"] = sum(context.observation_result.row_counts.values())
    row_counts["observation_membership"] = context.membership_result.row_count
    context.manifest = build_manifest(
        cfg,
        context.raw_inventory,
        table_hashes["column_registry"],
        table_hashes,
        context.observation_result.content_hash,
        row_counts,
        {
            "observations": context.observation_result.partition_counts,
            "observation_membership": context.membership_result.partition_count,
        },
        context.membership_result.dataset_hash,
        context.membership_result.partition_manifest_hash,
        context.membership_result.partition_count,
        context.membership_result.row_count,
        context.membership_result.pass_empty_count,
        file_hashes,
    )
    report = build_run_report(
        context.manifest,
        context.validation,
        context.readiness,
        context.cache_manifest,
    )
    write_core_metadata(
        staging,
        context.manifest,
        context.validation,
        context.readiness,
        context.cache_manifest,
        context.extraction,
        report,
    )
    context.publication_status = publish_staging(
        staging, context.output, context.manifest["core_data_hash"]
    )
