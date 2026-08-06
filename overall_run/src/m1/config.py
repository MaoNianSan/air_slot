from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import M1_CONTRACT_ID


class M1ConfigError(ValueError):
    pass


RETIRED_KEYS = {
    "formal_" + "target",
    "sensitivity_" + "target",
    "quantiles",
    "tuning_" + "quantiles",
    "historical_" + "baseline",
    "feature_" + "allowlist",
    "feature_" + "contract_version",
    "trigger_probability_threshold",
    "n_estimators",
    "num_" + "leaves",
    "m1_" + "tuning",
    "y_" + "movement_raw",
    "y_" + "movement_model",
}

REQUIRED_EXCLUSIONS = {
    "separate_fast_model",
    "lightgbm_formal_model",
    "independent_takeoff_head",
    "online_weight_update",
    "adaptive_test_calibration",
    "cross_module_training",
}


@dataclass(frozen=True)
class M1Settings:
    contract_id: str = M1_CONTRACT_ID
    hidden_size: int = 8
    hidden_size_sensitivity: tuple[int, ...] = (16,)
    roll_minutes: int = 5
    roll_sensitivity_minutes: tuple[int, ...] = (10,)
    horizons_minutes: tuple[int, ...] = (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)
    delay_thresholds_minutes: tuple[int, ...] = (15, 30, 60)
    bin_minutes: int = 5
    predecessor_max_minutes: int = 480
    learned_upper_quantile: float = 0.995
    sample_count: int = 1000
    base_seed: int = 20260718
    calibration_tail_fraction: float = 0.5
    minimum_episodes_per_partition: int = 2
    feature_schema_version: str = "M1_FEATURE_SCHEMA_V1"
    maximum_snapshot_minutes: int = 480
    stale_after_minutes: float = 30.0
    require_model_checkpoint: bool = True
    require_temperature_artifact: bool = True
    allow_identity_temperature_in_formal: bool = False
    bin_representative_mode: str = "FIXED_WITHIN_BIN_UNIFORM"
    overflow_mode: str = "TRAINING_EMPIRICAL_TAIL"
    min_empirical_tail_count: int = 30
    dependence_mode: str = "CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING"


def _walk(mapping: Mapping[str, Any], prefix: str = "") -> list[str]:
    hits: list[str] = []
    for raw_key, value in mapping.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if key in RETIRED_KEYS:
            hits.append(path)
        if isinstance(value, Mapping):
            hits.extend(_walk(value, path))
    return hits


