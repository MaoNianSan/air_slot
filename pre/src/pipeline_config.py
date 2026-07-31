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
from .target_contract import FORMAL_TARGET_COLUMN, SENSITIVITY_TARGET_COLUMN


@dataclass
class BuildResult:
    output_root: Path
    validation: dict[str, Any]
    readiness: dict[str, Any]
    manifest: dict[str, Any]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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
    config["schema"] = _read_yaml(config_dir / "schema.yaml")
    config["actions"] = _read_yaml(config_dir / "actions.yaml")
    mode_path = config_dir / f"{mode}.yaml"
    if mode_path.exists():
        config = _deep_merge(config, _read_yaml(mode_path))
    if override_path:
        override = Path(override_path)
        if not override.is_absolute():
            cwd_candidate = (Path.cwd() / override).resolve()
            override = cwd_candidate if cwd_candidate.exists() else (project_root / override).resolve()
        config = _deep_merge(config, _read_yaml(override))
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
        key: value for key, value in config.items()
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
    if len(cfg["actions"]["action_ids"]) != 13:
        raise ValueError("actions.yaml must declare exactly 13 action IDs")


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


