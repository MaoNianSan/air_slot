"""M1 FAST path V2: executable ARX-LightGBM distributional baseline.

The FAST path shares with STATE_AWARE the V2 formal semantics:

- primitive chain T_IB_A00 -> D_OB -> D_TX
- predecessor head: TRUE discrete hazard over the INTERNAL remaining-time
  coordinate (``T_IB_REMAINING_HAZARD``; public ``T_IB_A00`` = decision time
  + coordinate).  Each finite-bin model is trained on its risk set
  ``R_k = {n : active AND remaining >= start(B_k)}`` with
  ``y_{n,k} = 1[T_n in B_k]``; rows beyond ``max_finite`` stay at-risk in
  every finite risk set and are absorbed by the survival tail
  (``hazard_pmf = h_k * prod_{j<k}(1-h_j)``, tail = ``prod_j(1-h_j)``).
- successor heads: hurdle + positive conditional quantile, D_TX conditioned
  on the formal D_OB parent
- output schema (``{T_IB_A00: pmf, D_OB: {...}, D_TX: {...}}``) via
  ``conditional_head_summary``
- support schema and V2 scenario schema (``model.M1.scenarios.ancestral_sample_v2``)

Round 2.2 representation contract (``r_fast``):
- ``r_fast(i, t)`` is the deterministic current/local-change
  feature block (last causal row of the V2 feature vector:
  current state + weather + decision-node schedule countdown + local Delta X +
  masks + reduced support + stage) — NOT a second flattening
  of the full sequence and NOT a LightGBM prediction/hidden state.
- FAST consumes ``r_fast`` directly (never the GRU recurrent hidden state);
  STATE_AWARE consumes ``concat(GRU(history), projection(r_fast))``.
- Degenerate synthetic risk sets may use a TEST_ONLY deterministic/constant
  hazard surrogate (``allow_test_only_surrogate``, fixture-only); principal
  training never silently substitutes one and the statistical definition
  (risk-set discrete hazard) never changes.

Fitted models stay DEVELOPMENT_ONLY; ``predict_distributions`` keeps ABSTAIN
until a train-frozen V2 artifact is registered (``final_test_access_count ==
0``, no paper promotion).  Synthetic/unit training smoke exercises the
architecture through ``predict_development``.
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
from .data import STATIC_FEATURE_COUNT, fast_features_from_sequence
from .static_features import (
    M1StaticNormalizationArtifact,
    static_reference_features_from_pre,
)
from .calibration import (
    common_calibration_policy,
    fit_hazard_temperature,
    fit_zero_mass_temperature,
    require_calibration_split,
    require_no_final_test,
    quantile_coverage_diagnostic,
)
from .contracts import M1_TEMPERATURE_D_OB_ZERO, M1_TEMPERATURE_D_TX_ZERO, M1_TEMPERATURE_HAZARD
from .pipeline import conditional_head_summary
from .loss import monotone_positive_quantiles
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
    feature_semantics: str = "R_FAST_CURRENT_AR_BLOCK_DETERMINISTIC"
    target_semantics: str = "T_IB_A00_D_OB_D_TX_HAZARD_HURDLE_QUANTILE_CONTRACTS"
    hazard_semantics: str = "DISCRETE_HAZARD_RISK_SET"
    calibration_version: str = "M1_CALIBRATION_CONTRACT_V1"
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


class _ConstantValuePredictor:
    """TEST_ONLY constant-value predictor (quantile-regressor surrogate)."""

    def __init__(self, value: float):
        self.value = float(value)
        self.test_only_surrogate = True

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.full(np.asarray(features).shape[0], self.value, dtype=float)


class _ConstantHazardSurrogate:
    """TEST_ONLY deterministic/constant hazard surrogate.

    Used ONLY for degenerate synthetic risk sets (single-class) under
    ``allow_test_only_surrogate=True``.  It is explicitly fixture-only: the
    principal path raises instead of silently substituting a surrogate, and
    the discrete-hazard statistical definition never changes.
    """

    def __init__(self, probability: float):
        if not 0.0 < probability < 1.0:
            raise ValueError("M1_FAST_TEST_ONLY_HAZARD_SURROGATE_OUT_OF_RANGE")
        self.probability = float(probability)
        self.test_only_surrogate = True

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.full(np.asarray(features).shape[0], self.probability,
                       dtype=float)


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
    """ARX-LightGBM distributional V2 baseline (DEVELOPMENT_ONLY).

    ``contracts`` maps each V2 INTERNAL target to its typed contract
    (``HazardBinContract`` for T_IB_REMAINING_HAZARD; ``HurdleQuantileContract``
    for D_OB/D_TX).  ``models`` is the fitted architecture:

    - ``T_IB_REMAINING_HAZARD.hazard_models``: one binary classifier per
      finite remaining-time bin trained on the bin's risk set
      ``{remaining >= start(B_k)}`` (true discrete hazard; the PMF is
      ``h_k * prod_{j<k}(1-h_j)`` with survival tail);
    - ``D_OB`` / ``D_TX``: ``zero`` classifier plus ``quantiles`` per-level
      positive regressors, conditioned on the formal parents.

    The predictor consumes ``r_fast`` (deterministic current/local block), never
    a GRU recurrent hidden state.  Without a registered train-frozen fitted
    artifact the principal ``predict_distributions`` path abstains
    (``ABSTAIN``) instead of fabricating distributions;
    ``predict_development`` executes the fitted architecture for
    synthetic/unit smoke only.
    """

    def __init__(
        self,
        contracts: Mapping[str, object],
        models: Mapping[str, object] | None = None,
        static_normalization: M1StaticNormalizationArtifact | None = None,
    ):
        self.contracts = dict(contracts)
        self.models = dict(models or {})
        self.calibration_temperatures: dict[str, float] = {
            M1_TEMPERATURE_HAZARD: 1.0,
            M1_TEMPERATURE_D_OB_ZERO: 1.0,
            M1_TEMPERATURE_D_TX_ZERO: 1.0,
        }
        self.calibration_diagnostics: dict[str, object] = {}
        self.static_normalization = static_normalization
        # Tranche 3 static parity: when fitted with PRE-published MODEL_FEATURE
        # fields, the ARX-LightGBM models are fitted on ``concat(r_fast,
        # c_static)`` and inference requires the same static block.
        self._static_input_size: int = 0
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
        allow_test_only_surrogate: bool = False,
        static_features: np.ndarray | None = None,
    ) -> "LightGBMDistributionalPredictor":
        """Fit the ARX-LightGBM architecture on one bundle (no paper fitting).

        ``X`` is the ``r_fast`` feature matrix (B, F).  ``static_features``
        (optional) is the PRE-published ``c_static`` block (B, S): when
        supplied the models are fitted on ``concat(r_fast, c_static)`` so the
        FAST path shares the manuscript ``[r_fast, c_static]`` representation
        (never an ordinal encoding of retained identities).  ``targets`` keys are
        the V2 INTERNAL training-target names:
        - ``T_IB_REMAINING_HAZARD``: remaining minutes (or NaN for inactive);
        - ``D_OB`` / ``D_TX``: nonnegative minutes (or NaN).

        Hazard fitting follows the true discrete-hazard definition: for each
        finite bin ``k`` the binary model is fit ONLY on the risk set
        ``R_k = {n : active AND remaining >= start(B_k)}`` with
        ``y_{n,k} = 1[remaining in B_k]``.  Rows with
        ``remaining >= max_finite`` remain at-risk in every finite risk set
        and produce no finite-bin event (survival tail absorbs them).  A
        single-class risk set on a synthetic bundle raises unless
        ``allow_test_only_surrogate=True``, in which case a TEST_ONLY
        constant-hazard surrogate is used for that bin (fixture-only).
        """
        lgbm = _require_lightgbm()
        hazard: HazardBinContract = self.contracts[M1_V2_HAZARD_COORDINATE]
        d_ob: HurdleQuantileContract = self.contracts["D_OB"]
        d_tx: HurdleQuantileContract = self.contracts["D_TX"]
        features = np.asarray(X, dtype=float)
        if static_features is not None:
            static = np.asarray(static_features, dtype=float)
            if static.shape[0] != features.shape[0]:
                raise ContractError("M1_FAST_STATIC_ROWS_MISMATCH")
            if static.ndim != 2 or static.shape[1] < 1:
                raise ContractError("M1_FAST_STATIC_COLUMNS_INVALID")
            features = np.concatenate([features, static], axis=-1)
            self._static_input_size = int(static.shape[1])
        else:
            self._static_input_size = 0
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

        # --- T_IB hazard: per-bin risk-set binary models ---
        ib_valid = ~np.isnan(ib_target)
        if ib_valid.sum() < 4:
            raise ContractError("M1_FAST_HAZARD_TRAINING_ROWS_INSUFFICIENT")
        width = hazard.bin_width_minutes
        hazard_models: list[object] = []
        risk_set_sizes: list[int] = []
        test_only_surrogates: list[int] = []
        for bin_index in range(hazard.finite_class_count):
            bin_start = float(bin_index * width)
            risk_mask = ib_valid & (ib_target >= bin_start)
            risk_size = int(risk_mask.sum())
            risk_set_sizes.append(risk_size)
            if risk_size < 2:
                degenerate = True
            else:
                event = (
                    (ib_target[risk_mask] >= bin_start)
                    & (ib_target[risk_mask] < bin_start + width)
                )
                degenerate = bool(event.sum() < 1 or (1 - event).sum() < 1)
            if degenerate:
                if not allow_test_only_surrogate:
                    raise ContractError(
                        "M1_FAST_HAZARD_RISK_SET_DEGENERATE:"
                        f"BIN={bin_index}:RISK_SIZE={risk_size}"
                    )
                # TEST_ONLY constant-hazard surrogate: fixture-only, never
                # silently substituted in the principal path, and the
                # statistical definition is unchanged (still a conditional
                # hazard on the bin's risk set).
                surrogate = _ConstantHazardSurrogate(0.5)
                hazard_models.append(surrogate)
                test_only_surrogates.append(bin_index)
                continue
            model = _classifier()
            model.fit(features[risk_mask], event.astype(np.int32))
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
            M1_V2_HAZARD_COORDINATE_TARGET: {
                "hazard_models": hazard_models,
                "risk_set_sizes": risk_set_sizes,
                "test_only_surrogates": test_only_surrogates,
            },
            "D_OB": {"zero": ob_zero_model, "quantiles": ob_quantile_models},
            "D_TX": {"zero": tx_zero_model, "quantiles": tx_quantile_models},
        }
        self.status = M1FastPathStatus.DEVELOPMENT_ONLY
        return self

    def _fast_features(self, values: torch.Tensor, lengths=None) -> torch.Tensor:
        """Deterministic current/local block ``r_fast`` (last causal row)."""
        return fast_features_from_sequence(values, lengths)

    def hazard_risk_set_sizes(
        self, ib_target, active=None,
    ) -> list[int]:
        """Risk-set sizes ``R_k = {n : active AND remaining >= start(B_k)}``.

        Contract used by ``fit`` for every finite hazard bin and directly
        verifiable in tests: a later-bin model never sees rows whose event
        already happened, and rows with ``remaining >= max_finite`` remain
        at-risk in every finite risk set (absorbed by the survival tail).
        """
        hazard: HazardBinContract = self.contracts[M1_V2_HAZARD_COORDINATE]
        ib = np.asarray(ib_target, dtype=float)
        if active is None:
            mask = ~np.isnan(ib)
        else:
            mask = np.asarray(active, dtype=bool) & ~np.isnan(ib)
        return [
            int((mask & (ib >= float(k) * hazard.bin_width_minutes)).sum())
            for k in range(hazard.finite_class_count)
        ]

    def state_representation(self, features: torch.Tensor,
                             fast_features=None,
                             static_features: torch.Tensor | None = None) -> torch.Tensor:
        """FAST state = concat(r_fast, c_static) (no GRU recurrent hidden).

        ``features`` is the deterministic current/local block ``r_fast``; when
        PRE-published static MODEL_FEATURE fields are supplied they are
        appended directly (deterministic, no projection).  Without static
        features the state is exactly ``r_fast``.
        """
        if static_features is None:
            return features
        static = torch.as_tensor(static_features, dtype=torch.float32)
        if static.shape[0] != features.shape[0]:
            static = static.expand(features.shape[0], -1)
        return torch.cat([features, static], dim=-1)

    def _ib_representatives(self, ib_index, batch: int) -> np.ndarray:
        hazard: HazardBinContract = self.contracts[M1_V2_HAZARD_COORDINATE]
        indices = torch.as_tensor(ib_index, dtype=torch.long).reshape(-1)
        if indices.numel() == 1 and batch > 1:
            indices = indices.expand(batch)
        return np.asarray([hazard.representative(int(item))[0] for item in indices],
                          dtype=float)

    def hazard_logits(self, state: torch.Tensor) -> torch.Tensor:
        """Hazard logits over the internal remaining-time coordinate.

        Each logit is the conditional hazard ``h_k`` of its finite bin; the
        shared ``hazard_pmf`` turns these into
        ``pmf_k = h_k * prod_{j<k}(1-h_j)`` with survival tail.
        """
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

    def _predict_heads(self, values: torch.Tensor, lengths=None,
                       static_features: torch.Tensor | None = None):
        features = self._fast_features(values, lengths)
        state = torch.tensor(features, dtype=torch.float32)
        if static_features is not None:
            if self._static_input_size == 0:
                raise ContractError("M1_FAST_STATIC_NOT_FITTED")
            state = self.state_representation(state, None, static_features)
        elif self._static_input_size > 0:
            # The fitted architecture consumes ``concat(r_fast, c_static)``;
            # a missing static block is a width-contract violation (never a
            # silent zero substitution).
            raise ContractError("M1_FAST_STATIC_FEATURES_REQUIRED")
        return conditional_head_summary(self, state, self.contracts,
                                        temperatures=self.calibration_temperatures)

    def predict_development(
        self, values: torch.Tensor, lengths: torch.Tensor | None = None,
        static_features: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor | dict[str, torch.Tensor]]:
        """Execute the fitted architecture for synthetic/unit smoke only.

        Never a paper result: fitted-but-unfrozen models are DEVELOPMENT_ONLY
        and the principal ``predict_distributions`` path keeps ABSTAIN until a
        train-frozen V2 artifact is registered.
        """
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        return self._predict_heads(values, lengths, static_features)

    def predict_from_pre(
        self, pre_state, values: torch.Tensor,
        lengths: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor | dict[str, torch.Tensor]]:
        """FAST production forecast over a PRE state (same PRE interface).

        Mirrors the STATE_AWARE path: the PRE-published static context
        (``static_reference_publication``) is rebuilt into the typed M1
        context and only MODEL_FEATURE fields with legal frozen-reference
        provenance enter ``c_static``.
        """
        from .contracts import static_reference_context_from_pre
        publication = getattr(pre_state, "static_reference_publication", None)
        context = (static_reference_context_from_pre(publication)
                   if publication else None)
        if self._static_input_size == 0:
            return self.predict_development(values, lengths)
        if self.static_normalization is None:
            raise ContractError("M1_FAST_STATIC_NORMALIZATION_REQUIRED_FOR_PRE_INFERENCE")
        static_features, _ = static_reference_features_from_pre(
            pre_state, context, self.static_normalization)
        return self.predict_development(values, lengths, static_features)

    def calibration_policy(self):
        """Same scientific calibration policy as STATE_AWARE."""
        return common_calibration_policy()

    def calibrate_development(
        self,
        X: np.ndarray,
        *,
        ib_target: np.ndarray,
        d_ob_target: np.ndarray,
        d_tx_target: np.ndarray,
        active: dict[str, np.ndarray] | None = None,
        split: str = "calibration",
    ) -> dict[str, float]:
        """Fit per-estimator calibration temperatures (development path).

        Same scientific procedure as STATE_AWARE (``M1CalibrationContract``);
        the numeric temperatures are fitted from THIS estimator's calibration
        predictions — same procedure != same numeric temperature.  Hazard uses
        event-time NLL; D_OB/D_TX zero-mass use binary CE on the hurdle zero
        logits; positive quantiles stay ``QUANTILE_CALIBRATION_NOT_APPLIED``.
        """
        require_calibration_split(split)
        require_no_final_test(0)
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        hazard: HazardBinContract = self.contracts[M1_V2_HAZARD_COORDINATE]
        ib = np.asarray(ib_target, dtype=float)
        if active is None:
            act_ib = ~np.isnan(ib)
            act_ob = ~np.isnan(np.asarray(d_ob_target, dtype=float))
            act_tx = ~np.isnan(np.asarray(d_tx_target, dtype=float))
        else:
            act_ib = np.asarray(active.get(M1_V2_HAZARD_COORDINATE_TARGET, np.zeros(len(ib))), dtype=bool)
            act_ob = np.asarray(active.get("D_OB", np.zeros(len(ib))), dtype=bool)
            act_tx = np.asarray(active.get("D_TX", np.zeros(len(ib))), dtype=bool)
        features = torch.tensor(np.asarray(X, dtype=float), dtype=torch.float32)
        temperatures = {
            M1_TEMPERATURE_HAZARD: 1.0,
            M1_TEMPERATURE_D_OB_ZERO: 1.0,
            M1_TEMPERATURE_D_TX_ZERO: 1.0,
        }
        coverage: dict[str, dict[str, float | None]] = {}
        if bool(act_ib.any()):
            labels = np.full(ib.shape, -1, dtype=np.int64)
            for index in np.nonzero(act_ib)[0]:
                labels[index] = hazard.encode(float(ib[index]))
            temperatures[M1_TEMPERATURE_HAZARD] = fit_hazard_temperature(
                self.hazard_logits(features),
                torch.tensor(labels, dtype=torch.long),
                torch.tensor(act_ib, dtype=torch.bool),
                hazard,
                split=split,
            )
        for name, key, targets, act in (
            ("D_OB", M1_TEMPERATURE_D_OB_ZERO,
             np.asarray(d_ob_target, dtype=float), act_ob),
            ("D_TX", M1_TEMPERATURE_D_TX_ZERO,
             np.asarray(d_tx_target, dtype=float), act_tx),
        ):
            if not bool(act.any()):
                continue
            parent_ib = np.asarray([hazard.encode(float(ib[i]))
                                    for i in np.nonzero(act)[0]], dtype=np.int64)
            rows = features[np.nonzero(act)[0]]
            if name == "D_OB":
                zero_logit, quantile_logit = self.d_ob_heads(
                    rows, torch.tensor(parent_ib))
            else:
                # D_TX conditions on the FORMAL D_OB parent (its own D_TX
                # minute value is never a proxy): encode each active row's
                # ``d_ob_target``.  A missing D_OB parent under an active
                # D_TX calibration row is a contract violation.
                active_indices = np.nonzero(act)[0]
                parent_ob = np.empty(len(active_indices), dtype=np.int64)
                for row_position, index in enumerate(active_indices):
                    parent_minutes = float(d_ob_target[index])
                    if np.isnan(parent_minutes) or parent_minutes < 0:
                        raise ContractError("M1_FAST_D_TX_CALIBRATION_PARENT_MISSING")
                    parent_ob[row_position] = self.contracts["D_OB"].encode(
                        parent_minutes)
                zero_logit, quantile_logit = self.d_tx_heads(
                    rows, torch.tensor(parent_ib), torch.tensor(parent_ob))
            zero_label = np.asarray([float(targets[i]) == 0.0
                                     for i in np.nonzero(act)[0]], dtype=float)
            temperatures[key] = fit_zero_mass_temperature(
                zero_logit, torch.tensor(zero_label, dtype=torch.float32),
                torch.ones(len(zero_label), dtype=torch.bool), split=split,
            )
            actual = torch.tensor(targets[np.nonzero(act)[0]], dtype=torch.float32)
            positive_active = torch.isfinite(actual) & (actual > 0)
            coverage[name] = quantile_coverage_diagnostic(
                monotone_positive_quantiles(quantile_logit), actual,
                tuple(self.contracts[name].quantile_levels), positive_active,
                split=split,
            )
        self.calibration_temperatures = temperatures
        policy = common_calibration_policy()
        self.calibration_diagnostics = {
            "positive_quantile_status": policy.positive_quantile_calibration,
            "positive_quantile_coverage": coverage,
            "split": policy.split,
            "policy_version": policy.version,
        }
        return dict(temperatures)

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
        """Adapter matching ``M1Service(fast_predictor=...)`` callback signature.

        No train-frozen V2 FAST artifact is registered, so the callback
        abstains (``M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED``) and never
        fabricates distributional outputs.
        """
        return self.predict_distributions(values, lengths)


FastPredictor = Callable[[object, torch.Tensor, torch.Tensor | None], dict[str, object]]

__all__ = [
    "FastPathContract",
    "FastPredictor",
    "LightGBMDistributionalPredictor",
    "M1FastPathStatus",
    "fast_v2_distribution_schema",
]
