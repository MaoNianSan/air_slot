from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import warnings
from concurrent.futures import ThreadPoolExecutor
import time
from lightgbm import LGBMRegressor, early_stopping, log_evaluation
from sklearn.compose import ColumnTransformer

from .input import FORMAL_TARGET_COLUMN, FORMAL_TARGET_CONTRACT_VERSION
from .m1_baseline import HistoricalBaseline
from .m1_calibration import (
    apply_residual_calibration,
    fit_residual_calibration,
    monotone_quantiles,
)
from .m1_metrics import (
    approximate_crps,
    exceedance_probability_from_quantiles,
    pinball_loss,
)
from .m1_feature_contract import M1FeatureContract
from .m1_sampling import inverse_quantile_sample
from .m1_training import (
    blocked_folds,
    make_quantile_regressor,
    make_transformer,
    prepare_model_frame,
)
from .progress import Progress
from .utils import stable_seed


@dataclass
class M1Artifact:
    quantiles: list[float]
    feature_columns: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]
    feature_contract: M1FeatureContract
    transformer: ColumnTransformer
    models: dict[float, LGBMRegressor]
    calibration_offsets: dict[str, dict[Any, np.ndarray]]
    calibration_min_support: int
    baseline: HistoricalBaseline
    selected_config_id: str
    selected_config: dict[str, Any]
    excluded_all_missing_features: list[str] = field(default_factory=list)
    training_nonmissing_counts: dict[str, int] = field(default_factory=dict)
    target_column: str = FORMAL_TARGET_COLUMN
    formal_target_contract_version: str = FORMAL_TARGET_CONTRACT_VERSION
    formal_target_definition_hash: str = ""
    training_label_hash: str = ""
    validation_label_hash: str = ""
    test_label_hash: str = ""
    model_parameter_hash: str = ""
    feature_schema_hash: str = ""
    feature_contract_version: str = "M1_PREVIOUS_LEG_V1"

    def _transform(self, df: pd.DataFrame):
        self.feature_contract.validate_artifact_columns(
            self.feature_columns,
            self.categorical_columns,
        )
        return self.transformer.transform(
            self.feature_contract.select_authoritative(df)
        )

    def raw_quantiles(self, df: pd.DataFrame) -> np.ndarray:
        X = self._transform(df)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            return np.column_stack([self.models[float(t)].predict(X) for t in self.quantiles])

    def calibrated_quantiles(self, df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
        return apply_residual_calibration(
            self.raw_quantiles(df),
            df,
            self.calibration_offsets,
            np.asarray(self.quantiles),
        )

    def predict_quantiles_only(self, df: pd.DataFrame) -> dict[str, Any]:
        raw_qmat = self.raw_quantiles(df)
        qmat, levels = self.calibrated_quantiles(df)
        quantiles = np.asarray(self.quantiles, dtype=float)
        window_col = next((c for c in ["execution_window_margin", "m_window", "window_margin"] if c in df.columns), None)
        pwin = np.full(len(df), np.nan, dtype=float)
        if window_col:
            margins = pd.to_numeric(df[window_col], errors="coerce").to_numpy(float)
            finite = np.isfinite(margins)
            for i in np.flatnonzero(finite):
                pwin[i] = exceedance_probability_from_quantiles(qmat[i:i + 1], quantiles, float(margins[i]))[0]
        return {
            "raw_quantiles": raw_qmat,
            "quantiles": qmat,
            "p_exceed_15": exceedance_probability_from_quantiles(qmat, quantiles, 15.0),
            "p_window": pwin,
            "calibration_level": levels,
        }

    def predict_distribution(self, df: pd.DataFrame, n_samples: int, base_seed: int) -> dict[str, Any]:
        raw_qmat = self.raw_quantiles(df)
        qmat, levels = self.calibrated_quantiles(df)
        quantiles = np.asarray(self.quantiles, dtype=float)
        seeds = np.asarray([
            stable_seed(base_seed, row.flight_id, row.snapshot_id, "m1_samples")
            for row in df[["flight_id", "snapshot_id"]].itertuples(index=False)
        ])
        samples = inverse_quantile_sample(qmat, quantiles, n_samples, seeds)
        p15 = exceedance_probability_from_quantiles(qmat, quantiles, 15.0)
        window_col = next((c for c in ["execution_window_margin", "m_window", "window_margin"] if c in df.columns), None)
        if window_col:
            margins = pd.to_numeric(df[window_col], errors="coerce").to_numpy(float)
            pwin = np.full(len(df), np.nan, dtype=float)
            finite = np.isfinite(margins)
            for i in np.flatnonzero(finite):
                pwin[i] = exceedance_probability_from_quantiles(
                    qmat[i : i + 1], quantiles, float(margins[i])
                )[0]
        else:
            pwin = np.full(len(df), np.nan)
        return {
            "raw_quantiles": raw_qmat,
            "quantiles": qmat,
            "samples": samples,
            "sample_ids": np.arange(n_samples, dtype=np.int32),
            "sample_seeds": seeds.astype(np.uint64),
            "p_exceed_15": p15,
            "p_window": pwin,
            "calibration_level": levels,
        }


def fit_m1(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    scientific: dict[str, Any],
    compute: dict[str, Any],
    progress: Progress,
    *,
    tuning_train: pd.DataFrame | None = None,
    fast: bool = False,
    excluded_all_missing_features: list[str] | None = None,
    training_nonmissing_counts: dict[str, int] | None = None,
) -> tuple[M1Artifact, pd.DataFrame]:
    quantiles = [float(x) for x in scientific["m1"]["quantiles"]]
    tuning_quantiles = [float(x) for x in scientific["m1"]["tuning_quantiles"]]
    tuning_cfg = compute["m1_tuning"]
    workers = int(compute.get("inner_model_threads", compute.get("workers", 1)))
    outer_workers = int(compute.get("outer_workers", 1))
    configs = list(tuning_cfg["curated_configs"])
    if fast:
        configs = configs[:1]

    feature_columns = list(train.attrs["feature_columns"])
    numeric = list(train.attrs["numeric_columns"])
    categorical = list(train.attrs["categorical_columns"])
    selection = tuning_train if tuning_train is not None else train
    selection = selection.copy()
    selection.attrs.update(train.attrs)
    y_selection = selection["target"].to_numpy(float)
    weights_selection = selection["flight_weight"].to_numpy(float)
    folds = blocked_folds(selection)

    rows: list[dict[str, Any]] = []
    best_iterations: dict[tuple[str, float], list[int]] = {}
    tuning_taus = np.asarray(tuning_quantiles, dtype=float)

    for cfg in progress.iter(configs, desc="M1 tuning configs", total=len(configs)):
        for fold_id, (tr, va) in enumerate(folds, start=1):
            fold_numeric = [c for c in numeric if selection.iloc[tr][c].notna().any()]
            fold_categorical = [c for c in categorical if selection.iloc[tr][c].notna().any()]
            fold_features = fold_numeric + fold_categorical
            if not fold_features:
                raise RuntimeError(f"M1_FOLD_FEATURES_ALL_MISSING:{fold_id}")
            fold_transformer = make_transformer(fold_numeric, fold_categorical)
            X_tr = fold_transformer.fit_transform(selection.iloc[tr][fold_features])
            X_va = fold_transformer.transform(selection.iloc[va][fold_features])
            def fit_tuning_quantile(tau: float) -> tuple[float, np.ndarray, int, float]:
                model = make_quantile_regressor(
                    cfg,
                    tau,
                    int(tuning_cfg["max_estimators"]),
                    stable_seed(cfg["id"], fold_id, tau),
                    workers,
                )
                model.fit(
                    X_tr,
                    y_selection[tr],
                    sample_weight=weights_selection[tr],
                    eval_set=[(X_va, y_selection[va])],
                    eval_metric="quantile",
                    callbacks=[
                        early_stopping(int(tuning_cfg["early_stopping_rounds"]), verbose=False),
                        log_evaluation(0),
                    ],
                )
                started = time.perf_counter()
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="X does not have valid feature names")
                    pred_tau = model.predict(X_va)
                elapsed = time.perf_counter() - started
                return tau, pred_tau, int(model.best_iteration_ or model.n_estimators), elapsed

            if outer_workers > 1 and len(tuning_quantiles) > 1:
                with ThreadPoolExecutor(max_workers=min(outer_workers, len(tuning_quantiles))) as executor:
                    tuning_results = list(executor.map(fit_tuning_quantile, tuning_quantiles))
            else:
                tuning_results = [fit_tuning_quantile(tau) for tau in tuning_quantiles]
            fold_predictions = []
            prediction_seconds = 0.0
            for tau, pred_tau, best_iteration, elapsed in tuning_results:
                fold_predictions.append(pred_tau)
                prediction_seconds += elapsed
                best_iterations.setdefault((cfg["id"], tau), []).append(best_iteration)

            qmat = monotone_quantiles(np.column_stack(fold_predictions), tuning_taus)
            crps_proxy = float(
                np.average(approximate_crps(y_selection[va], qmat, tuning_taus), weights=weights_selection[va])
            )
            p15 = exceedance_probability_from_quantiles(qmat, tuning_taus, 15.0)
            event = (y_selection[va] > 15.0).astype(float)
            brier = float(np.average((p15 - event) ** 2, weights=weights_selection[va]))
            coverage = float(
                np.average(
                    (y_selection[va] >= qmat[:, 0]) & (y_selection[va] <= qmat[:, -1]),
                    weights=weights_selection[va],
                )
            )
            target_coverage = float(tuning_taus[-1] - tuning_taus[0])
            rows.append(
                {
                    "config_id": cfg["id"],
                    "fold": fold_id,
                    "crps_proxy": crps_proxy,
                    "brier15": brier,
                    "coverage": coverage,
                    "coverage_error": abs(coverage - target_coverage),
                    "prediction_ms_per_snapshot": 1000.0 * prediction_seconds / max(len(va), 1),
                    "num_leaves": int(cfg["num_leaves"]),
                    "max_depth": int(cfg["max_depth"]),
                }
            )

    tuning = pd.DataFrame(rows)
    score = (
        tuning.groupby("config_id", as_index=False)
        .agg(
            crps_proxy=("crps_proxy", "mean"),
            brier15=("brier15", "mean"),
            coverage_error=("coverage_error", "mean"),
            prediction_ms_per_snapshot=("prediction_ms_per_snapshot", "max"),
            num_leaves=("num_leaves", "first"),
            max_depth=("max_depth", "first"),
        )
    )
    best_crps = float(score["crps_proxy"].min())
    tolerance = float(tuning_cfg.get("tie_relative_tolerance", 0.005))
    near = score[score["crps_proxy"] <= best_crps * (1.0 + tolerance)].copy()
    near["complexity_depth"] = near["max_depth"].replace(-1, 10_000)
    near = near.sort_values(
        [
            "brier15",
            "coverage_error",
            "prediction_ms_per_snapshot",
            "num_leaves",
            "complexity_depth",
            "config_id",
        ],
        kind="mergesort",
    )
    selected_id = str(near.iloc[0]["config_id"])
    selected = next(c for c in configs if c["id"] == selected_id)
    progress.summary(f"M1 selected config: {selected_id}")

    # Final preprocessing and all formal quantile models are fitted on the complete
    # allowed training partition after selection.
    final_numeric = [c for c in numeric if train[c].notna().any()]
    final_categorical = [c for c in categorical if train[c].notna().any()]
    final_features = final_numeric + final_categorical
    additionally_excluded = [c for c in feature_columns if c not in final_features]
    if not final_features:
        raise RuntimeError("M1_FINAL_FEATURES_ALL_MISSING")
    contract_version = str(
        scientific["m1"].get("feature_contract_version", "M1_PREVIOUS_LEG_V1")
    )
    feature_contract = M1FeatureContract.build(
        train,
        final_features,
        final_categorical,
        contract_version=contract_version,
    )
    y_all = train["target"].to_numpy(float)
    weights_all = train["flight_weight"].to_numpy(float)
    transformer = make_transformer(final_numeric, final_categorical)
    X_all = transformer.fit_transform(feature_contract.select_authoritative(train))
    def fit_final_quantile(tau: float) -> tuple[float, LGBMRegressor]:
        if (selected_id, tau) in best_iterations:
            related = best_iterations[(selected_id, tau)]
        else:
            nearest_tau = min(tuning_quantiles, key=lambda x: abs(x - tau))
            related = best_iterations.get((selected_id, nearest_tau), [])
        n_estimators = int(np.median(related)) if related else min(500, int(tuning_cfg["max_estimators"]))
        model = make_quantile_regressor(
            selected,
            tau,
            max(n_estimators, 20),
            stable_seed("final", selected_id, tau),
            workers,
        )
        model.fit(X_all, y_all, sample_weight=weights_all)
        return tau, model

    if outer_workers > 1 and len(quantiles) > 1:
        with ThreadPoolExecutor(max_workers=min(outer_workers, len(quantiles))) as executor:
            final_results = list(executor.map(fit_final_quantile, quantiles))
    else:
        final_results = [
            fit_final_quantile(tau)
            for tau in progress.iter(quantiles, desc="M1 quantile models", total=len(quantiles))
        ]
    models: dict[float, LGBMRegressor] = {tau: model for tau, model in final_results}

    X_val_final = transformer.transform(
        feature_contract.select_authoritative(validation)
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        raw_val = np.column_stack([models[t].predict(X_val_final) for t in quantiles])
    residuals = validation["target"].to_numpy(float)[:, None] - raw_val
    min_support = int(scientific["m1"]["calibration"]["minimum_support"])
    offsets = fit_residual_calibration(
        validation,
        residuals,
        quantiles,
        min_support,
    )

    baseline = HistoricalBaseline(
        quantiles,
        int(scientific["m1"]["historical_baseline"]["minimum_support"]),
    ).fit(train)
    artifact = M1Artifact(
        quantiles=quantiles,
        feature_columns=final_features,
        numeric_columns=final_numeric,
        categorical_columns=final_categorical,
        feature_contract=feature_contract,
        transformer=transformer,
        models=models,
        calibration_offsets=offsets,
        calibration_min_support=min_support,
        baseline=baseline,
        selected_config_id=selected_id,
        selected_config=selected,
        excluded_all_missing_features=sorted(
            set(excluded_all_missing_features or []) | set(additionally_excluded)
        ),
        training_nonmissing_counts=dict(training_nonmissing_counts or {}),
        feature_schema_hash=feature_contract.contract_hash,
        feature_contract_version=feature_contract.contract_version,
    )
    tuning = tuning.merge(score, on="config_id", suffixes=("", "_aggregate"), how="left")
    tuning["selected"] = tuning["config_id"].eq(selected_id)
    return artifact, tuning
