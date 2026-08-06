from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .action_contract import load_action_contract
from .m1.config import M1ConfigError, validate_m1_config


class ConfigError(RuntimeError):
    pass


AUTHORITATIVE_CODE = (
    ("main.py", "cli"),
    ("src/config.py", "configuration"),
    ("src/pipeline.py", "orchestration"),
    ("src/pipeline_checkpoint.py", "checkpoint_and_resume"),
    ("src/pipeline_data.py", "pipeline_data_contract"),
    ("src/pipeline_fit.py", "artifact_fit_stages"),
    ("src/pipeline_finalize.py", "acceptance_and_publication"),
    ("src/pipeline_modes.py", "validation_and_publication_modes"),
    ("src/pipeline_parameters.py", "parameter_provenance"),
    ("src/pipeline_precision.py", "precision_mode"),
    ("src/m1/contracts.py", "m1_contracts"),
    ("src/m1/config.py", "m1_configuration"),
    ("src/m1/pipeline.py", "m1_orchestration"),
    ("src/m1/adapter/manifest_validator.py", "m1_pre_manifest_adapter"),
    ("src/m1/adapter/bundle_loader.py", "m1_pre_bundle_adapter"),
    ("src/m1/adapter/availability.py", "m1_availability_adapter"),
    ("src/m1/adapter/timeline.py", "m1_timeline_adapter"),
    ("src/m1/adapter/feature_schema.py", "m1_feature_schema"),
    ("src/m1/adapter/operational_references.py", "m1_operational_reference_adapter"),
    ("src/m1/adapter/snapshot_builder.py", "m1_snapshot_adapter"),
    ("src/m1/adapter/episode_sequence.py", "m1_episode_sequence_adapter"),
    ("src/m1/adapter/target_builder.py", "m1_target_adapter"),
    ("src/m1/adapter/stage_builder.py", "m1_stage_adapter"),
    ("src/m1/model/network.py", "m1_gru"),
    ("src/m1/model/heads.py", "m1_distribution_heads"),
    ("src/m1/model/loss.py", "m1_loss"),
    ("src/m1/runtime/state_store.py", "m1_state_store"),
    ("src/m1/runtime/replay.py", "m1_replay"),
    ("src/m1/runtime/update_service.py", "m1_update_service"),
    ("src/m1/distribution/bins.py", "m1_distribution_bins"),
    ("src/m1/distribution/calibration.py", "m1_temperature_calibration"),
    ("src/m1/distribution/sampling.py", "m1_sampling"),
    ("src/m1/distribution/derived.py", "m1_derived_outputs"),
    ("src/m1/evaluation/report.py", "m1_evaluation"),
    ("src/m2/contracts.py", "m2_v2_contracts"),
    ("src/m2/input_adapter.py", "m1_to_m2_adapter"),
    ("src/m2/reconstruction.py", "m2_v2_reconstruction"),
    ("src/m2/summaries.py", "m2_v2_summaries"),
    ("src/m3/__init__.py", "m3_public_api"),
    ("src/m3/contracts.py", "m3_v4_contracts"),
    ("src/m3/catalog.py", "m3_v4_catalog"),
    ("src/m3/footprint.py", "m3_v4_footprint"),
    ("src/m3/parameters.py", "m3_v4_parameters"),
    ("src/m3/sampling.py", "m3_v4_sampling"),
    ("src/m3/costs.py", "m3_v4_costs"),
    ("src/m3/artifact.py", "m3_v4_artifact"),
    ("src/m3/compatibility.py", "m3_v4_compatibility"),
    ("src/m3/evaluation.py", "m3_v4_evaluation"),
    ("src/m4.py", "m4_public_api"),
    ("src/m4_screening.py", "m4_physical_screening"),
    ("src/m4_evaluation.py", "m4_risk_evaluation"),
    ("src/ranking_contract.py", "ranking_contract_adapter"),
    ("../ranking_contract.py", "ranking_contract"),
    ("src/report.py", "publication_orchestration"),
    ("src/report_contract.py", "publication_contract"),
    ("src/report_figures.py", "publication_figures"),
    ("src/report_m4.py", "publication_m4_diagnostics"),
    ("src/visualize.py", "publication_metric_figures"),
    ("src/visualize_common.py", "publication_figure_contract"),
    ("src/visualize_representative.py", "publication_representative_episode"),
    ("src/audit.py", "acceptance"),
    ("src/artifacts.py", "artifacts"),
    ("src/scientific_transition.py", "scientific_transition_contract"),
    ("config/scientific_transition_4ff_to_df2.json", "scientific_transition_definition"),
)
KNOWN_MODES = {
    "fast", "diagnostic", "adapt_full", "acceptance_23d", "middle", "full", "precision"
}
MODE_ALIASES = {"adapt_full": "acceptance_23d"}


