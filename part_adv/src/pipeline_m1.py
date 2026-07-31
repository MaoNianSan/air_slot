from __future__ import annotations

from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from lightgbm import LGBMRegressor
from scipy.stats import norm
from sklearn.tree import DecisionTreeRegressor

try:
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
except ModuleNotFoundError:
    NGBRegressor = None
    Normal = None
try:
    from quantile_forest import RandomForestQuantileRegressor
except ModuleNotFoundError:
    RandomForestQuantileRegressor = None

from .pipeline_common import (
    FORMAL_TARGET_COLUMN,
    MODELS,
    PROJECT,
    _RunTelemetry,
    _seed,
    validate_m1_target_mapping,
)
from .pipeline_inputs import (
    _calibrate_quantiles,
    _confusion,
    _crps,
    _formal_quantiles,
    _matrix,
    _model_frame,
    _weighted_quantile,
)


def _m1(
    cfg: dict[str, Any], cohort: pd.DataFrame, telemetry: _RunTelemetry
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validate_m1_target_mapping({model: FORMAL_TARGET_COLUMN for model in MODELS})
    frame = _model_frame(cfg, cohort)
    evaluation_ids = set(cohort["snapshot_id"].astype(str))
    evaluation = frame[frame["snapshot_id"].astype(str).isin(evaluation_ids)].copy().sort_values("snapshot_id")
    train = frame[frame["split"].eq("train")].copy().sort_values(["anchor_date", "flight_id", "snapshot_id"])
    validation = frame[frame["split"].eq("validation")].copy().sort_values("snapshot_id")
    if set(train["flight_id"]) & set(validation["flight_id"]) or set(train["flight_id"]) & set(evaluation["flight_id"]):
        raise ValueError("M1_SPLIT_FLIGHT_OVERLAP")
    default = yaml.safe_load((PROJECT / "overall_run" / "config" / "default.yaml").read_text(encoding="utf-8"))
    features = [name for name in default["m1"]["feature_allowlist"] if name in frame and train[name].notna().any()]
    x_train, medians = _matrix(train, features)
    x_validation, _ = _matrix(validation, features, medians)
    x_evaluation, _ = _matrix(evaluation, features, medians)
    y_train = train["observed_outcome"].to_numpy(float)
    weights = train["sample_weight"].to_numpy(float)
    upstream_prediction_table = pd.read_parquet(
        cfg["upstream"] / "metrics" / "m1_predictions_evaluation.parquet"
    )
    scientific = yaml.safe_load(
        (PROJECT / "overall_run" / "config" / "scientific.yaml").read_text(encoding="utf-8")
    )
    quantiles, upstream_quantile_columns = _formal_quantiles(scientific, upstream_prediction_table.columns)
    sample_count = cfg["samples"]
    model_info: dict[str, Any] = {}

    def historical_raw(target: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
        rows, levels = [], []
        for record in target.itertuples(index=False):
            mask = train["airport_id"].eq(record.airport_id) & train["snapshot_stage"].eq(record.snapshot_stage)
            level = "airport_stage"
            if int(mask.sum()) < 20:
                mask = np.ones(len(train), dtype=bool)
                level = "global_explicit"
            rows.append(_weighted_quantile(train.loc[mask, "observed_outcome"].to_numpy(float), quantiles, weights[mask]))
            levels.append(level)
        return np.vstack(rows), levels

    def build_hist() -> dict[str, Any]:
        hist_validation, _ = historical_raw(validation)
        hist_evaluation, hist_fallback = historical_raw(evaluation)
        hist_cal, hist_levels, hist_info = _calibrate_quantiles(
            hist_validation, validation, hist_evaluation, evaluation, quantiles
        )
        return {
            "calibrated": hist_cal,
            "levels": hist_levels,
            "info": hist_info,
            "fallback": hist_fallback,
        }

    hist_result = telemetry.model_step(1, "HIST", len(train) + len(validation) + len(evaluation), build_hist)
    hist_cal = hist_result["calibrated"]
    hist_levels = hist_result["levels"]
    hist_info = hist_result["info"]
    hist_fallback = hist_result["fallback"]
    model_info["HIST"] = {"calibration": hist_info, "fallback": hist_fallback}

    def build_qrf() -> dict[str, Any]:
        if RandomForestQuantileRegressor is None:
            raise RuntimeError("quantile-forest is required for the QRF candidate")
        qrf = RandomForestQuantileRegressor(
            n_estimators=int(cfg["m1"][f"qrf_estimators_{cfg['compute_mode']}"]),
            max_depth=12,
            min_samples_leaf=30,
            max_features=0.75,
            n_jobs=1,
            random_state=_seed(cfg["base_seed"], "QRF"),
        )
        qrf.fit(x_train, y_train, sample_weight=weights)
        qrf_validation = np.asarray(
            qrf.predict(x_validation, quantiles=quantiles.tolist(), interpolation="linear")
        )
        qrf_evaluation = np.asarray(
            qrf.predict(x_evaluation, quantiles=quantiles.tolist(), interpolation="linear")
        )
        qrf_cal, qrf_levels, qrf_info = _calibrate_quantiles(
            qrf_validation, validation, qrf_evaluation, evaluation, quantiles
        )
        return {"model": qrf, "calibrated": qrf_cal, "levels": qrf_levels, "info": qrf_info}

    qrf_result = telemetry.model_step(2, "QRF", len(train) + len(validation) + len(evaluation), build_qrf)
    qrf = qrf_result["model"]
    qrf_cal = qrf_result["calibrated"]
    qrf_levels = qrf_result["levels"]
    qrf_info = qrf_result["info"]
    model_info["QRF"] = {"calibration": qrf_info}

    def build_ngb() -> dict[str, Any]:
        if NGBRegressor is None or Normal is None:
            raise RuntimeError("ngboost is required for the NGB candidate")
        ngb = NGBRegressor(
            Dist=Normal,
            Base=DecisionTreeRegressor(
                max_depth=2, min_samples_leaf=20, random_state=_seed(cfg["base_seed"], "NGB_TREE")
            ),
            n_estimators=int(cfg["m1"][f"ngb_estimators_{cfg['compute_mode']}"]),
            learning_rate=0.03,
            minibatch_frac=0.8,
            col_sample=0.8,
            verbose=False,
            random_state=_seed(cfg["base_seed"], "NGB"),
        )
        ngb.fit(x_train, y_train, sample_weight=weights)
        ngb_validation_dist = ngb.pred_dist(x_validation)
        ngb_evaluation_dist = ngb.pred_dist(x_evaluation)
        ngb_validation = np.asarray(ngb_validation_dist.loc)[:, None] + np.maximum(
            np.asarray(ngb_validation_dist.scale), 1e-6
        )[:, None] * norm.ppf(quantiles)[None, :]
        ngb_evaluation = np.asarray(ngb_evaluation_dist.loc)[:, None] + np.maximum(
            np.asarray(ngb_evaluation_dist.scale), 1e-6
        )[:, None] * norm.ppf(quantiles)[None, :]
        ngb_cal, ngb_levels, ngb_info = _calibrate_quantiles(
            ngb_validation, validation, ngb_evaluation, evaluation, quantiles
        )
        return {"model": ngb, "calibrated": ngb_cal, "levels": ngb_levels, "info": ngb_info}

    ngb_result = telemetry.model_step(3, "NGB", len(train) + len(validation) + len(evaluation), build_ngb)
    ngb = ngb_result["model"]
    ngb_cal = ngb_result["calibrated"]
    ngb_levels = ngb_result["levels"]
    ngb_info = ngb_result["info"]
    model_info["NGB"] = {"calibration": ngb_info}

    upstream_prediction = upstream_prediction_table.set_index("snapshot_id")
    def build_prop() -> dict[str, Any]:
        prop_cal = upstream_prediction.reindex(evaluation["snapshot_id"])[upstream_quantile_columns].to_numpy(float)
        prop_levels = upstream_prediction.reindex(evaluation["snapshot_id"])["calibration_level"].astype(str).tolist()
        prop_info = {
            "raw_crossing": np.zeros(len(evaluation), bool),
            "repair_magnitude": np.zeros(len(evaluation)),
        }
        return {"calibrated": prop_cal, "levels": prop_levels, "info": prop_info}

    prop_result = telemetry.model_step(4, "PROP", len(evaluation), build_prop)
    prop_cal = prop_result["calibrated"]
    prop_levels = prop_result["levels"]
    prop_info = prop_result["info"]
    model_info["PROP"] = {"calibration": prop_info}

    def build_point() -> dict[str, Any]:
        oof_residuals: list[float] = []
        dates = sorted(train["anchor_date"].unique())
        for date in dates[1:]:
            past = train[train["anchor_date"] < date]
            hold = train[train["anchor_date"] == date]
            if past.empty or hold.empty:
                continue
            x_past, _ = _matrix(past, features, medians)
            x_hold, _ = _matrix(hold, features, medians)
            model = LGBMRegressor(
                n_estimators=int(cfg["m1"][f"point_estimators_{cfg['compute_mode']}"]),
                num_leaves=15,
                verbosity=-1,
                n_jobs=1,
                random_state=_seed(cfg["base_seed"], "POINT_OOF", date),
            )
            model.fit(x_past, past["observed_outcome"], sample_weight=past["sample_weight"])
            oof_residuals.extend((hold["observed_outcome"].to_numpy(float) - model.predict(x_hold)).tolist())
        if len(oof_residuals) < 20:
            raise ValueError("POINT_OOF_RESIDUAL_SUPPORT_INSUFFICIENT")
        point = LGBMRegressor(
            n_estimators=int(cfg["m1"][f"point_estimators_{cfg['compute_mode']}"]),
            num_leaves=15,
            verbosity=-1,
            n_jobs=1,
            random_state=_seed(cfg["base_seed"], "POINT_FINAL"),
        )
        point.fit(x_train, y_train, sample_weight=weights)
        residual_quantiles = np.quantile(np.asarray(oof_residuals), quantiles)
        point_validation = point.predict(x_validation)[:, None] + residual_quantiles
        point_evaluation = point.predict(x_evaluation)[:, None] + residual_quantiles
        point_cal, point_levels, point_info = _calibrate_quantiles(
            point_validation, validation, point_evaluation, evaluation, quantiles
        )
        return {
            "model": point,
            "calibrated": point_cal,
            "levels": point_levels,
            "info": point_info,
            "oof_residual_count": len(oof_residuals),
        }

    point_result = telemetry.model_step(
        5, "POINT_OOF", len(train) + len(validation) + len(evaluation), build_point
    )
    point = point_result["model"]
    point_cal = point_result["calibrated"]
    point_levels = point_result["levels"]
    point_info = point_result["info"]
    oof_residual_count = int(point_result["oof_residual_count"])
    model_info["POINT_OOF"] = {"calibration": point_info}

    quantile_blocks = {
        "HIST": (hist_cal, hist_levels),
        "QRF": (qrf_cal, qrf_levels),
        "NGB": (ngb_cal, ngb_levels),
        "PROP": (prop_cal, prop_levels),
        "POINT_OOF": (point_cal, point_levels),
    }
    sample_blocks = {
        model: np.asarray(
            [
                np.interp(
                    np.random.default_rng(_seed(cfg["base_seed"], "M1_SAMPLE", model, snapshot_id)).uniform(size=sample_count),
                    quantiles,
                    row,
                    left=row[0],
                    right=row[-1],
                )
                for snapshot_id, row in zip(evaluation["snapshot_id"], matrix)
            ]
        )
        for model, (matrix, _) in quantile_blocks.items()
    }
    upstream_samples = pd.read_parquet(cfg["upstream"] / "m1_predictive_samples" / "part.parquet")
    upstream_samples = upstream_samples[
        upstream_samples["snapshot_id"].isin(evaluation["snapshot_id"])
        & upstream_samples["sample_id"].lt(sample_count)
    ]
    prop_matrix = upstream_samples.pivot(index="snapshot_id", columns="sample_id", values="sample_value").reindex(
        evaluation["snapshot_id"]
    )
    if prop_matrix.shape != (len(evaluation), sample_count) or prop_matrix.isna().any().any():
        raise ValueError("PROP_UPSTREAM_SAMPLE_CONTRACT_MISMATCH")
    sample_blocks["PROP"] = prop_matrix.to_numpy(float)

    outcomes = evaluation["observed_outcome"].to_numpy(float)
    frozen_tail = float(validation["observed_outcome"].quantile(0.95))
    prediction_rows, metric_rows, sample_rows = [], [], []
    for model, samples in sample_blocks.items():
        qmatrix, calibration_levels = quantile_blocks[model]
        means = samples.mean(axis=1)
        probabilities = (samples > 15).mean(axis=1)
        triggers = probabilities >= float(default["m1"]["trigger_probability_threshold"])
        crps = _crps(samples, outcomes)
        for index, record in enumerate(evaluation.itertuples(index=False)):
            row = {
                "model_id": model,
                "episode_id": record.episode_id,
                "flight_id": record.flight_id,
                "snapshot_id": record.snapshot_id,
                "anchor_date": record.anchor_date,
                "airport_id": record.airport_id,
                "snapshot_stage": record.snapshot_stage,
                "observed_outcome": outcomes[index],
                "predictive_mean": means[index],
                "trigger_probability": probabilities[index],
                "trigger_decision": bool(triggers[index]),
                "crps": crps[index],
                "fallback_level": hist_fallback[index] if model == "HIST" else "NONE",
                "calibration_level": calibration_levels[index],
            }
            row.update({f"q_{q:g}": float(qmatrix[index, q_index]) for q_index, q in enumerate(quantiles)})
            prediction_rows.append(row)
            sample_rows.extend(
                {
                    "model_id": model,
                    "snapshot_id": record.snapshot_id,
                    "sample_id": sample_id,
                    "sample_value": float(value),
                }
                for sample_id, value in enumerate(samples[index])
            )
        tail = outcomes >= frozen_tail
        lower = np.quantile(samples, 0.05, axis=1)
        upper = np.quantile(samples, 0.95, axis=1)
        errors = means - outcomes
        metric_rows.append(
            {
                "model_id": model,
                "mean_error": float(errors.mean()),
                "mae": float(np.mean(np.abs(errors))),
                "rmse": float(np.sqrt(np.mean(errors**2))),
                "crps": float(crps.mean()),
                "twcrps": float(np.average(crps, weights=np.where(tail, 5.0, 1.0))),
                "coverage_90": float(np.mean((outcomes >= lower) & (outcomes <= upper))),
                "frozen_tail_threshold": frozen_tail,
                "frozen_tail_count": int(tail.sum()),
                "frozen_tail_coverage_90": float(np.mean((outcomes[tail] >= lower[tail]) & (outcomes[tail] <= upper[tail]))),
                "evaluation_rows": len(evaluation),
                "formal_ranking": model != "POINT_OOF",
                **_confusion(outcomes, triggers),
            }
        )
    joblib.dump(
        {
            "qrf": qrf,
            "ngb": ngb,
            "point": point,
            "features": features,
            "medians": medians.to_dict(),
            "quantiles": quantiles,
            "point_oof_residual_count": oof_residual_count,
        },
        cfg["output"] / "m1_models.joblib",
    )
    return pd.DataFrame(prediction_rows), pd.DataFrame(sample_rows), pd.DataFrame(metric_rows), frame


