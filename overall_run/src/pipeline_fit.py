from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .artifacts import save_model_artifacts
from .config import RunConfig
from .failures import FormalRunBlocked
from .input import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    SENSITIVITY_TARGET_COLUMN,
)
from .m1 import fit_m1
from .m2 import fit_m2
from .m3 import generate_m3_library, load_actions
from .m4 import fit_m4
from .pipeline_data import (
    filter_training_features,
    flight_weights,
    role_mask,
    set_model_attrs,
    stable_scale_frame,
)
from .progress import Progress
from .utils import stable_hash


def fit_artifacts(
    cfg: RunConfig,
    tables: dict[str, pd.DataFrame],
    model_frame: pd.DataFrame,
    features: list[str],
    numeric: list[str],
    categorical: list[str],
    artifact_root: Path,
    progress: Progress,
    *,
    mode: str,
    formal_target_definition_hash: str,
    test_label_hash: str,
) -> tuple[Any, Any, Any, Any, pd.DataFrame, pd.DataFrame]:
    """Fit and persist the M1-M4 artifact set in frozen stage order."""
    roles = cfg.scientific["cohort"]["roles"]
    train = model_frame[
        role_mask(model_frame["split"], roles["train"])
        & model_frame["target"].notna()
    ].copy()
    validation = model_frame[
        role_mask(model_frame["split"], roles["validation"])
        & model_frame["target"].notna()
    ].copy()
    if train.empty or validation.empty:
        raise FormalRunBlocked(
            f"TRAIN_OR_VALIDATION_EMPTY: train={len(train)}, validation={len(validation)}"
        )
    train["flight_weight"] = flight_weights(train)
    validation["flight_weight"] = flight_weights(validation)
    features, numeric, categorical, feature_audit = filter_training_features(
        train, features, numeric, categorical
    )
    train = set_model_attrs(train, features, numeric, categorical)
    validation = set_model_attrs(validation, features, numeric, categorical)

    maximum_tuning_rows = int(cfg.compute["m1_tuning"]["max_snapshots"])
    if len(train) > maximum_tuning_rows:
        selection = train.copy()
        selection["anchor_date"] = selection["decision_time"].dt.date.astype(str)
        flight_level = selection.groupby("flight_id", as_index=False).agg(
            airport=("airport", "first"),
            anchor_date=("anchor_date", "first"),
            outcome=("target", "median"),
            snapshot_count=("snapshot_id", "count"),
        )
        try:
            flight_level["outcome_stratum"] = pd.qcut(
                flight_level["outcome"].rank(method="first"),
                5,
                labels=["q1", "q2", "q3", "q4", "q5"],
                duplicates="drop",
            ).astype(str)
        except ValueError:
            flight_level["outcome_stratum"] = "all"
        flight_level["selection_key"] = flight_level["flight_id"].map(
            lambda flight_id: stable_hash(
                cfg.compute["random_seed"], "m1_tuning", flight_id
            )
        )
        target_flights = max(
            1,
            int(
                maximum_tuning_rows
                / max(float(flight_level["snapshot_count"].mean()), 1.0)
            ),
        )
        parts = []
        groups = flight_level.groupby(
            ["airport", "anchor_date", "outcome_stratum"],
            dropna=False,
            sort=True,
        )
        total = max(len(flight_level), 1)
        for _, group in groups:
            quota = max(1, round(target_flights * len(group) / total))
            parts.append(
                group.sort_values("selection_key", kind="mergesort").head(quota)
            )
        selected_frame = (
            pd.concat(parts, ignore_index=True)
            .sort_values("selection_key", kind="mergesort")
            .head(target_flights)
        )
        tune_train = train[
            train["flight_id"].isin(set(selected_frame["flight_id"]))
        ].copy()
    else:
        tune_train = train.copy()
    tune_train = set_model_attrs(tune_train, features, numeric, categorical)

    progress.stage(4, 10, "Tune and fit M1")
    final_train = tune_train if mode == "fast" else train
    final_train = set_model_attrs(final_train, features, numeric, categorical)
    m1, tuning = fit_m1(
        final_train,
        validation,
        cfg.scientific,
        cfg.compute,
        progress,
        tuning_train=tune_train,
        fast=mode == "fast",
        excluded_all_missing_features=feature_audit.loc[
            feature_audit["status"] == "excluded_all_missing_train", "feature"
        ].astype(str).tolist(),
        training_nonmissing_counts=dict(
            zip(
                feature_audit["feature"].astype(str),
                feature_audit["training_nonmissing"].astype(int),
            )
        ),
    )
    m1.formal_target_definition_hash = str(formal_target_definition_hash)
    m1.training_label_hash = stable_hash(
        final_train[["snapshot_id", "target"]]
        .sort_values("snapshot_id")
        .to_dict("records")
    )
    m1.validation_label_hash = stable_hash(
        validation[["snapshot_id", "target"]]
        .sort_values("snapshot_id")
        .to_dict("records")
    )
    m1.test_label_hash = str(test_label_hash)
    m1.model_parameter_hash = stable_hash(m1.selected_config)
    m1.feature_schema_hash = m1.feature_contract.contract_hash
    m1.feature_contract_version = str(
        cfg.scientific["m1"].get(
            "feature_contract_version", "M1_PREVIOUS_LEG_V1"
        )
    )
    excluded = set(m1.excluded_all_missing_features)
    feature_audit.loc[
        feature_audit["feature"].astype(str).isin(excluded), "status"
    ] = "excluded_all_missing_model_train"

    progress.stage(5, 10, "Fit M2 quantities and common-unit conversion")
    m2 = fit_m2(train, cfg.scientific)
    scale_sample = stable_scale_frame(train, cfg, mode)
    scale_sample = set_model_attrs(scale_sample, features, numeric, categorical)
    scale_samples = int(cfg.compute.get("m2_unit_scale", {}).get("formal_samples", 256))
    scale_prediction = m1.predict_distribution(
        scale_sample,
        n_samples=scale_samples,
        base_seed=int(cfg.compute["random_seed"]),
    )
    m2.fit_unit_scales(scale_sample, scale_prediction["samples"])

    progress.stage(6, 10, "Freeze M3 responses and M4 decision contract")
    actions = load_actions(cfg.scientific)
    formal_samples = int(cfg.mode(mode)["formal_samples"])
    m3 = generate_m3_library(
        actions=actions,
        n_samples=formal_samples,
        base_seed=int(cfg.compute["random_seed"]),
        scientific=cfg.scientific,
    )
    m4 = fit_m4(cfg.scientific)
    save_model_artifacts(artifact_root, m1=m1, m2=m2, m3=m3, m4=m4)
    (artifact_root / "model_contract.json").write_text(
        json.dumps({
            "contract_version": cfg.contract_version,
            "formal_target_column": FORMAL_TARGET_COLUMN,
            "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
            "formal_target_definition_hash": m1.formal_target_definition_hash,
            "observed_outcome_source": FORMAL_TARGET_COLUMN,
            "sensitivity_target_column": SENSITIVITY_TARGET_COLUMN,
            "training_label_hash": m1.training_label_hash,
            "validation_label_hash": m1.validation_label_hash,
            "test_label_hash": m1.test_label_hash,
            "model_parameter_hash": m1.model_parameter_hash,
            "feature_schema_hash": m1.feature_schema_hash,
            "m1_feature_contract_version": m1.feature_contract_version,
            "feature_columns": m1.feature_columns,
            "feature_contract": m1.feature_contract.to_dict(),
            "predecessor_feature_columns": [
                column
                for column in m1.feature_columns
                if column.startswith("predecessor_")
                or column
                in {
                    "has_predecessor_candidate",
                    "has_supported_predecessor",
                    "observed_ground_gap_minutes",
                    "ground_gap_deviation_from_reference",
                    "airport_continuity",
                    "turnaround_pressure_proxy",
                    "continuation_risk_proxy",
                    "previous_leg_observation_quality",
                }
            ],
            "excluded_all_missing_features": m1.excluded_all_missing_features,
            "m2_passenger_proxy_supported": m2.passenger_proxy_supported,
            "m2_unit_scales": m2.unit_scales,
            "m2_unit_scale_support": m2.unit_scale_support,
            "m2_unit_scale_rows": int(len(scale_sample)),
            "m3_parameter_hash": m3.parameter_hash,
            "m3_sample_hash": m3.sample_hash,
            "m4_available": bool(getattr(m4, "available", True)),
        }, indent=2),
        encoding="utf-8",
    )
    return m1, m2, m3, m4, tuning, feature_audit
