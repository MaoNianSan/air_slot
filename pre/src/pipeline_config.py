from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .core.contracts import CONTRACT_ID, RESEARCH_CODE_REVISION, SCHEMA_VERSION
from .progress import normalize_progress_level
from .shared.config_merge import strict_deep_merge


SUPPORTED_MODES = ("fast", "middle", "full", "diagnostic")
EXPECTED_ARTIFACTS = (
    "episodes",
    "events",
    "observations",
    "observation_membership",
    "calibration",
    "evidence_audit",
    "column_registry",
    "pre_manifest",
)


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"CONFIG_TOP_LEVEL_NOT_MAPPING={path}")
    return payload


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


def _resolve_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (project_root / path).resolve()


def validate_shared_config(cfg: dict[str, Any]) -> None:
    cfg.setdefault("runtime", {})["progress_level"] = normalize_progress_level(
        cfg.get("runtime", {}).get("progress_level", "normal")
    )
    if not cfg.get("sources"):
        raise ValueError("CORE_V2_SOURCES_MISSING")
    for name, source in cfg["sources"].items():
        if not isinstance(source, dict) or "root" not in source:
            raise ValueError(f"CORE_V2_SOURCE_INVALID={name}")
    intervals: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
    for name, bounds in cfg.get("splits", {}).items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError(f"CORE_V2_SPLIT_INVALID={name}")
        start, end = pd.Timestamp(bounds[0]), pd.Timestamp(bounds[1])
        if start >= end:
            raise ValueError(f"CORE_V2_SPLIT_INVALID={name}")
        intervals.append((start, end, name))
    if [name for _, _, name in intervals] != ["train", "validation", "test"]:
        raise ValueError("CORE_V2_SPLIT_ORDER_INVALID")
    for (_, previous_end, previous), (next_start, _, following) in zip(
        intervals, intervals[1:]
    ):
        if previous_end > next_start:
            raise ValueError(f"CORE_V2_SPLIT_OVERLAP={previous}/{following}")
    if not cfg.get("airports", {}).get("core"):
        raise ValueError("CORE_V2_AIRPORT_COHORT_EMPTY")