def _canonical_hash(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Missing configuration file: {path}")
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Top-level YAML object must be a mapping: {path}")
    return data


def _implementation_manifest(root: Path, config_sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative, role in AUTHORITATIVE_CODE:
        path = (root / relative).resolve()
        if not path.exists():
            raise ConfigError(f"Authoritative implementation file missing: {path}")
        rows.append({"path": str(path), "sha256": _sha256(path), "role": role})
    for source in config_sources:
        rows.append({"path": source["absolute_path"], "sha256": source["sha256"], "role": "configuration"})
    return rows


@dataclass(frozen=True)
class RunConfig:
    merged: dict[str, Any]
    root: Path
    mode_name: str
    config_hash: str
    implementation_hash: str
    config_sources: list[dict[str, Any]]
    implementation_manifest: list[dict[str, str]]
    requested_mode: str
    profile_contract: dict[str, Any]

    @property
    def scientific(self) -> dict[str, Any]:
        return self.merged

    @property
    def compute(self) -> dict[str, Any]:
        return self.merged

    @property
    def acceptance(self) -> dict[str, Any]:
        return self.merged

    @property
    def contract_version(self) -> str:
        return str(self.merged["contract_version"])

    @property
    def project_version(self) -> str:
        return str(self.merged.get("project", {}).get("version", "0.0.0"))

    def mode(self, name: str | None = None) -> dict[str, Any]:
        selected = name or self.mode_name
        modes = self.merged.get("modes", {})
        if selected not in modes:
            raise ConfigError(f"Unknown mode: {selected}")
        return dict(modes[selected])


def load_config(
    root: Path,
    mode: str = "full",
    override: Path | None = None,
    config_dir: Path | None = None,
) -> RunConfig:
    root = root.resolve()
    if mode not in KNOWN_MODES:
        raise ConfigError(f"Unknown mode: {mode}")
    requested_mode = mode
    mode = MODE_ALIASES.get(mode, mode)
    directory = (config_dir or (root / "config")).resolve()
    paths = [
        directory / "default.yaml",
        directory / "scientific.yaml",
        directory / "m3_response_v4_atomic_subitem.yaml",
        directory / "compute.yaml",
        directory / "acceptance.yaml",
        directory / f"{mode}.yaml",
    ]
    if override is not None:
        candidate = override if override.is_absolute() else (root / override)
        paths.append(candidate.resolve())
    loaded_at = datetime.now(timezone.utc).isoformat()
    sources: list[dict[str, Any]] = []
    merged: dict[str, Any] = {}
    for order, path in enumerate(paths, 1):
        data = _load_yaml(path)
        merged = _deep_merge(merged, data)
        sources.append({
            "absolute_path": str(path.resolve()),
            "exists": True,
            "sha256": _sha256(path),
            "merge_order": order,
            "loaded_at": loaded_at,
        })
    merged["mode"] = mode
    _validate_config(merged, mode)
    config_hash = _canonical_hash(merged)
    implementation_manifest = _implementation_manifest(root, sources)
    implementation_hash = _canonical_hash([
        {"path": row["path"], "sha256": row["sha256"], "role": row["role"]}
        for row in implementation_manifest
    ])
    return RunConfig(
        merged=merged,
        root=root,
        mode_name=mode,
        config_hash=config_hash,
        implementation_hash=implementation_hash,
        config_sources=sources,
        implementation_manifest=implementation_manifest,
        requested_mode=requested_mode,
        profile_contract={
            "requested_token": requested_mode,
            "profile_id": mode,
            "run_profile": None if mode == "acceptance_23d" else mode,
            "acceptance_profile": "acceptance_23d" if mode == "acceptance_23d" else None,
            "compute_profile": "full" if mode in {"acceptance_23d", "middle", "full"} else mode,
            "legacy_token": "adapt_full" if requested_mode == "adapt_full" else None,
            "smoke_subset": False,
            "output_id": mode,
        },
    )


def _validate_config(config: dict[str, Any], mode: str) -> None:
    required_top = ("contract_version", "project", "paths", "cohort", "m1", "m2", "m3", "m4", "modes", "performance", "warnings", "gates")
    missing = [key for key in required_top if key not in config]
    if missing:
        raise ConfigError("Missing merged configuration keys: " + ",".join(missing))
    if mode not in config["modes"]:
        raise ConfigError(f"compute.modes does not define {mode}")
    if "m1_tuning" in config:
        raise ConfigError("RETIRED_M1_CONFIG_KEY:m1_tuning")
    try:
        validate_m1_config(config["m1"])
    except M1ConfigError as exc:
        raise ConfigError(str(exc)) from exc
    m3_contract = load_action_contract("V4")
    actions = config["m3"].get("actions", [])
    expected_actions = list(m3_contract["action_ids"])
    if [str(item.get("action_id")) for item in actions] != expected_actions:
        raise ConfigError("m3.actions does not match the V4 atomic action order")
    if config["m3"].get("identity", {}).get("name") != "M3_RESPONSE_V4_ATOMIC_SUBITEM":
        raise ConfigError("m3 identity must select M3_RESPONSE_V4_ATOMIC_SUBITEM")
    versions = config["m3"].get("version", {})
    if versions.get("action_library") != "M3_ATOMIC_ACTION_LIBRARY_V1":
        raise ConfigError("m3 action library must select M3_ATOMIC_ACTION_LIBRARY_V1")
    if versions.get("response_contract") != "M3_SUBITEM_RESPONSE_V1":
        raise ConfigError("m3 response contract must select M3_SUBITEM_RESPONSE_V1")
    if config["m3"].get("config_path") != "config/m3_response_v4_atomic_subitem.yaml":
        raise ConfigError("m3.config_path must select the independent V4 contract")
    status = config["m3"].get("status", {})
    if status.get("parameter_freeze") != "NOT_YET_DONE":
        raise ConfigError("m3 parameter freeze must remain NOT_YET_DONE")
    if status.get("formal_library") != "NOT_YET_RUN":
        raise ConfigError("m3 formal library must remain NOT_YET_RUN")
    m2 = config["m2"]
    required_m2 = {
        "identity": "EPISODE_PRE_ACTION_LOSS_RECONSTRUCTION_V2",
        "subitem_schema_version": "M2_SUBITEM_SCHEMA_V2",
        "subitem_contract_version": "M2_NINE_SUBITEM_V1",
        "input_mode": "M1_SCENARIO_PLUS_PRE_CONTEXT",
        "primary_mode": "DIRECT_STRUCTURAL_COMPACT",
        "formal_loss_field": "total_pre_action_loss_rmb",
        "valuation_version": "REQUIRES_DEVELOPMENT_FREEZE",
    }
    for key, expected in required_m2.items():
        if m2.get(key) != expected:
            raise ConfigError(f"m2.{key} must be {expected}")
    complexity = m2.get("complexity", {})
    if int(complexity.get("max_nonzero_breakpoints_per_subitem", -1)) != 2:
        raise ConfigError("m2 complexity breakpoint limit must be 2")
    if int(complexity.get("max_primary_context_multipliers_per_subitem", -1)) != 1:
        raise ConfigError("m2 context multiplier limit must be 1")
    if complexity.get("allow_high_order_interactions") is not False:
        raise ConfigError("m2 high-order interactions must be disabled")
    if complexity.get("allow_neural_reconstruction") is not False:
        raise ConfigError("m2 neural reconstruction must be disabled")
    if m2.get("cross_channel", {}).get("primary_mode") != "DIRECT_ONLY":
        raise ConfigError("m2 cross-channel primary mode must be DIRECT_ONLY")
    if m2.get("learned_correction", {}).get("enabled") is not False:
        raise ConfigError("m2 learned correction must be disabled")
    currency = m2.get("currency", {})
    if (
        currency.get("code") != "RMB"
        or currency.get("mapping_mode") != "IDENTITY"
        or currency.get("mapping_version") != "IDENTITY_V1_EXPLICIT"
    ):
        raise ConfigError("m2 currency must use RMB IDENTITY")
    rates = [currency.get(name) for name in (
        "flight_rmb_per_cu", "passenger_rmb_per_cu", "resource_rmb_per_cu"
    )]
    if rates != [1.0, 1.0, 1.0]:
        raise ConfigError("m2 formal currency mapping must be 1 CU = 1 RMB")
    if any(
        key in config["m3"]
        for key in ("response_parameters", "response_parameter_version", "resource_profiles")
    ):
        raise ConfigError("m3 active config contains retired V2/V3 response fields")
    decision_value = config["m4"].get("decision_value", {})
    for key in ("burden_ratio_max", "positive_net_benefit_probability_min"):
        if key not in decision_value:
            raise ConfigError(f"m4.decision_value.{key} is required")
    for key in ("coverage_90_lower", "coverage_90_upper"):
        if not isinstance(config["performance"].get(key), (int, float)):
            raise ConfigError(f"performance.{key} must be numeric")
    for gate in ("tail_coverage_90_lower", "quantile_crossing_rate_max", "passenger_proxy_support_required", "artifact_contract_required", "config_contract_required"):
        if gate not in config["gates"]:
            raise ConfigError(f"gates.{gate} is required")
    mode_config = config["modes"][mode]
    if int(mode_config.get("formal_samples", 0)) < 1:
        raise ConfigError(f"modes.{mode}.formal_samples must be positive")


def dump_config_snapshot(cfg: RunConfig, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "merged_config.json").write_text(
        json.dumps(cfg.merged, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (target_dir / "config_sources.json").write_text(
        json.dumps(cfg.config_sources, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (target_dir / "implementation_manifest.json").write_text(
        json.dumps(cfg.implementation_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
