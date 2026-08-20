from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Callable

from model.common.errors import ContractError
from model.common.value_objects import FrozenModel
from model.M1.semantics import DELAY_THRESHOLDS_MINUTES, FORMAL_FORECAST_HORIZONS_MINUTES


class M1ModelPath(str, Enum):
    FAST = "FAST"
    STATE_AWARE = "STATE_AWARE"


class M1Forecast(FrozenModel):
    episode_id: str
    decision_node_id: str
    model_path: M1ModelPath
    model_version: str
    forecast_generated_at: datetime
    information_cutoff: datetime
    roll_minutes: int
    forecast_horizons_minutes: tuple[int, ...]
    delay_thresholds_minutes: tuple[int, ...]
    state_updated_at: datetime
    state_age_minutes: float
    distributions: dict[str, Any]
    support: dict[str, str]
    fallback_status: str


class M1Service:
    """Stable facade over state-aware M1 and an explicitly supplied FAST path."""

    def __init__(self, pipeline, *, model_version: str,
                 fast_predictor: Callable | None = None):
        self.pipeline = pipeline
        self.model_version = model_version
        self.fast_predictor = fast_predictor
        self._state_updated_at: dict[str, datetime] = {}

    def scheduled_update(self, pre_state) -> None:
        node = pre_state.decision_node
        self._state_updated_at[node.episode_id] = node.decision_time

    def event_update(self, pre_state) -> None:
        self.scheduled_update(pre_state)

    def predict_now(self, pre_state, values, lengths, *, mode: str = "state",
                    generated_at: datetime | None = None) -> M1Forecast:
        node = pre_state.decision_node
        generated_at = generated_at or node.decision_time
        if mode == "fast":
            if self.fast_predictor is None:
                raise ContractError("M1_FAST_PATH_NOT_CONFIGURED")
            distributions = self.fast_predictor(pre_state, values, lengths)
            model_path = M1ModelPath.FAST
            fallback = "EXPLICIT_FAST_QUERY"
        elif mode == "state":
            # Tranche 3 execution closure: production forecast consumes the
            # same PRE information state as scenario generation
            # (h + r_fast + c_static via predict_from_pre).
            distributions = self.pipeline.predict_from_pre(
                pre_state, values, lengths)
            model_path = M1ModelPath.STATE_AWARE
            fallback = "NONE"
        else:
            raise ContractError("M1_MODEL_PATH_UNKNOWN")
        state_updated_at = self._state_updated_at.get(node.episode_id, node.decision_time)
        from .pipeline import V1_TO_V2_SUPPORT
        support = {
            V1_TO_V2_SUPPORT.get(item.target_name, item.target_name): item.support_state.value
            for item in pre_state.target_support
        }
        return M1Forecast(
            episode_id=node.episode_id,
            decision_node_id=node.decision_node_id,
            model_path=model_path,
            model_version=self.model_version,
            forecast_generated_at=generated_at,
            information_cutoff=node.information_cutoff,
            roll_minutes=node.roll_minutes,
            forecast_horizons_minutes=FORMAL_FORECAST_HORIZONS_MINUTES,
            delay_thresholds_minutes=DELAY_THRESHOLDS_MINUTES,
            state_updated_at=state_updated_at,
            state_age_minutes=max(0.0, (generated_at - state_updated_at).total_seconds() / 60.0),
            distributions=distributions,
            support=support,
            fallback_status=fallback,
        )

    def generate_scenarios(self, pre_state, values, lengths, **kwargs):
        from .factual_state import factual_observed_state
        observed = factual_observed_state(pre_state)
        supplied = kwargs.pop("observed", None)
        if supplied is not None and supplied != observed:
            raise ContractError("M1_CALLER_OBSERVED_STATE_FORBIDDEN")
        return self.pipeline.sample_from_pre(
            pre_state, values, lengths, observed=observed, **kwargs)
