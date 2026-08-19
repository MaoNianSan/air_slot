"""M1 FAST path V2: executable ARX-LightGBM distributional baseline.

The FAST path shares with STATE_AWARE the V2 formal semantics:

- primitive chain T_IB_A00 -> D_OB -> D_TX
- predecessor head: discrete hazard over the INTERNAL remaining-time
  coordinate (``T_IB_REMAINING_HAZARD``; public ``T_IB_A00`` = decision time
  + coordinate)
- successor heads: hurdle + positive conditional quantile, D_TX conditioned
  on the formal D_OB parent
- output schema (``{T_IB_A00: pmf, D_OB: {...}, D_TX: {...}}``) via
  ``conditional_head_summary``
- support schema and V2 scenario schema (``model.M1.scenarios.ancestral_sample_v2``)

Round 2.1 executable architecture (ARX-LightGBM):
- T_IB_REMAINING_HAZARD: one LightGBM binary hazard model per finite bin
- D_OB / D_TX: zero classifier + per-level positive quantile regressors,
  conditioned on the formal parents (T_IB hazard coordinate; D_TX also on the
  formal D_OB minutes)
- fitted models stay DEVELOPMENT_ONLY; ``predict_distributions`` keeps
  ABSTAIN until a train-frozen V2 artifact is registered
  (``final_test_access_count == 0``, no paper promotion).  Synthetic/unit
  training smoke exercises the architecture through ``predict_development``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

import numpy as np

import torch

from model.common.errors import ContractError

from .contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1_V2_HAZARD_COORDINATE,
)
from .pipeline import conditional_head_summary
from .scenarios import ancestral_sample_v2
from .semantics import M1_V2_HAZARD_COORDINATE_TARGET


class M1FastPathStatus(str, Enum):
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    ABSTAIN = "ABSTAIN"


def fast_v2_distribution_schema() -> dict[str, object]:
    """Formal V2 output schema shared by FAST and STATE_AWARE paths."""
    return {
        "T_IB_A00": "hazard_pmf",
        "D_OB": {"zero_probability": "scalar",
                 "positive_quantiles_minutes": "vector"},
        "D_TX": {"zero_probability": "scalar",
                 "positive_quantiles_minutes": "vector"},
    }


@dataclass(frozen=True)
class FastPathContract:
    """Typed V2 contract shared by FAST and STATE_AWARE M1 paths."""

    status: M1FastPathStatus
    feature_semantics: str = "CAUSAL_HISTORY_PREFIX_ONLY"
    target_semantics: str = "T_IB_A00_D_OB_D_TX_HAZARD_HURDLE_QUANTILE_CONTRACTS"
    output_schema: str = "V2_TARGET_KEYED_DISTRIBUTION_SUMMARY"
    support_schema: str = "M1V2_SCENARIO_SUPPORT"
    scenario_schema: str = "M1V2_SCENARIO"
    final_test_access_count: int = 0
    paper_full_run: bool = False


def _require_lightgbm():
    try:
        import lightgbm
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ContractError("M1_FAST_LIGHTGBM_UNAVAILABLE") from exc
    return lightgbm


def _clip_probability(values: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(values, dtype=float), 1e-7, 1.0 - 1e-7)


def _quantile_logits_from_values(values: np.ndarray) -> np.ndarray:
    """Invert the softplus-cumsum parameterization of positive quantiles.

    ``monotone_positive_quantiles(logits) = cumsum(softplus(logits))``; FAST
    regressors emit values directly, so the head returns logits that reproduce
    those values under the shared V2 parameterization (monotone by
    construction after a cumulative-max + positivity clamp).
    """
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array[None, :]
    monotone = np.maximum.accumulate(array, axis=-1)
    monotone = np.clip(monotone, 1e-6, None)
    increments = np.diff(
        np.concatenate([np.zeros_like(monotone[:, :1]), monotone], axis=-1),
        axis=-1,
    )
    increments = np.clip(increments, 1e-6, None)
    return np.log(np.expm1(increments))


def _classifier_logits(classifier, features: np.ndarray) -> torch.Tensor:
    probability = _clip_probability(classifier.predict(features))
    return torch.tensor(np.log(probability / (1.0 - probability)),
                        dtype=torch.float32)


class LightGBMDistributionalPredictor:
    """ARX-lagged LightGBM distributional V2 baseline (DEVELOPMENT_ONLY).

    ``contracts`` maps each V2 INTERNAL target to its typed contract
    (``HazardBinContract`` for T_IB_REMAINING_HAZARD; ``HurdleQuantileContract``
    for D_OB/D_TX).  ``models`` is the fitted architecture:

    - ``T_IB_REMAINING_HAZARD.hazard_models``: one binary classifier per
      finite remaining-time bin (discrete-hazard semantics);
    - ``D_OB`` / ``D_TX``: ``zero`` classifier plus ``quantiles`` per-level
      positive regressors, conditioned on the formal parents.

    Without a registered train-frozen fitted artifact the principal
    ``predict_distributions`` path abstains (``ABSTAIN``) instead of
    fabricating distributions; ``predict_development`` executes the fitted
    architecture for synthetic/unit smoke only.
    """

    def __init__(
        self,
        contracts: Mapping[str, object],
        models: Mapping[str, object] | None = None,
        feature_window: int = 6,
    ):
        self.contracts = dict(contracts)
        self.models = dict(models or {})
        self.feature_window = int(feature_window)
        if self.feature_window < 1:
            raise ValueError("M1_FAST_FEATURE_WINDOW_MUST_BE_POSITIVE")
        missing = set(self._model_spec_keys()) - set(self.models)
        self.status = (
            M1FastPathStatus.DEVELOPMENT_ONLY
            if models is not None and not missing
            else M1FastPathStatus.ABSTAIN
        )

    def _model_spec_keys(self) -> set[str]:
        return {M1_V2_HAZARD_COORDINATE_TARGET, "D_OB", "D_TX"}

    def contract(self) -> FastPathContract:
        return FastPathContract(status=self.status)

    # ------------------------------------------------------------------
    # executable architecture
    # ------------------------------------------------------------------
    def fit(
        self,
        X: np.ndarray,
        targets: Mapping[str, np.ndarray],
        *,
        seed: int = 0,
        n_estimators: int = 32,
    ) -> "LightGBMDistributionalPredictor":
        """Fit the ARX-LightGBM architecture on one bundle (no paper fitting).

        ``targets`` keys are the V2 INTERNAL training-target names:
        - ``T_IB_REMAINING_HAZARD``: remaining minutes (or NaN for inactive);
        - ``D_OB`` / ``D_TX``: nonnegative minutes (or NaN).

        D_OB models condition on the T_IB hazard coordinate; D_TX models also
        condition on the formal D_OB parent minutes.  Rows whose required
        formal parent is missing are excluded from the child model's fit.
        """
        lgbm = _require_lightgbm()
        hazard: HazardBinContract = self.contracts[M1_V2_HAZARD_COORDINATE]
        d_ob: HurdleQuantileContract = self.contracts["D_OB"]
        d_tx: HurdleQuantileContract = self.contracts["D_TX"]
        features = np.asarray(X, dtype=float)
        ib_target = np.asarray(targets.get(M1_V2_HAZARD_COORDINATE_TARGET), dtype=float)
        d_ob_target = np.asarray(targets.get("D_OB"), dtype=float)
        d_tx_target = np.asarray(targets.get("D_TX"), dtype=float)

        def _classifier():
            return lgbm.LGBMClassifier(
                n_estimators=int(n_estimators), num_leaves=7,
                learning_rate=0.1, random_state=int(seed), verbose=-1,
            )

        def _regressor(level: float):
            return lgbm.LGBMRegressor(
                objective="quantile", alpha=float(level),
                n_estimators=int(n_estimators), num_leaves=7,
                learning_rate=0.1, random_state=int(seed), verbose=-1,
            )

        # --- T_IB hazard: one binary model per finite remaining-time bin ---
        ib_valid = ~np.isnan(ib_target)
        ib_bin = np.full(ib_target.shape, -1, dtype=np.int64)
        ib_bin[ib_valid] = np.minimum(
            (np.maximum(0.0, ib_target[ib_valid]) // hazard.bin_width_minutes).astype(
                np.int64),
            hazard.finite_class_count - 1,
        )
        hazard_models = []
        for bin_index in range(hazard.finite_class_count):
            if ib_valid.sum() < 4:
                raise ContractError("M1_FAST_HAZARD_TRAINING_ROWS_INSUFFICIENT")
            y = (ib_bin[ib_valid] == bin_index).astype(np.int32)
            if y.sum() < 1 or (1 - y).sum() < 1:
                # degenerate bin on the tiny smoke set: zero-hazard surrogate
                model = _classifier()
                model.fit(features[ib_valid][:4], np.zeros(4, dtype=np.int32))
            else:
                model = _classifier()
                model.fit(features[ib_valid], y)
            hazard_models.append(model)

        # --- D_OB: zero classifier + positive quantile regressors ---
        ob_valid = ~np.isnan(d_ob_target)
        if ob_valid.sum() < 4:
            raise ContractError("M1_FAST_D_OB_TRAINING_ROWS_INSUFFICIENT")
        ib_parent = np.where(ib_valid, np.maximum(0.0, ib_target), 0.0)
        ob_features = np.concatenate([features, ib_parent[:, None]], axis=-1)
        ob_positive = ob_valid & (d_ob_target > 0)
        ob_zero_model = _classifier()
        ob_zero_model.fit(ob_features[ob_valid], (d_ob_target[ob_valid] == 0).astype(np.int32))
        ob_quantile_models = []
        if ob_positive.sum() < 2:
            raise ContractError("M1_FAST_D_OB_POSITIVE_ROWS_INSUFFICIENT")
        for level in d_ob.quantile_levels:
            model = _regressor(level)
            model.fit(ob_features[ob_positive], d_ob_target[ob_positive])
            ob_quantile_models.append(model)

        # --- D_TX: conditioned on the formal D_OB parent ---
        tx_parent_ok = ob_valid & ~np.isnan(d_tx_target)
        if tx_parent_ok.sum() < 4:
            raise ContractError("M1_FAST_D_TX_TRAINING_ROWS_INSUFFICIENT")
        tx_features = np.concatenate(
            [ob_features, np.where(ob_valid, np.maximum(0.0, d_ob_target), 0.0)[:, None]],
            axis=-1,
        )
        tx_positive = tx_parent_ok & (d_tx_target > 0)
        tx_zero_model = _classifier()
        tx_zero_model.fit(tx_features[tx_parent_ok],
                          (d_tx_target[tx_parent_ok] == 0).astype(np.int32))
        tx_quantile_models = []
        if tx_positive.sum() < 2:
            raise ContractError("M1_FAST_D_TX_POSITIVE_ROWS_INSUFFICIENT")
        for level in d_tx.quantile_levels:
            model = _regressor(level)
            model.fit(tx_features[tx_positive], d_tx_target[tx_positive])
            tx_quantile_models.append(model)

        self.models = {
            M1_V2_HAZARD_COORDINATE_TARGET: {"hazard_models": hazard_models},
            "D_OB": {"zero": ob_zero_model, "quantiles": ob_quantile_models},
            "D_TX": {"zero": tx_zero_model, "quantiles": tx_quantile_models},
        }
        self.status = M1FastPathStatus.DEVELOPMENT_ONLY
        return self

    def _arx_features(self, values: torch.Tensor) -> np.ndarray:
        """Lag matrix from the causal history prefix; never future rows."""
        batch, time, features = values.shape
        window = self.feature_window
        rows = []
        for index in range(batch):
            length = time
            seq = values[index, max(0, length - window):, :]
            if seq.shape[0] < window:
                pad = torch.zeros(window - seq.shape[0], features, dtype=seq.dtype)
                seq = torch.cat((pad, seq), dim=0)
            rows.append(seq.reshape(-1).numpy())
        return np.stack(rows, axis=0)

    def state_representation(self, features: torch.Tensor, static_features=None) -> torch.Tensor:
        """FAST state is the ARX feature matrix itself (identity adapter)."""
        return features

    def _ib_representatives(self, ib_index, batch: int) -> np.ndarray:
        hazard: HazardBinContract = self.contracts[M1_V2_HAZARD_COORDINATE]
        indices = torch.as_tensor(ib_index, dtype=torch.long).reshape(-1)
        if indices.numel() == 1 and batch > 1:
            indices = indices.expand(batch)
        return np.asarray([hazard.representative(int(item))[0] for item in indices],
                          dtype=float)

    def hazard_logits(self, state: torch.Tensor) -> torch.Tensor:
        """Hazard logits over the internal remaining-time coordinate."""
        models = self.models.get(M1_V2_HAZARD_COORDINATE_TARGET, {}).get("hazard_models")
        if not models:
            raise ContractError("M1_FAST_HAZARD_MODELS_MISSING")
        features = np.asarray(state.detach().cpu(), dtype=float)
        probabilities = np.column_stack([
            _clip_probability(model.predict(features)) for model in models
        ])
        return torch.tensor(np.log(probabilities / (1.0 - probabilities)),
                            dtype=torch.float32)

    def _positive_quantile_values(self, regressors, features: np.ndarray) -> np.ndarray:
        return np.column_stack([model.predict(features) for model in regressors])

    def d_ob_heads(self, state: torch.Tensor, ib_index):
        """(zero_logit, quantile_logits) for D_OB conditioned on T_IB coord."""
        d_ob: HurdleQuantileContract = self.contracts["D_OB"]
        features = np.asarray(state.detach().cpu(), dtype=float)
        ib_repr = self._ib_representatives(ib_index, features.shape[0])
        augmented = np.concatenate([features, ib_repr[:, None]], axis=-1)
        zero = _classifier_logits(self.models["D_OB"]["zero"], augmented)
        quantiles = self._positive_quantile_values(
            self.models["D_OB"]["quantiles"], augmented)
        quantile_logits = torch.tensor(
            _quantile_logits_from_values(quantiles), dtype=torch.float32)
        return zero, quantile_logits

    def d_tx_heads(self, state: torch.Tensor, ib_index, d_ob_index):
        """(zero_logit, quantile_logits) for D_TX conditioned on formal parents."""
        d_ob: HurdleQuantileContract = self.contracts["D_OB"]
        features = np.asarray(state.detach().cpu(), dtype=float)
        ib_repr = self._ib_representatives(ib_index, features.shape[0])
        ob_indices = torch.as_tensor(d_ob_index, dtype=torch.long).reshape(-1)
        if ob_indices.numel() == 1 and features.shape[0] > 1:
            ob_indices = ob_indices.expand(features.shape[0])
        ob_repr = np.asarray([d_ob.representative(int(item))[0] for item in ob_indices],
                             dtype=float)
        augmented = np.concatenate(
            [features, ib_repr[:, None], ob_repr[:, None]], axis=-1)
        zero = _classifier_logits(self.models["D_TX"]["zero"], augmented)
        quantiles = self._positive_quantile_values(
            self.models["D_TX"]["quantiles"], augmented)
        quantile_logits = torch.tensor(
            _quantile_logits_from_values(quantiles), dtype=torch.float32)
        return zero, quantile_logits

    def _predict_heads(self, values: torch.Tensor, lengths=None):
        features = self._arx_features(values)
        state = torch.tensor(features, dtype=torch.float32)
        return conditional_head_summary(self, state, self.contracts)

    def predict_development(
        self, values: torch.Tensor, lengths: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor | dict[str, torch.Tensor]]:
        """Execute the fitted architecture for synthetic/unit smoke only.

        Never a paper result: fitted-but-unfrozen models are DEVELOPMENT_ONLY
        and the principal ``predict_distributions`` path keeps ABSTAIN until a
        train-frozen V2 artifact is registered.
        """
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        return self._predict_heads(values, lengths)

    def predict_distributions(
        self, values: torch.Tensor, lengths: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor | dict[str, torch.Tensor]]:
        """Return the V2 distribution summary schema like ``M1Pipeline``.

        Fitted V2 FAST artifacts are not yet registered; until a train-frozen
        artifact exists the predictor abstains instead of emitting
        hazard/hurdle-quantile outputs that have not been frozen.
        """
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        raise ContractError("M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED")

    def sample(
        self,
        *,
        features: torch.Tensor,
        episode_id: str,
        decision_node_id: str,
        stage: str,
        observed: dict[str, object],
        count: int,
        seed: int,
        target_support: dict[str, str],
        decision_time_utc: str | None,
        scheduled_ob_utc: str | None = None,
        **kwargs,
    ):
        """Shared V2 scenario schema through ``ancestral_sample_v2``."""
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        return ancestral_sample_v2(
            self, features, self.contracts,
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            stage=stage,
            observed=observed,
            count=count,
            seed=seed,
            target_support=target_support,
            decision_time_utc=decision_time_utc,
            scheduled_ob_utc=scheduled_ob_utc,
            **kwargs,
        )

    def __call__(self, pre_state, values, lengths) -> dict[str, object]:
        """Adapter matching ``M1Service(fast_predictor=...)`` callback signature."""
        return self.predict_distributions(values, lengths)


FastPredictor = Callable[[object, torch.Tensor, torch.Tensor | None], dict[str, object]]

__all__ = [
    "FastPathContract",
    "FastPredictor",
    "LightGBMDistributionalPredictor",
    "M1FastPathStatus",
    "fast_v2_distribution_schema",
]