def validate_core_v2_config(cfg: dict[str, Any]) -> None:
    schema = cfg.get("core_schema", {})
    identity = (
        schema.get("contract_id"),
        schema.get("schema_version"),
        schema.get("research_code_revision"),
    )
    if identity != (CONTRACT_ID, SCHEMA_VERSION, RESEARCH_CODE_REVISION):
        raise ValueError(f"CORE_V2_SCHEMA_IDENTITY_MISMATCH={identity}")
    if tuple(schema.get("formal_artifacts", ())) != EXPECTED_ARTIFACTS:
        raise ValueError("CORE_V2_FORMAL_ARTIFACT_SET_INVALID")
    event_specs = cfg.get("event_specs", {})
    required_events = {"ATOT_MINUS", "ALDT_MINUS", "AIBT_MINUS", "AOBT_PLUS", "ATOT_PLUS"}
    if set(event_specs) != required_events:
        raise ValueError("CORE_V2_EVENT_CONTRACT_INVALID")
    for name, spec in event_specs.items():
        if spec.get("support_level") not in {"SUPPORTED_PROXY", "UNSUPPORTED"}:
            raise ValueError(f"CORE_V2_EVENT_SUPPORT_INVALID={name}")
        if spec.get("support_level") == "UNSUPPORTED" and spec.get("time_column") is not None:
            raise ValueError(f"CORE_V2_UNSUPPORTED_EVENT_HAS_SOURCE={name}")
    predecessor = cfg.get("predecessor_matching", {})
    required_chain = {
        "contract_id", "feature_contract_version", "primary_rule",
        "gap_threshold_policy", "gap_threshold_minutes",
        "administrative_hard_ceiling_minutes", "missing_predecessor_policy",
    }
    if required_chain - set(predecessor):
        raise ValueError("CORE_V2_CHAIN_CONTRACT_INCOMPLETE")
    threshold = float(predecessor["gap_threshold_minutes"])
    ceiling = float(predecessor["administrative_hard_ceiling_minutes"])
    if threshold <= 0 or ceiling < threshold:
        raise ValueError("CORE_V2_CHAIN_THRESHOLDS_INVALID")
    request = cfg.get("request_contract", {})
    if request.get("sources") != ["state", "weather", "flow"]:
        raise ValueError("CORE_V2_REQUEST_SOURCES_INVALID")
    if float(cfg.get("state_vectors", {}).get("lookback_minutes", 0)) <= 0:
        raise ValueError("CORE_V2_STATE_WINDOW_INVALID")
    if float(cfg.get("flow", {}).get("lookback_minutes", 0)) <= 0:
        raise ValueError("CORE_V2_FLOW_WINDOW_INVALID")
    partitioning = schema.get("partitioning", {})
    expected_partition = ["source", "observation_date"]
    if partitioning.get("observations") != expected_partition or partitioning.get("observation_membership") != expected_partition:
        raise ValueError("CORE_V2_PARTITIONING_INVALID")
    retention = schema.get("retention_rules", {})
    if not retention.get("source_global_observation") or not retention.get("preserve_raw_columns_unless_temporary_or_duplicate"):
        raise ValueError("CORE_V2_RETENTION_RULES_INVALID")
    membership = cfg.get("core_membership", {})
    if membership.get("partition_unit") != "source_date" or membership.get("many_to_many") is not True:
        raise ValueError("CORE_V2_MEMBERSHIP_RULES_INVALID")
    if set(membership.get("identity", {})) != {"state", "weather", "flow"}:
        raise ValueError("CORE_V2_MEMBERSHIP_IDENTITY_INVALID")
    if cfg.get("eligibility", {}).get("observed_chain_proxy_scientific_eligible") is not False:
        raise ValueError("CORE_V2_ELIGIBILITY_SEMANTICS_INVALID")
    if cfg.get("references", {}).get("passenger", {}).get("reference_period_semantics") != "source_period_end_before_or_at_train_cutoff":
        raise ValueError("CORE_V2_REFERENCE_RULES_INVALID")
    required_manifest = {
        "contract_id", "schema_version", "research_code_revision",
        "frozen_config_hash", "source_manifest_hash", "source_schema_hash",
        "event_contract_hash", "chain_contract_hash", "split_contract_hash",
        "reference_contract_hash", "observation_contract_hash",
        "column_registry_contract_hash", "file_hashes",
    }
    if required_manifest - set(schema.get("manifest_required", [])):
        raise ValueError("CORE_V2_MANIFEST_FIELDS_INCOMPLETE")


def load_config(
    override_path: str | Path | None = None,
    *,
    mode: str = "full",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"CORE_V2_MODE_UNSUPPORTED={mode}")
    project_root = Path(__file__).resolve().parents[1]
    config_dir = project_root / "config"
    config = _read_yaml(config_dir / "default.yaml")
    mode_overrides = config.pop("mode_overrides")
    config["sources"] = _read_yaml(config_dir / "sources.yaml")["sources"]
    config["core_schema"] = _load_core_schema(config_dir)
    config["predecessor_matching"] = _read_yaml(
        config_dir / "predecessor_matching.yaml"
    )
    config = strict_deep_merge(config, mode_overrides[mode])
    if override_path:
        override = Path(override_path)
        if not override.is_absolute():
            cwd_candidate = (Path.cwd() / override).resolve()
            override = cwd_candidate if cwd_candidate.exists() else (project_root / override).resolve()
        config = strict_deep_merge(config, _read_yaml(override))
    config["mode"] = mode
    config["project_root"] = project_root
    config["data_root"] = _resolve_path(project_root, config["paths"]["data_root"])
    configured_output = output_dir or config["paths"]["output_root"]
    config["output_root"] = _resolve_path(project_root, configured_output)
    config["cache_root"] = (project_root / "cache" / "state_extract_v2").resolve()
    validate_shared_config(config)
    validate_core_v2_config(config)
    return config
