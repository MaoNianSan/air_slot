from __future__ import annotations

import importlib.metadata
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .input import object_hash
from .progress import normalize_progress_level
from .shared_contracts import strict_deep_merge, v3_pre_action_contract
from .target_contract import FORMAL_TARGET_COLUMN, SENSITIVITY_TARGET_COLUMN


@dataclass
class BuildResult:
    output_root: Path
    validation: dict[str, Any]
    readiness: dict[str, Any]
    manifest: dict[str, Any]


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"CONFIG_TOP_LEVEL_NOT_MAPPING={path}")
    return payload


def _load_schema(config_dir: Path) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    schema_dir = config_dir / "schema"
    sections = {
        "legacy_tables.yaml": ["tables", "consumers"],
        "column_roles.yaml": ["m1_required_inputs", "evidence_completeness_features"],
        "column_aliases.yaml": ["aliases"],
    }
    for name, allowed in sections.items():
        payload = _read_yaml(schema_dir / name)
        payload = {key: payload[key] for key in allowed if key in payload}
        overlap = sorted(set(schema) & set(payload))
        if overlap:
            raise ValueError("SCHEMA_SECTION_DUPLICATE=" + ",".join(overlap))
        schema.update(payload)
    return schema


def _load_core_schema(config_dir: Path) -> dict[str, Any]:
    schema_dir = config_dir / "schema"
    core = _read_yaml(schema_dir / "core_tables.yaml")
    roles = _read_yaml(schema_dir / "column_roles.yaml")
    aliases = _read_yaml(schema_dir / "column_aliases.yaml")
    core["role_definitions"] = roles.get("role_definitions", [])
    core["column_roles"] = roles.get("core_column_roles", {})
    core["column_aliases"] = aliases.get("core_aliases", {})
    core["forbidden_aliases"] = aliases.get("forbidden_aliases", [])
    return core


