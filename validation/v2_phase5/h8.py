"""Phase 5 H8 lower-capacity sensitivity artifact (matched training contract).

The legacy ``M1_FROZEN_H8`` checkpoint was produced under the retired fast
contract (seed 20260821, 2 epochs) and is therefore *not* an H/history-only
contrast against the frozen H16 primary. Phase 5 retrains H8 from the exact H16
cache and the exact formal cohort with the identical Stage-1 training contract
(seed 20260813, 8 epochs, Adam, lr 0.001, weight decay 0.0, batch 64), changing
only the hidden width. The result is a Phase-5-owned sensitivity artifact; the
H16 primary and the Current comparator are never modified.

Only the Development splits of the frozen cache are consumed. No Final-Test path
is read and ``FINAL_TEST_ACCESS_COUNT`` stays unchanged.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Mapping

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_COUNT
from model.M1.history import HistoryEncoderMode
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from model.M1.tuning_stage1 import (
    OPTIONAL_ROBUSTNESS_SEEDS,
    PRIMARY_EPOCHS,
    PRIMARY_TRAINING_SEED,
    STAGE1_SUPPORT,
    STAGE1_TRAINING_CONFIG,
    validate_stage1_contract,
)
from model.common.config import load_config_layers
from model.common.errors import ContractError
from model.common.identity import content_id

from .common import (
    COHORT_PATH,
    H16_MANIFEST,
    H8_CHECKPOINT,
    H8_MANIFEST,
    H8_ROOT,
    PROJECT_ROOT,
    SOURCE_CACHE,
    SOURCE_CACHE_MANIFEST,
    assert_development_path,
    file_hash,
    read_json,
    write_json,
)


LEGACY_H8_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1" / "M1_FROZEN_H8"
LEGACY_H8_MANIFEST = LEGACY_H8_ROOT / "M1_FROZEN_H8_MANIFEST.json"
LEGACY_H8_CHECKPOINT = LEGACY_H8_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST.pt"
LEGACY_H8_TRAINING_SEED = 20260821
LEGACY_H8_EPOCHS = 2

MODEL_VERSION = "M1_STATE_ESTIMATOR_V2_H8_PHASE5_MATCHED"
ARTIFACT_STATUS = "FORMAL_SENSITIVITY_RUNTIME_ARTIFACT_READY"
MODEL_ROLE = "PRIMARY_LOWER_CAPACITY_SENSITIVITY"
SELECTION_ROLE = "PREDEFINED_SENSITIVITY_ONLY"
HISTORY_SCOPE = "FULL_ADAPTIVE_CAUSAL_PREFIX"

#: Contract fields that must be identical to the frozen H16 primary apart from
#: the hidden width. Naming and artifact identity are recorded separately.
CONTRACT_KEYS: tuple[str, ...] = (
    "training_seed",
    "epochs",
    "optimizer",
    "learning_rate",
    "weight_decay",
    "batch_size",
    "training_cohort_hash",
    "train_episode_hash",
    "calibration_cohort_hash",
    "development_cohort_hash",
    "target_contract_hash",
    "support_contract_hash",
    "feature_contract_hash",
    "scenario_count",
    "history_mode",
)


def _source_cache(cache_manifest: Mapping[str, Any]) -> M1DevelopmentBaseCache:
    return M1DevelopmentBaseCache.load(
        SOURCE_CACHE,
        SOURCE_CACHE_MANIFEST,
        expected_cache_key=cache_manifest["cache_key"],
        allow_legacy_schema=True,
    )


def _cohort_rows(
    cache: M1DevelopmentBaseCache, cohort: Mapping[str, Any], split: str
):
    ids = set(cohort[f"{split}_episode_ids"])
    rows = tuple(
        row
        for row in cache.partition(split, representation="ADAPTIVE_HISTORY")
        if row.episode_id in ids
    )
    if {row.episode_id for row in rows} != ids:
        raise ContractError(f"PHASE5_H8_COHORT_ID_MISMATCH:{split}")
    return rows


def matched_audit(
    manifest: Mapping[str, Any],
    h16_manifest: Mapping[str, Any],
    *,
    hidden_size: int,
) -> dict[str, Any]:
    """Verify that H8 differs from H16 only by hidden width and identity."""

    checks = {
        key: manifest.get(key) == h16_manifest.get(key) for key in CONTRACT_KEYS
    }
    h8_width = manifest.get("hidden_size")
    h16_width = h16_manifest.get("hidden_size")
    resolved_h8 = None if h8_width is None else int(h8_width)
    resolved_h16 = None if h16_width is None else int(h16_width)
    checks["different_hidden_size"] = (
        resolved_h8 != resolved_h16 and resolved_h8 == int(hidden_size)
    )
    checks["different_artifact_identity"] = (
        manifest.get("model_version") != h16_manifest.get("model_version")
    )
    checks["lower_capacity"] = (
        resolved_h8 is not None
        and resolved_h16 is not None
        and resolved_h8 < resolved_h16
    )
    checks["no_final_test_access"] = (
        int(manifest.get("final_test_access_count", -1)) == 0
        and int(h16_manifest.get("final_test_access_count", -1)) == 0
    )
    checks["development_not_used_for_selection"] = (
        manifest.get("development_used_for_parameter_selection") is False
        and h16_manifest.get("development_used_for_parameter_selection") is False
    )
    checks = {name: bool(value) for name, value in checks.items()}
    audit = {
        "schema_version": "V2_PHASE5_H8_MATCHED_CONTRACT_AUDIT_V1",
        "checks": checks,
        "h16_hidden_size": h16_width,
        "h8_hidden_size": h8_width,
        "h16_model_version": h16_manifest.get("model_version"),
        "h8_model_version": manifest.get("model_version"),
        "h16_checkpoint_hash": h16_manifest.get("checkpoint_hash"),
        "h8_checkpoint_hash": manifest.get("checkpoint_hash"),
        "changed_factor": "HISTORY_CAPACITY_ONLY",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "final_test_access_count": 0,
        "development_used_for_parameter_selection": False,
    }
    if audit["status"] != "PASS":
        failed = sorted(name for name, ok in checks.items() if not ok)
        raise ContractError(
            "PHASE5_H8_MATCHED_CONTRACT_FAILED:" + ",".join(failed)
        )
    return audit


def h8_hidden_size(scientific: Any) -> int:
    primary = int(scientific.parameters["m1_hidden_size"].value)
    sensitivity = int(scientific.parameters["m1_sensitivity_hidden_size"].value)
    if sensitivity >= primary:
        raise ContractError("PHASE5_H8_NOT_A_LOWER_CAPACITY_SETTING")
    return sensitivity


def _reusable_manifest(
    h16_manifest: Mapping[str, Any], cache_key: str, hidden_size: int
) -> dict[str, Any] | None:
    if not H8_MANIFEST.is_file() or not H8_CHECKPOINT.is_file():
        return None
    manifest = read_json(H8_MANIFEST)
    if manifest.get("source_cache_key") != cache_key:
        return None
    if int(manifest.get("hidden_size", -1)) != hidden_size:
        return None
    if file_hash(H8_CHECKPOINT) != manifest.get("checkpoint_hash"):
        return None
    for key in CONTRACT_KEYS:
        if manifest.get(key) != h16_manifest.get(key):
            return None
    return manifest


def _expected_contract_hashes(h16_manifest: Mapping[str, Any]) -> dict[str, str]:
    """Recompute the shared contract hashes and cross-check the H16 manifest."""

    expected = {
        "support_contract_hash": content_id(STAGE1_SUPPORT),
        "feature_contract_hash": content_id({"feature_names": FEATURE_NAMES_V2}),
    }
    for name, value in expected.items():
        if h16_manifest.get(name) != value:
            raise ContractError(f"PHASE5_H8_SHARED_CONTRACT_HASH_MISMATCH:{name}")
    return expected


def _legacy_supersession_note() -> dict[str, Any]:
    return {
        "status": "SUPERSEDED_FOR_PHASE5_MATCHED_CONTRACT",
        "reason": (
            "LEGACY_FAST_CONTRACT_SEED_20260821_TWO_EPOCHS_CONFOUNDS_H_WITH_"
            "TRAINING_CONTRACT"
        ),
        "legacy_manifest": str(LEGACY_H8_MANIFEST),
        "legacy_manifest_hash": (
            file_hash(LEGACY_H8_MANIFEST) if LEGACY_H8_MANIFEST.is_file() else None
        ),
        "legacy_checkpoint_hash": (
            file_hash(LEGACY_H8_CHECKPOINT)
            if LEGACY_H8_CHECKPOINT.is_file()
            else None
        ),
        "legacy_training_seed": LEGACY_H8_TRAINING_SEED,
        "legacy_epochs": LEGACY_H8_EPOCHS,
    }


def materialize_h8_sensitivity(
    *,
    root: Path = PROJECT_ROOT,
    output_root: Path = H8_ROOT,
    reuse: bool = True,
) -> dict[str, Any]:
    """Train (or reuse) the Phase-5 H8 lower-capacity sensitivity artifact."""

    output_root = Path(output_root)
    assert_development_path(output_root)
    cache_manifest = read_json(SOURCE_CACHE_MANIFEST)
    cache_key = str(cache_manifest["cache_key"])
    h16_manifest = read_json(H16_MANIFEST)
    scientific = load_config_layers(Path(root) / "configs").scientific
    validate_stage1_contract(scientific)
    hidden_size = h8_hidden_size(scientific)
    shared_hashes = _expected_contract_hashes(h16_manifest)

    if reuse and output_root == H8_ROOT:
        reusable = _reusable_manifest(h16_manifest, cache_key, hidden_size)
        if reusable is not None:
            audit = matched_audit(
                reusable, h16_manifest, hidden_size=hidden_size
            )
            return {
                "status": "REUSED_PHASE5_H8_SENSITIVITY",
                "manifest_path": str(H8_MANIFEST),
                "manifest": reusable,
                "matched_audit": audit,
                "final_test_access_count": 0,
            }

    cohort = read_json(COHORT_PATH)
    if int(cohort.get("final_test_access_count", 0)) != 0:
        raise ContractError("PHASE5_H8_COHORT_FINAL_TEST_ACCESS_VIOLATION")
    cache = _source_cache(cache_manifest)
    train = _cohort_rows(cache, cohort, "train")
    calibration = _cohort_rows(cache, cohort, "calibration")
    _cohort_rows(cache, cohort, "development")

    # The call sequence mirrors the frozen H16 materialization exactly: the
    # pipeline is constructed against the ambient RNG state and only
    # ``lifecycle.train(seed=...)`` re-seeds. This keeps the hidden width the
    # single changed factor instead of introducing a Phase-5 seeding convention.
    pipeline = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES_V2),
        normalization=cache.normalization,
        hidden_size=hidden_size,
        static_input_size=STATIC_FEATURE_COUNT,
        static_normalization=cache.static_normalization,
        history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
    )
    lifecycle = M1Lifecycle(pipeline, device="cpu")
    history = lifecycle.train(
        train,
        epochs=PRIMARY_EPOCHS,
        learning_rate=float(STAGE1_TRAINING_CONFIG["learning_rate"]),
        weight_decay=float(STAGE1_TRAINING_CONFIG["weight_decay"]),
        batch_size=int(STAGE1_TRAINING_CONFIG["batch_size"]),
        bucketed=True,
        seed=PRIMARY_TRAINING_SEED,
        teacher_forcing=True,
    )
    temperatures = lifecycle.calibrate(
        calibration, batch_size=int(STAGE1_TRAINING_CONFIG["batch_size"])
    )
    contracts = {
        name: contract.model_dump(mode="json")
        for name, contract in pipeline.contracts.items()
    }
    target_hash = content_id(contracts)
    if target_hash != h16_manifest.get("target_contract_hash"):
        raise ContractError("PHASE5_H8_TARGET_CONTRACT_HASH_MISMATCH")

    output_root.mkdir(parents=True, exist_ok=True)
    checkpoint = output_root / H8_CHECKPOINT.name
    lifecycle.save(checkpoint)
    calibration_payload = {
        "schema_version": "M1_FORMAL_H16_CALIBRATION_V1",
        "model_version": MODEL_VERSION,
        "model_role": MODEL_ROLE,
        "history_mode": HISTORY_SCOPE,
        "calibration_cohort_hash": cohort["calibration_episode_hash"],
        "calibration_partition": {"start": "2019-07-01", "end": "2019-07-31"},
        "calibration_protocol": pipeline.calibration_contract.model_dump(mode="json"),
        "temperatures": temperatures,
        "reused_h32_temperature": False,
        "variant_specific_calibration": True,
        "final_test_access_count": 0,
    }
    calibration_payload["calibration_hash"] = content_id(calibration_payload)
    calibration_path = output_root / "M1_V2_PHASE5_H8_SENSITIVITY_CALIBRATION.json"
    write_json(calibration_path, calibration_payload)

    manifest: dict[str, Any] = {
        "schema_version": "V2_PHASE5_H8_SENSITIVITY_MANIFEST_V1",
        "artifact_status": ARTIFACT_STATUS,
        "model_role": MODEL_ROLE,
        "selection_role": SELECTION_ROLE,
        "model_version": MODEL_VERSION,
        "hidden_size": hidden_size,
        "history_mode": HISTORY_SCOPE,
        "history_contract": {
            "history_mode": HISTORY_SCOPE,
            "history_encoder_enabled": True,
            "future_information": "FORBIDDEN",
            "full_episode_access": "CAUSAL_PREFIX_ONLY",
        },
        "training_seed": PRIMARY_TRAINING_SEED,
        "epochs": PRIMARY_EPOCHS,
        "optimizer": STAGE1_TRAINING_CONFIG["optimizer"],
        "learning_rate": STAGE1_TRAINING_CONFIG["learning_rate"],
        "weight_decay": STAGE1_TRAINING_CONFIG["weight_decay"],
        "batch_size": STAGE1_TRAINING_CONFIG["batch_size"],
        "training_cohort_id": cohort["cohort_id"],
        "training_cohort_hash": cohort["cohort_hash"],
        "train_episode_hash": cohort["train_episode_hash"],
        "calibration_cohort_hash": cohort["calibration_episode_hash"],
        "development_cohort_hash": cohort["development_episode_hash"],
        "target_contract_hash": target_hash,
        "support_contract_hash": shared_hashes["support_contract_hash"],
        "feature_contract_hash": shared_hashes["feature_contract_hash"],
        "scenario_count": int(h16_manifest["scenario_count"]),
        "quantile_grid": list(scientific.parameters["m1_v2_quantile_levels"].value),
        "checkpoint_path": str(checkpoint),
        "checkpoint_hash": file_hash(checkpoint),
        "calibration_path": str(calibration_path),
        "calibration_hash": calibration_payload["calibration_hash"],
        "source_cache_path": str(SOURCE_CACHE),
        "source_cache_key": cache_key,
        "source_cache_hash": cache_manifest.get("cache_hash"),
        "formal_training_contract_source": (
            "model/M1/tuning_stage1.py:STAGE1_TRAINING_CONFIG"
        ),
        "optional_robustness_seeds": list(OPTIONAL_ROBUSTNESS_SEEDS),
        "development_used_for_parameter_selection": False,
        "selection_or_tuning": False,
        "final_test_access_count": 0,
        "paper_result": False,
        "code_commit": _git_head(Path(root)),
        "training": history,
        "calibration_parameters_are_variant_specific": True,
        "legacy_h8_supersession": _legacy_supersession_note(),
        "derived_from": {
            "h16_cache": str(SOURCE_CACHE),
            "h16_cache_key": cache_key,
            "h16_manifest_hash": file_hash(H16_MANIFEST),
            "h16_checkpoint_hash": h16_manifest.get("checkpoint_hash"),
            "matched_factor": "HIDDEN_SIZE_ONLY",
        },
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / H8_MANIFEST.name
    write_json(manifest_path, manifest)
    audit = matched_audit(manifest, h16_manifest, hidden_size=hidden_size)
    return {
        "status": "TRAINED_PHASE5_H8_SENSITIVITY",
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "matched_audit": audit,
        "final_test_access_count": 0,
    }


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - env only
        return "UNKNOWN"


__all__ = [
    "ARTIFACT_STATUS",
    "CONTRACT_KEYS",
    "HISTORY_SCOPE",
    "LEGACY_H8_MANIFEST",
    "MODEL_ROLE",
    "MODEL_VERSION",
    "SELECTION_ROLE",
    "h8_hidden_size",
    "matched_audit",
    "materialize_h8_sensitivity",
]
