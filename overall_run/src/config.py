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
    ("src/m1/adapter/feature_builder.py", "m1_feature_adapter"),
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
    ("src/m2.py", "m2"),
    ("src/m3.py", "m3"),
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
        directory / "m3_v3.yaml",
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
    actions = config["m3"].get("actions", [])
    expected_actions = [
        "A00", "A11", "A12", "A13", "A21", "A22", "A23", "A31", "A32",
        "A33", "A41", "A42", "A43", "A51", "A52", "A53", "A54", "A55",
        "A61", "A62", "A71", "A72", "A73", "A81", "A82", "A83",
    ]
    if [str(item.get("id")) for item in actions] != expected_actions:
        raise ConfigError("m3.actions does not match the frozen action order")
    graph_edges = {str(key): float(value) for key, value in config["m2"].get("graph_edges", {}).items()}
    allowed_edges = {"F_to_P", "F_to_R", "P_to_R"}
    if set(graph_edges) - allowed_edges:
        raise ConfigError("m2.graph_edges contains unsupported edges")
    if "R_to_F" in graph_edges:
        raise ConfigError("m2.graph_edges must not contain R_to_F")
    unit_costs = {str(key): float(value) for key, value in config["m2"].get("unit_costs_rmb", {}).items()}
    if set(unit_costs) != {"F", "P", "R"} or any(value < 0 for value in unit_costs.values()):
        raise ConfigError("m2.unit_costs_rmb must define non-negative F/P/R values")
    response = config["m3"].get("response_parameters", {})
    if set(response) != set(expected_actions):
        raise ConfigError("m3.response_parameters must cover all frozen actions")
    if config["m3"].get("response_parameter_version") != "M3_RESPONSE_V3_EXPANDED":
        raise ConfigError("m3.response_parameter_version must select M3_RESPONSE_V3_EXPANDED")
    ranking_depths = [int(value) for value in config["m4"].get("ranking_depths", [])]
    if ranking_depths != [1, 2, 3, 5] or int(config["m4"].get("maximum_ranking_depth", 0)) != 5:
        raise ConfigError("m4 ranking depths must be [1,2,3,5] with maximum 5")
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