def validate_m1_config(config: Mapping[str, Any]) -> M1Settings:
    retired = _walk(config)
    if retired:
        raise M1ConfigError("RETIRED_M1_CONFIG_KEY:" + ",".join(sorted(retired)))
    if config.get("contract_id") != M1_CONTRACT_ID:
        raise M1ConfigError("M1_CONTRACT_ID_INVALID")
    architecture = config.get("architecture", {})
    required_architecture = {
        "type": "single_lightweight_gru",
        "layers": 1,
        "bidirectional": False,
        "attention": False,
        "dropout": 0.0,
    }
    for key, expected in required_architecture.items():
        if architecture.get(key) != expected:
            raise M1ConfigError(f"M1_ARCHITECTURE_INVALID:{key}")
    if int(architecture.get("hidden_size", 0)) != 8:
        raise M1ConfigError("M1_ARCHITECTURE_INVALID:hidden_size")
    if tuple(int(v) for v in architecture.get("hidden_size_sensitivity", ())) != (16,):
        raise M1ConfigError("M1_ARCHITECTURE_INVALID:hidden_size_sensitivity")
    if float(architecture.get("gradient_clip", -1)) != 1.0:
        raise M1ConfigError("M1_ARCHITECTURE_INVALID:gradient_clip")
    if float(architecture.get("weight_decay", -1)) != 0.0001:
        raise M1ConfigError("M1_ARCHITECTURE_INVALID:weight_decay")
    pre = config.get("pre", {})
    required_pre = {
        "required_contract_id": "AIR_CHAIN_CORE_V2",
        "required_schema_version": "air-chain-core-2.0",
        "required_research_revision": "AIR_CHAIN_CORE_V2_R2",
        "published_bundle_only": True,
    }
    for key, expected in required_pre.items():
        if pre.get(key) != expected:
            raise M1ConfigError(f"M1_PRE_CONFIG_INVALID:{key}")
    exclusions = config.get("exclusions", {})
    if set(exclusions) != REQUIRED_EXCLUSIONS or any(
        value is not False for value in exclusions.values()
    ):
        raise M1ConfigError("M1_EXCLUSION_FLAG_MUST_BE_FALSE")
    calibration = config.get("calibration", {})
    if calibration.get("enabled") is not True:
        raise M1ConfigError("M1_CALIBRATION_DISABLED")
    if calibration.get("method") != "temperature_scaling":
        raise M1ConfigError("M1_CALIBRATION_METHOD_INVALID")
    if calibration.get("scope") != "per_target":
        raise M1ConfigError("M1_CALIBRATION_SCOPE_INVALID")
    if calibration.get("fit_partition") != "calibration":
        raise M1ConfigError("M1_CALIBRATION_PARTITION_INVALID")
    time = config.get("time", {})
    horizons = tuple(int(value) for value in time.get("horizons_minutes", ()))
    thresholds = tuple(int(value) for value in time.get("delay_thresholds_minutes", ()))
    if horizons != M1Settings.horizons_minutes:
        raise M1ConfigError("M1_HORIZON_GRID_INVALID")
    if thresholds != M1Settings.delay_thresholds_minutes:
        raise M1ConfigError("M1_DELAY_THRESHOLDS_INVALID")
    if int(time.get("roll_minutes", 0)) != 5:
        raise M1ConfigError("M1_ROLL_MINUTES_INVALID")
    if tuple(int(v) for v in time.get("roll_sensitivity_minutes", ())) != (10,):
        raise M1ConfigError("M1_ROLL_SENSITIVITY_INVALID")
    distribution = config.get("distribution", {})
    if distribution.get("overflow_bin") is not True:
        raise M1ConfigError("M1_OVERFLOW_BIN_REQUIRED")
    sampling = config.get("sampling", {})
    if sampling.get("fixed_episode_random_numbers") is not True:
        raise M1ConfigError("M1_FIXED_RANDOM_NUMBERS_REQUIRED")
    if sampling.get("bin_representative_mode") != "FIXED_WITHIN_BIN_UNIFORM":
        raise M1ConfigError("M1_BIN_REPRESENTATIVE_MODE_INVALID")
    if sampling.get("overflow_mode") != "TRAINING_EMPIRICAL_TAIL":
        raise M1ConfigError("M1_OVERFLOW_MODE_INVALID")
    if int(sampling.get("min_empirical_tail_count", 0)) < 1:
        raise M1ConfigError("M1_EMPIRICAL_TAIL_COUNT_INVALID")
    if sampling.get("dependence_mode") != "CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING":
        raise M1ConfigError("M1_DEPENDENCE_MODE_INVALID")
    feature_schema = config.get("feature_schema", {})
    if feature_schema.get("version") != "M1_FEATURE_SCHEMA_V1":
        raise M1ConfigError("M1_FEATURE_SCHEMA_VERSION_INVALID")
    required_schema_flags = {
        "include_missing_mask",
        "include_observation_age",
        "include_stale_mask",
        "include_fallback_mask",
        "include_stage_encoding",
        "include_delta_t",
    }
    if any(feature_schema.get(key) is not True for key in required_schema_flags):
        raise M1ConfigError("M1_FEATURE_SCHEMA_COMPONENT_DISABLED")
    snapshot = config.get("snapshot", {})
    if int(snapshot.get("roll_minutes", 0)) != 5:
        raise M1ConfigError("M1_SNAPSHOT_ROLL_INVALID")
    if int(snapshot.get("maximum_minutes", -1)) != 480:
        raise M1ConfigError("M1_SNAPSHOT_MAXIMUM_INVALID")
    if snapshot.get("scheduled_grid_required") is not True:
        raise M1ConfigError("M1_SNAPSHOT_GRID_REQUIRED")
    runtime = config.get("runtime", {})
    required_runtime = {
        "incremental_step_nodes": 1,
        "revision_replay": "full_from_revision",
        "temporary_state_isolated": True,
    }
    for key, expected in required_runtime.items():
        if runtime.get(key) != expected:
            raise M1ConfigError(f"M1_RUNTIME_CONFIG_INVALID:{key}")
    artifacts = config.get("artifacts", {})
    if artifacts.get("require_model_checkpoint") is not True:
        raise M1ConfigError("M1_MODEL_CHECKPOINT_NOT_REQUIRED")
    if artifacts.get("require_temperature_artifact") is not True:
        raise M1ConfigError("M1_TEMPERATURE_ARTIFACT_NOT_REQUIRED")
    if artifacts.get("allow_identity_temperature_in_formal") is not False:
        raise M1ConfigError("M1_IDENTITY_TEMPERATURE_FORMAL_PROHIBITED")
    readiness = config.get("readiness", {})
    if readiness.get("target_support_implies_training_pass") is not False:
        raise M1ConfigError("M1_READINESS_TRAINING_INFERENCE_PROHIBITED")
    if readiness.get("target_support_implies_calibration_pass") is not False:
        raise M1ConfigError("M1_READINESS_CALIBRATION_INFERENCE_PROHIBITED")
    return M1Settings(
        hidden_size=int(architecture.get("hidden_size", 8)),
        hidden_size_sensitivity=tuple(int(v) for v in architecture.get("hidden_size_sensitivity", [16])),
        roll_minutes=int(time.get("roll_minutes", 5)),
        roll_sensitivity_minutes=tuple(int(v) for v in time.get("roll_sensitivity_minutes", [10])),
        horizons_minutes=horizons,
        delay_thresholds_minutes=thresholds,
        bin_minutes=int(distribution.get("bin_minutes", 5)),
        predecessor_max_minutes=int(distribution.get("predecessor_max_minutes", 480)),
        learned_upper_quantile=float(distribution.get("learned_upper_quantile", 0.995)),
        sample_count=int(sampling.get("sample_count", 1000)),
        base_seed=int(sampling.get("base_seed", 20260718)),
        calibration_tail_fraction=float(config.get("split", {}).get("calibration_tail_fraction", 0.5)),
        minimum_episodes_per_partition=int(config.get("split", {}).get("minimum_episodes_per_partition", 2)),
        feature_schema_version=str(feature_schema["version"]),
        maximum_snapshot_minutes=int(snapshot["maximum_minutes"]),
        stale_after_minutes=float(snapshot.get("stale_after_minutes", 30.0)),
        require_model_checkpoint=bool(artifacts["require_model_checkpoint"]),
        require_temperature_artifact=bool(artifacts["require_temperature_artifact"]),
        allow_identity_temperature_in_formal=bool(
            artifacts["allow_identity_temperature_in_formal"]
        ),
        bin_representative_mode=str(sampling["bin_representative_mode"]),
        overflow_mode=str(sampling["overflow_mode"]),
        min_empirical_tail_count=int(sampling["min_empirical_tail_count"]),
        dependence_mode=str(sampling["dependence_mode"]),
    )
