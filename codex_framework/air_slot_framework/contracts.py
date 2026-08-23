"""Typed E -> S -> C -> CU contracts for the AIR SLOT decision chain."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


CONSEQUENCE_COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("NAIVE_DATETIME_NOT_CANONICAL")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def content_hash(value: Any) -> str:
    payload = json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return f"sha256:{sha256(payload).hexdigest()}"


class SupportState(str, Enum):
    SUPPORTED = "SUPPORTED"
    ABSTAIN = "ABSTAIN"


class OperationalInformation(FrozenModel):
    """Decision-time admissible operational information E."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    decision_time: datetime
    information_cutoff: datetime
    current_information: dict[str, Any]
    admissible_history: tuple[dict[str, Any], ...]
    provenance: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def decision_time_boundary(self):
        for value in (self.decision_time, self.information_cutoff):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("E_REQUIRES_TIMEZONE_AWARE_TIMESTAMPS")
        if self.information_cutoff > self.decision_time:
            raise ValueError("E_INFORMATION_CUTOFF_AFTER_DECISION_TIME")
        return self

    @computed_field
    @property
    def information_hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"information_hash"}))


class NativeConsequenceComponent(FrozenModel):
    """One native consequence C_k before heterogeneous normalization."""

    component_id: str
    q_value: float | None
    native_unit: str = Field(min_length=1)
    support_state: SupportState
    train_positive_median: float | None = Field(default=None, gt=0)
    reference_lineage: tuple[str, ...] = Field(min_length=1)
    reason_code: str | None = None

    @model_validator(mode="after")
    def explicit_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("C_UNKNOWN_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if self.q_value is not None or self.train_positive_median is not None:
                raise ValueError("C_ABSTAIN_MUST_REMAIN_NULL")
            if not self.reason_code:
                raise ValueError("C_ABSTAIN_REQUIRES_REASON")
        else:
            if self.q_value is None or self.train_positive_median is None:
                raise ValueError("C_SUPPORTED_REQUIRES_Q_AND_TRAIN_MEDIAN")
            if not isfinite(self.q_value):
                raise ValueError("C_NONFINITE_VALUE")
        return self

    @computed_field
    @property
    def consequence_id(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"consequence_id"}))


class CUComponent(FrozenModel):
    """Constructed unit CU_k = q_k / s_k; never a monetary quantity."""

    component_id: str
    value_cu: float | None
    support_state: SupportState
    source_consequence_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    normalization_scale: float | None = Field(default=None, gt=0)
    normalization_rule: str = "TRAIN_POSITIVE_MEDIAN"
    reason_code: str | None = None

    @classmethod
    def from_native(cls, component: NativeConsequenceComponent) -> "CUComponent":
        if component.support_state is SupportState.ABSTAIN:
            return cls(
                component_id=component.component_id,
                value_cu=None,
                support_state=SupportState.ABSTAIN,
                source_consequence_id=component.consequence_id,
                normalization_scale=None,
                reason_code=component.reason_code,
            )
        return cls(
            component_id=component.component_id,
            value_cu=float(component.q_value) / float(component.train_positive_median),
            support_state=SupportState.SUPPORTED,
            source_consequence_id=component.consequence_id,
            normalization_scale=component.train_positive_median,
        )

    @model_validator(mode="after")
    def explicit_support(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("CU_UNKNOWN_COMPONENT")
        if self.support_state is SupportState.ABSTAIN:
            if self.value_cu is not None or self.normalization_scale is not None:
                raise ValueError("CU_ABSTAIN_MUST_REMAIN_NULL")
            if not self.reason_code:
                raise ValueError("CU_ABSTAIN_REQUIRES_REASON")
        elif self.value_cu is None or self.normalization_scale is None:
            raise ValueError("CU_SUPPORTED_REQUIRES_VALUE_AND_SCALE")
        return self

    @computed_field
    @property
    def cu_id(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"cu_id"}))


class ConsequenceScenario(FrozenModel):
    """One scenario-specific C -> CU baseline consequence representation."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    native_components: tuple[NativeConsequenceComponent, ...]
    cu_components: tuple[CUComponent, ...]

    @classmethod
    def from_native(
        cls,
        *,
        episode_id: str,
        decision_node_id: str,
        scenario_id: int,
        scenario_weight: float,
        components: tuple[NativeConsequenceComponent, ...],
    ) -> "ConsequenceScenario":
        return cls(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            scenario_id=scenario_id,
            scenario_weight=scenario_weight,
            native_components=components,
            cu_components=tuple(CUComponent.from_native(item) for item in components),
        )

    @model_validator(mode="after")
    def exact_component_vector(self):
        native_ids = tuple(item.component_id for item in self.native_components)
        cu_ids = tuple(item.component_id for item in self.cu_components)
        if native_ids != CONSEQUENCE_COMPONENTS or cu_ids != CONSEQUENCE_COMPONENTS:
            raise ValueError("C_CU_EXACT_SEVEN_COMPONENTS_REQUIRED")
        if any(
            native.consequence_id != cu.source_consequence_id
            for native, cu in zip(self.native_components, self.cu_components, strict=True)
        ):
            raise ValueError("C_CU_LINEAGE_MISMATCH")
        return self

    @computed_field
    @property
    def scenario_consequence_hash(self) -> str:
        return content_hash(
            self.model_dump(mode="json", exclude={"scenario_consequence_hash"})
        )


class HistoryConditionedState(FrozenModel):
    """History-conditioned operational state S carrying aligned scenarios."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    information_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    history_mode: str = Field(min_length=1)
    state_provenance: tuple[str, ...] = Field(min_length=1)
    consequence_scenarios: tuple[ConsequenceScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_joint_distribution(self):
        scenario_ids = tuple(item.scenario_id for item in self.consequence_scenarios)
        weights = tuple(item.scenario_weight for item in self.consequence_scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("S_DUPLICATE_SCENARIO_ID")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("S_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        if any(
            item.episode_id != self.episode_id
            or item.decision_node_id != self.decision_node_id
            for item in self.consequence_scenarios
        ):
            raise ValueError("S_SCENARIO_CONTEXT_MISMATCH")
        return self

    @computed_field
    @property
    def state_hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"state_hash"}))


__all__ = [
    "CONSEQUENCE_COMPONENTS",
    "CUComponent",
    "ConsequenceScenario",
    "FrozenModel",
    "HistoryConditionedState",
    "NativeConsequenceComponent",
    "OperationalInformation",
    "SupportState",
    "content_hash",
]
