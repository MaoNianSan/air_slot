"""Tail-aware typed M1 Development scenario envelopes.

This contract is deliberately separate from ``M1V2Scenario``.  The frozen
checkpoint can draw a finite support class, but it does not identify a scalar
value for a positive quantile tail.  A tail-aware envelope therefore carries
the class identity and support interval while leaving the scalar ``None``.
Observed factual values are retained in a separate, evaluation-only field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from model.common.value_objects import FrozenModel


TAIL_CLASS_ID = "OVERFLOW_TAIL"
ZERO_CLASS_ID = "ZERO"
ABSTAIN_CLASS_ID = "ABSTAIN"

ScenarioClassId = str
ScenarioSourceRole = Literal["MODEL_DRAW", "FACTUAL_OBSERVED", "ABSTAIN"]
ScenarioSupportState = Literal["SUPPORTED", "ABSTAIN"]
ScalarSupportState = Literal["SUPPORTED", "ABSTAIN_TAIL_CLASS", "ABSTAIN_UNSUPPORTED"]


class TargetScenarioEnvelope(FrozenModel):
    """One target value in a joint scenario draw."""

    target_name: str = Field(min_length=1)
    class_index: int | None = Field(default=None, ge=0)
    conditioning_index: int | None = Field(default=None, ge=0)
    class_id: ScenarioClassId = Field(min_length=1)
    class_lower_minutes: float | None = Field(default=None, ge=0)
    class_upper_minutes: float | None = Field(default=None, ge=0)
    scalar_minutes: float | None = Field(default=None, ge=0)
    event_time_utc: str | None = None
    raw_observed_minutes: float | None = Field(default=None, ge=0)
    raw_observed_time_utc: str | None = None
    raw_model_candidate_minutes: float | None = Field(default=None, ge=0)
    source_role: ScenarioSourceRole
    support_state: ScenarioSupportState
    scalar_support_state: ScalarSupportState
    overflow: bool = False
    lineage: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_class_and_scalar(self):
        if self.class_id == ABSTAIN_CLASS_ID:
            if self.class_index is not None or self.conditioning_index is not None or self.overflow:
                raise ValueError("M1_SCENARIO_ABSTAIN_CLASS_INVALID")
            if self.scalar_minutes is not None:
                raise ValueError("M1_SCENARIO_ABSTAIN_SCALAR_MUST_BE_NULL")
            if self.support_state != "ABSTAIN" or self.scalar_support_state != "ABSTAIN_UNSUPPORTED":
                raise ValueError("M1_SCENARIO_ABSTAIN_SUPPORT_INVALID")
            if self.source_role != "ABSTAIN":
                raise ValueError("M1_SCENARIO_ABSTAIN_SOURCE_ROLE_INVALID")
            return self

        if self.class_index is None:
            raise ValueError("M1_SCENARIO_CLASS_INDEX_REQUIRED")
        if self.class_id == ZERO_CLASS_ID:
            if self.target_name not in ("D_OB", "D_TX"):
                raise ValueError("M1_SCENARIO_ZERO_CLASS_TARGET_INVALID")
            if self.overflow:
                raise ValueError("M1_SCENARIO_ZERO_CLASS_CANNOT_OVERFLOW")
            if self.class_lower_minutes != 0 or self.class_upper_minutes != 0:
                raise ValueError("M1_SCENARIO_ZERO_CLASS_INTERVAL_INVALID")
            if self.scalar_minutes != 0:
                raise ValueError("M1_SCENARIO_ZERO_CLASS_SCALAR_INVALID")
            if self.scalar_support_state != "SUPPORTED":
                raise ValueError("M1_SCENARIO_ZERO_CLASS_SUPPORT_INVALID")
        elif self.class_id == TAIL_CLASS_ID:
            if not self.overflow:
                raise ValueError("M1_SCENARIO_TAIL_FLAG_REQUIRED")
            if self.class_upper_minutes is not None:
                raise ValueError("M1_SCENARIO_TAIL_UPPER_BOUND_MUST_BE_OPEN")
            if self.scalar_minutes is not None:
                raise ValueError("M1_SCENARIO_TAIL_SCALAR_MUST_BE_NULL")
            if self.scalar_support_state != "ABSTAIN_TAIL_CLASS":
                raise ValueError("M1_SCENARIO_TAIL_SCALAR_SUPPORT_INVALID")
            if self.source_role == "FACTUAL_OBSERVED" and self.raw_model_candidate_minutes is not None:
                raise ValueError("M1_SCENARIO_FACTUAL_TAIL_MODEL_CANDIDATE_FORBIDDEN")
        else:
            if self.overflow:
                raise ValueError("M1_SCENARIO_FINITE_CLASS_CANNOT_OVERFLOW")
            if self.class_lower_minutes is None or self.class_upper_minutes is None:
                raise ValueError("M1_SCENARIO_FINITE_CLASS_INTERVAL_REQUIRED")
            if self.class_upper_minutes <= self.class_lower_minutes:
                raise ValueError("M1_SCENARIO_FINITE_CLASS_INTERVAL_INVALID")
            if self.scalar_minutes is None:
                raise ValueError("M1_SCENARIO_FINITE_CLASS_SCALAR_REQUIRED")
            if not (self.class_lower_minutes <= self.scalar_minutes < self.class_upper_minutes):
                raise ValueError("M1_SCENARIO_FINITE_CLASS_SCALAR_OUTSIDE_INTERVAL")
            if self.scalar_support_state != "SUPPORTED":
                raise ValueError("M1_SCENARIO_FINITE_SCALAR_SUPPORT_INVALID")

        if self.support_state != "SUPPORTED":
            raise ValueError("M1_SCENARIO_CLASS_SUPPORT_INVALID")
        if self.conditioning_index is None:
            raise ValueError("M1_SCENARIO_CONDITIONING_INDEX_REQUIRED")
        if self.source_role == "ABSTAIN":
            raise ValueError("M1_SCENARIO_SUPPORTED_CLASS_CANNOT_ABSTAIN_SOURCE")
        if self.target_name == "T_IB_A00":
            if self.event_time_utc is None and self.source_role == "MODEL_DRAW" and not self.overflow:
                raise ValueError("M1_SCENARIO_T_IB_EVENT_TIME_REQUIRED")
            if self.source_role == "FACTUAL_OBSERVED" and self.raw_observed_time_utc is None:
                raise ValueError("M1_SCENARIO_T_IB_RAW_TIME_REQUIRED")
        if self.source_role == "FACTUAL_OBSERVED":
            if self.target_name == "T_IB_A00":
                if self.raw_observed_time_utc is None:
                    raise ValueError("M1_SCENARIO_FACTUAL_T_IB_RAW_TIME_REQUIRED")
            elif self.raw_observed_minutes is None:
                raise ValueError("M1_SCENARIO_FACTUAL_RAW_MINUTES_REQUIRED")
        return self


class JointScenarioEnvelope(FrozenModel):
    """One coherent, weighted, tail-aware joint draw."""

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    scenario_id: int = Field(ge=0)
    scenario_weight: float = Field(gt=0, le=1)
    operational_stage: str = Field(min_length=1)
    decision_time_utc: str = Field(min_length=1)
    information_cutoff_utc: str = Field(min_length=1)
    targets: tuple[TargetScenarioEnvelope, ...] = Field(min_length=3, max_length=3)
    r_ib_minutes: float | None = Field(default=None, ge=0)
    r_ib_support: ScalarSupportState
    d_to_minutes: float | None = Field(default=None, ge=0)
    d_to_support: ScalarSupportState
    scenario_seed_key: str = Field(min_length=1)
    lineage: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_joint_identity(self):
        names = tuple(item.target_name for item in self.targets)
        if names != ("T_IB_A00", "D_OB", "D_TX"):
            raise ValueError("M1_SCENARIO_TARGET_ORDER_INVALID")
        ib = self.targets[0]
        if self.r_ib_support == "SUPPORTED":
            if self.r_ib_minutes is None or ib.scalar_support_state != "SUPPORTED":
                raise ValueError("M1_SCENARIO_R_IB_REQUIRES_FINITE_T_IB")
            if abs(self.r_ib_minutes - ib.scalar_minutes) > 1e-6:
                raise ValueError("M1_SCENARIO_R_IB_IDENTITY_INVALID")
        elif self.r_ib_minutes is not None:
            raise ValueError("M1_SCENARIO_R_IB_ABSTAIN_MUST_BE_NULL")
        if self.d_to_support == "SUPPORTED":
            if self.d_to_minutes is None:
                raise ValueError("M1_SCENARIO_D_TO_VALUE_REQUIRED")
            if any(item.scalar_support_state != "SUPPORTED" for item in self.targets[1:]):
                raise ValueError("M1_SCENARIO_D_TO_REQUIRES_FINITE_DELAY_SCALARS")
            expected = self.targets[1].scalar_minutes + self.targets[2].scalar_minutes
            if abs(self.d_to_minutes - expected) > 1e-6:
                raise ValueError("M1_SCENARIO_D_TO_IDENTITY_INVALID")
        else:
            if self.d_to_minutes is not None:
                raise ValueError("M1_SCENARIO_D_TO_ABSTAIN_MUST_BE_NULL")
        return self


__all__ = [
    "ABSTAIN_CLASS_ID",
    "TAIL_CLASS_ID",
    "ZERO_CLASS_ID",
    "JointScenarioEnvelope",
    "TargetScenarioEnvelope",
]
