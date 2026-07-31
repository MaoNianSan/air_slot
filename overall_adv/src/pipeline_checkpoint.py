from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .pipeline_common import (
    CHECKPOINT_SCHEMA_VERSION,
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    ROOT,
    _write_df,
    _write_json,
    sha256_file,
    stable_hash,
)


def _checkpoint_identity(cfg: dict[str, Any], upstream: dict[str, Any]) -> dict[str, str]:
    return {
        "input_hash": stable_hash(
            {
                "overall_run_registry": upstream["overall_run_registry_hash"],
                "common_support_cohort": upstream["common_support_cohort_hash"],
            }
        ),
        "config_hash": cfg["config_hash"],
        "implementation_hash": sha256_file(Path(__file__)),
        "mode": cfg["mode"],
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": upstream["formal_target_definition_hash"],
    }


def _policy_paths(output: Path, policy_id: str) -> tuple[Path, Path]:
    root = output / "checkpoints"
    return root / f"{policy_id}.json", root / f"{policy_id}_decisions.parquet"


def _load_policy_checkpoint(
    output: Path,
    policy_id: str,
    identity: dict[str, str],
    required_outputs: list[Path],
) -> pd.DataFrame | None:
    metadata_path, decisions_path = _policy_paths(output, policy_id)
    if not metadata_path.exists():
        unexpected = [path for path in [decisions_path, *required_outputs] if path.exists()]
        if unexpected:
            raise ValueError("MIXED_OUTPUT_UNCHECKPOINTED:" + ",".join(str(path) for path in unexpected))
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = {
        **identity,
        "checkpoint_schema": CHECKPOINT_SCHEMA_VERSION,
        "stage": policy_id,
        "model_id": policy_id,
    }
    mismatched = [key for key, value in expected.items() if metadata.get(key) != value]
    if mismatched:
        raise ValueError(f"CHECKPOINT_HASH_MISMATCH:{policy_id}:" + ",".join(mismatched))
    for item in metadata.get("outputs", []):
        path = output / item["relative_path"]
        if not path.exists() or sha256_file(path) != item["sha256"]:
            raise ValueError(f"CHECKPOINT_OUTPUT_HASH_MISMATCH:{policy_id}:{path}")
    declared = {item["relative_path"] for item in metadata.get("outputs", [])}
    expected_outputs = {path.relative_to(output).as_posix() for path in [decisions_path, *required_outputs]}
    if declared != expected_outputs:
        raise ValueError(f"CHECKPOINT_OUTPUT_SET_MISMATCH:{policy_id}")
    return pd.read_parquet(decisions_path)


def _write_policy_checkpoint(
    output: Path,
    policy_id: str,
    decisions: pd.DataFrame,
    identity: dict[str, str],
    required_outputs: list[Path],
) -> Path:
    metadata_path, decisions_path = _policy_paths(output, policy_id)
    _write_df(decisions, decisions_path)
    paths = [decisions_path, *required_outputs]
    output_records = [
        {"relative_path": path.relative_to(output).as_posix(), "sha256": sha256_file(path)}
        for path in paths
    ]
    _write_json(
        {
            **identity,
            "checkpoint_schema": CHECKPOINT_SCHEMA_VERSION,
            "stage": policy_id,
            "model_id": policy_id,
            "outputs": output_records,
            "output_hash": stable_hash(output_records),
            "completed_at": pd.Timestamp.now(tz="UTC"),
        },
        metadata_path,
    )
    return metadata_path


