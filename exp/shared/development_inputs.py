"""Validated Development input boundary shared by Exp1-Exp4."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from model.common.paths import PROJECT_ROOT

SHARED_OUTPUT = PROJECT_ROOT / "artifacts" / "experiment" / "shared" / "development"
EXP2_ROOT = PROJECT_ROOT / "artifacts" / "experiment" / "exp2" / "development"
NODE_SOURCE = EXP2_ROOT / "data" / "EXP2_H16_M2_V4_NODE_INPUT.parquet"
SCENARIO_SOURCE = EXP2_ROOT / "data" / "EXP2_COMMON_SUPPORT.parquet"
MANIFEST_SOURCE = EXP2_ROOT / "contract" / "EXP2_DEVELOPMENT_INPUT_MANIFEST.json"


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _require(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise RuntimeError(f"BLOCK_SHARED_INPUT_MISSING_COLUMNS:{label}:{missing}")


def _validate(nodes: pd.DataFrame, scenarios: pd.DataFrame, source: dict[str, Any]) -> dict[str, Any]:
    _require(nodes, ("episode_id", "decision_node_id", "decision_time", "information_cutoff", "operational_stage"), "nodes")
    _require(scenarios, ("episode_id", "decision_node_id", "scenario_id", "scenario_weight", "D_TO", "D_TO_support"), "scenarios")
    if source.get("status") != "PASS":
        raise RuntimeError("BLOCK_SHARED_INPUT_SOURCE_MANIFEST_NOT_PASS")
    if source.get("final_test_access_count") != 0 or source.get("paper_result") is not False:
        raise RuntimeError("BLOCK_SHARED_INPUT_SOURCE_GUARD_FAILED")
    node_keys = list(zip(nodes.episode_id, nodes.decision_node_id))
    if len(node_keys) != len(set(node_keys)):
        raise RuntimeError("BLOCK_SHARED_INPUT_DUPLICATE_NODE")
    scenario_keys = list(zip(scenarios.episode_id, scenarios.decision_node_id, scenarios.scenario_id))
    if len(scenario_keys) != len(set(scenario_keys)):
        raise RuntimeError("BLOCK_SHARED_INPUT_DUPLICATE_SCENARIO")
    grouped = scenarios.groupby(["episode_id", "decision_node_id"], sort=False)
    if not grouped["scenario_weight"].sum().between(1 - 1e-6, 1 + 1e-6).all():
        raise RuntimeError("BLOCK_SHARED_INPUT_WEIGHTS_NOT_NORMALIZED")
    if (scenarios["scenario_weight"] <= 0).any():
        raise RuntimeError("BLOCK_SHARED_INPUT_WEIGHT_NOT_POSITIVE")
    if (scenarios["D_TO_support"] == "ABSTAIN").any():
        raise RuntimeError("BLOCK_SHARED_INPUT_DELAY_UNSUPPORTED")
    if not set(zip(scenarios.episode_id, scenarios.decision_node_id)).issubset(set(node_keys)):
        raise RuntimeError("BLOCK_SHARED_INPUT_ORPHAN_SCENARIO")
    return {
        "node_count": len(nodes),
        "episode_count": int(nodes.episode_id.nunique()),
        "scenario_row_count": len(scenarios),
        "scenario_counts_per_node": sorted(int(x) for x in grouped.size().unique()),
        "operational_stages": sorted(nodes.operational_stage.dropna().astype(str).unique()),
    }


def _normalize_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    nodes = nodes.copy()
    if "original_episode_id" not in nodes:
        nodes["original_episode_id"] = nodes["episode_id"]
    if "operating_stage" not in nodes:
        nodes["operating_stage"] = nodes["operational_stage"]
    nodes["decision_time"] = pd.to_datetime(nodes["decision_time"], utc=True)
    nodes["information_cutoff"] = pd.to_datetime(nodes["information_cutoff"], utc=True)
    nodes = nodes.sort_values(
        ["original_episode_id", "decision_time", "decision_node_id"],
        kind="mergesort",
    ).reset_index(drop=True)
    nodes["node_order_within_episode"] = nodes.groupby(
        "original_episode_id", sort=False
    ).cumcount()
    nodes["split"] = "development"
    return nodes


def _normalize_scenarios(scenarios: pd.DataFrame) -> pd.DataFrame:
    scenarios = scenarios.copy()
    scenarios["scenario_support_state"] = scenarios["D_TO_support"]
    scenarios["scenario_weight"] = pd.to_numeric(
        scenarios["scenario_weight"], errors="raise"
    )
    return scenarios


def publish_from_exp2_materialization(
    *,
    output_root: Path = SHARED_OUTPUT,
    node_source: Path = NODE_SOURCE,
    scenario_source: Path = SCENARIO_SOURCE,
    manifest_source: Path = MANIFEST_SOURCE,
) -> dict[str, Any]:
    """Publish shared inputs from an existing Exp2 Development materialization."""
    missing = [str(path) for path in (node_source, scenario_source, manifest_source) if not path.is_file()]
    if missing:
        return {"status": "BLOCKED", "reason": "BLOCK_SHARED_INPUT_SOURCE_MISSING", "missing": missing, "final_test_access_count": 0, "paper_result": False}
    source = json.loads(manifest_source.read_text(encoding="utf-8"))
    nodes = _normalize_nodes(pd.read_parquet(node_source))
    scenarios = _normalize_scenarios(pd.read_parquet(scenario_source))
    counts = _validate(nodes, scenarios, source)
    output_root.mkdir(parents=True, exist_ok=True)
    node_target = output_root / "SHARED_DEVELOPMENT_INPUTS.parquet"
    scenario_target = output_root / "SHARED_SCENARIO_INPUTS.parquet"
    nodes.to_parquet(node_target, index=False)
    scenarios.to_parquet(scenario_target, index=False)
    manifest = {
        "schema_version": "AIR_SLOT_SHARED_DEVELOPMENT_INPUT_MANIFEST_V1",
        "status": "PASS",
        "artifact_scope": "DEVELOPMENT_ONLY_SHARED_INPUT",
        "source_manifest": str(manifest_source),
        "source_manifest_hash": _hash(manifest_source),
        "source_node_hash": _hash(node_source),
        "source_scenario_hash": _hash(scenario_source),
        "node_path": str(node_target),
        "scenario_path": str(scenario_target),
        "node_hash": _hash(node_target),
        "scenario_hash": _hash(scenario_target),
        "m1_checkpoint_hash": source.get("m1_checkpoint_hash"),
        "m1_artifact_hash": source.get("m1_artifact_hash"),
        "development_cohort_hash": source.get("development_cohort_hash"),
        "m2_registry_id": source.get("m2_registry_id"),
        "m2_registry_hash": source.get("m2_registry_hash"),
        "counts": counts,
        "final_test_access_count": 0,
        "paper_result": False,
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
    }
    manifest["manifest_hash"] = f"sha256:{sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}"
    _write_json(output_root / "SHARED_INPUT_MANIFEST.json", manifest)
    _write_json(output_root / "SHARED_SUPPORT_AUDIT.json", {
        "schema_version": "AIR_SLOT_SHARED_SUPPORT_AUDIT_V1",
        "status": "PASS",
        "zero_fill": False,
        "final_test_access_count": 0,
        "paper_result": False,
    })
    return manifest


__all__ = ["publish_from_exp2_materialization"]
