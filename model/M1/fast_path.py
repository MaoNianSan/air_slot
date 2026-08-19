"""M1 FAST path V2: ARX-LightGBM distributional baseline scaffold.

The FAST path shares with STATE_AWARE the V2 formal semantics:

- primitive chain T_IB_A00 -> D_OB -> D_TX
- predecessor head: discrete hazard over remaining time
- successor heads: hurdle + positive conditional quantile, D_TX conditioned on
  formal D_OB
- output schema (``{T_IB_A00: pmf, D_OB: {...}, D_TX: {...}}``)
- support schema and V2 scenario schema (``model.M1.scenarios.ancestral_sample_v2``)

Scientific status: DEVELOPMENT_ONLY until a train-frozen V2 artifact is
registered; without fitted models the predictor abstains (``ABSTAIN``) instead
of fabricating distributions.  No fitted model produced here may be promoted
to a paper result and no final-test access is permitted
(``final_test_access_count == 0``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

import numpy as np

import torch

from model.common.errors import ContractError


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


class LightGBMDistributionalPredictor:
    """ARX-lagged LightGBM distributional V2 baseline (DEVELOPMENT_ONLY).

    ``contracts`` maps each V2 primitive target to its typed contract
    (``HazardBinContract`` for T_IB_A00; ``HurdleQuantileContract`` for
    D_OB/D_TX).  Without a registered train-frozen fitted artifact the
    predictor abstains (``ABSTAIN``) instead of fabricating distributions.
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
        missing = set(self.contracts) - set(self.models)
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
    ) -> dict[str, torch.Tensor | dict[str, torch.Tensor]]:
        """Return the V2 distribution summary schema like ``M1Pipeline``.

        Fitted V2 FAST artifacts are not yet registered; until then the
        predictor abstains instead of emitting hazard/hurdle-quantile outputs
        that have not been trained.
        """
        if self.status is M1FastPathStatus.ABSTAIN:
            raise ContractError("M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS")
        raise ContractError("M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED")

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
