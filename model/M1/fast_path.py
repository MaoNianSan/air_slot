"""M1 FAST path: ARX-LightGBM distributional baseline.

The FAST path is a coded contract scaffold for the manuscript's ARX / LightGBM
distributional baseline.  It shares with STATE_AWARE:

- feature semantics (decision-time causal history prefix only)
- target semantics (R_IB / DELTA_OB / T_TX bin contracts)
- output schema (``{target: per-class probability tensor}``)
- support schema and scenario schema (via model.M1.scenarios.aligned_sample)

FAST differs only in history representation (lagged ARX features instead of
the GRU encoder) and model class (LightGBM multiclass per target).

Scientific status: DEVELOPMENT_ONLY until a train-frozen artifact is
registered.  No fitted model produced here may be promoted to a paper result,
and no final-test access is permitted (``final_test_access_count == 0``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

import numpy as np

import torch

from model.common.errors import ContractError
from .contracts import TargetBinContract


class M1FastPathStatus(str, Enum):
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class FastPathContract:
    """Typed contract shared by FAST and STATE_AWARE M1 paths."""

    status: M1FastPathStatus
    feature_semantics: str = "CAUSAL_HISTORY_PREFIX_ONLY"
    target_semantics: str = "R_IB_DELTA_OB_T_TX_BIN_CONTRACTS"
    output_schema: str = "TARGET_KEYED_CLASS_PROBABILITIES"
    support_schema: str = "ALIGNED_SCENARIO_SUPPORT"
    scenario_schema: str = "ALIGNED_SCENARIO"
    final_test_access_count: int = 0
    paper_full_run: bool = False


class LightGBMDistributionalPredictor:
    """ARX-lagged LightGBM multiclass distributional baseline (DEVELOPMENT_ONLY).

    ``models`` maps each stochastic target to a fitted LightGBM classifier
    whose class space equals the target's ``TargetBinContract`` class count.
    Without a fitted model the predictor abstains (``ABSTAIN``) instead of
    fabricating distributions.
    """

    def __init__(
        self,
        bins: Mapping[str, TargetBinContract],
        models: Mapping[str, object] | None = None,
        feature_window: int = 6,
    ):
        self.bins = dict(bins)
        self.models = dict(models or {})
        self.feature_window = int(feature_window)
        if self.feature_window < 1:
            raise ValueError("M1_FAST_FEATURE_WINDOW_MUST_BE_POSITIVE")
        missing = set(self.bins) - set(self.models)
        self.status = (
            M1FastPathStatus.DEVELOPMENT_ONLY
            if models is not None and not missing
            else M1FastPathStatus.ABSTAIN
        )

    def contract(self) -> FastPathContract:
        return FastPathContract(status=self.status)

    def _arx_features(self, values: torch.Tensor) -> torch.Tensor:
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
            rows.append(seq.reshape(-1))
        return torch.stack(rows, dim=0)

    def predict_distributions(
        self, values: torch.Tensor, lengths: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor]:
        """Return ``{target: (batch, class_count) probabilities}`` like M1Pipeline."""
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        features = self._arx_features(values)
        output = {}
        for target, model in self.models.items():
            class_count = self.bins[target].class_count
            if model.n_classes_ > class_count:
                raise ContractError("M1_FAST_MODEL_CLASS_SPACE_MISMATCH")
            scores = model.predict_proba(features.numpy())
            # LightGBM drops classes absent from its fit labels; scatter the
            # predicted probabilities back into the full bin class space.
            probabilities = torch.zeros(
                (values.shape[0], class_count), dtype=torch.float32
            )
            classes = np.asarray(model.classes_, dtype=np.int64)
            probabilities[:, classes] = torch.tensor(scores, dtype=torch.float32)
            row_sums = probabilities.sum(dim=-1, keepdim=True)
            if torch.any(row_sums <= 0):
                raise ContractError("M1_FAST_OUTPUT_INVALID")
            probabilities = probabilities / row_sums
            output[target] = probabilities
        return output

    def __call__(self, pre_state, values, lengths) -> dict[str, torch.Tensor]:
        """Adapter matching ``M1Service(fast_predictor=...)`` callback signature."""
        return self.predict_distributions(values, lengths)


FastPredictor = Callable[[object, torch.Tensor, torch.Tensor | None], dict[str, torch.Tensor]]

__all__ = [
    "FastPathContract",
    "FastPredictor",
    "LightGBMDistributionalPredictor",
    "M1FastPathStatus",
]