def _stable_config_value(value: Any, key: str = "") -> Any:
    volatile = {
        "progress_level", "terminal_formatting", "terminal_format", "pid",
        "process_id", "created_at", "temporary_staging_path", "staging_path",
        "runtime_progress", "progress", "runtime_random", "random_seed_runtime",
        "state_workers", "n_jobs", "requested_n_jobs", "outer_workers",
        "inner_threads", "parallel_backend", "task_seed_hash",
    }
    if key in volatile or key.lower() in volatile:
        return None
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for name, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            cleaned = _stable_config_value(item, str(name))
            if cleaned is not None:
                output[str(name)] = cleaned
        return output
    if isinstance(value, (list, tuple)):
        return [_stable_config_value(item, key) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def load_config(
    override_path: str | Path | None = None,
    *,
    mode: str = "full",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    config_dir = project_root / "config"
    config = _read_yaml(config_dir / "default.yaml")
    config["sources"] = _read_yaml(config_dir / "sources.yaml")["sources"]
    config["schema"] = _load_schema(config_dir)
    config["core_schema"] = _load_core_schema(config_dir)
    config["actions"] = {
        **_read_yaml(config_dir / "actions.yaml"),
        **v3_pre_action_contract(),
    }
    config["predecessor_matching"] = _read_yaml(
        config_dir / "predecessor_matching.yaml"
    )
    mode_path = config_dir / f"{mode}.yaml"
    if mode_path.exists():
        config = strict_deep_merge(config, _read_yaml(mode_path))
    if override_path:
        override = Path(override_path)
        if not override.is_absolute():
            cwd_candidate = (Path.cwd() / override).resolve()
            override = cwd_candidate if cwd_candidate.exists() else (project_root / override).resolve()
        config = strict_deep_merge(config, _read_yaml(override))
    if output_dir is not None:
        config["paths"]["output_root"] = str(output_dir)
        config["paths"]["intermediate_root"] = str(Path(output_dir) / "intermediate")
    config["mode"] = mode
    config["project_root"] = project_root
    data_root = Path(config["paths"]["data_root"])
    output_root = Path(config["paths"].get("output_root", f"output/{mode}"))
    intermediate_root = Path(config["paths"].get("intermediate_root", f"output/{mode}/intermediate"))
    config["data_root"] = data_root if data_root.is_absolute() else (project_root / data_root).resolve()
    config["output_root"] = output_root if output_root.is_absolute() else (project_root / output_root).resolve()
    config["intermediate_root"] = intermediate_root if intermediate_root.is_absolute() else (project_root / intermediate_root).resolve()
    config["cache_root"] = (project_root / "cache" / "state_extract_v2").resolve()
    hash_payload = {
        str(key): _stable_config_value(value, str(key))
        for key, value in config.items()
        if key not in {"project_root", "data_root", "output_root", "intermediate_root", "config_hash", "raw_hashes"}
    }
    config["config_hash"] = object_hash(hash_payload)
    _validate_config(config)
    return config


def _validate_config(cfg: dict[str, Any]) -> None:
    cfg.setdefault("runtime", {})["progress_level"] = normalize_progress_level(
        cfg.get("runtime", {}).get("progress_level", "normal")
    )
    labels = cfg.get("labels", {})
    def contains_target_candidates(value: Any) -> bool:
        if isinstance(value, dict):
            return "target_candidates" in value or any(contains_target_candidates(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_target_candidates(item) for item in value)
        return False

    if contains_target_candidates(cfg):
        raise ValueError("formal PRE config must not contain target_candidates")
    if labels.get("formal_target") != FORMAL_TARGET_COLUMN:
        raise ValueError(f"formal PRE target must be {FORMAL_TARGET_COLUMN}")
    if labels.get("sensitivity_target") != SENSITIVITY_TARGET_COLUMN:
        raise ValueError(f"PRE sensitivity target must be {SENSITIVITY_TARGET_COLUMN}")
    transform = labels.get("sensitivity_transform", {})
    if transform.get("method") != "TRAIN_SPLIT_QUANTILE_CLIP" or transform.get("fit_split") != "train":
        raise ValueError("PRE sensitivity target must use the declared train-split quantile clip")
    clip_quantiles = [float(value) for value in transform.get("clip_quantiles", [])]
    if len(clip_quantiles) != 2 or not 0 <= clip_quantiles[0] < clip_quantiles[1] <= 1:
        raise ValueError("PRE sensitivity clip_quantiles must be an ordered probability pair")
    ratios = [float(value) for value in cfg["snapshots"]["ratios"]]
    if ratios != sorted(set(ratios)) or {round(value, 1) for value in ratios} != {i / 10 for i in range(1, 10)}:
        raise ValueError("snapshot ratios must be unique 0.1..0.9")
    split_intervals = []
    for name, bounds in cfg["splits"].items():
        if len(bounds) != 2:
            raise ValueError(f"split {name} must have start/end")
        start, end = pd.Timestamp(bounds[0]), pd.Timestamp(bounds[1])
        if start >= end:
            raise ValueError(f"split {name} has invalid interval")
        split_intervals.append((start, end, name))
    split_intervals.sort()
    for (_, previous_end, previous_name), (next_start, _, next_name) in zip(split_intervals, split_intervals[1:]):
        if previous_end > next_start:
            raise ValueError(f"split overlap: {previous_name}/{next_name}")
    action_ids = [str(value) for value in cfg["actions"]["action_ids"]]
    declared_count = int(cfg["actions"]["formal_action_count"])
    if len(action_ids) != declared_count or len(action_ids) != len(set(action_ids)):
        raise ValueError("authoritative M3 action contract count/uniqueness failure")
    predecessor = cfg.get("predecessor_matching", {})
    required_predecessor = {
        "contract_id", "feature_contract_version", "scientific_approved",
        "publication_allowed", "primary_rule", "sensitivity_rule",
        "gap_threshold_policy", "gap_threshold_minutes",
        "administrative_hard_ceiling_minutes", "missing_predecessor_policy",
    }
    missing_predecessor = sorted(required_predecessor - set(predecessor))
    if missing_predecessor:
        raise ValueError(
            "predecessor_matching.yaml missing: " + ",".join(missing_predecessor)
        )
    if float(predecessor["gap_threshold_minutes"]) <= 0:
        raise ValueError("predecessor gap threshold must be positive")
    if float(predecessor["administrative_hard_ceiling_minutes"]) < float(
        predecessor["gap_threshold_minutes"]
    ):
        raise ValueError("predecessor administrative ceiling below gap threshold")


def _package_versions() -> dict[str, str]:
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ["numpy", "pandas", "pyarrow", "PyYAML", "tqdm"]:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "NOT_INSTALLED"
    return versions


def _ensure_dirs(root: Path) -> dict[str, Path]:
    paths = {
        "root": root,
        "intermediate": root / "intermediate",
        "artifacts": root / "artifacts",
        "manifests": root / "manifests",
        "reports": root / "reports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


