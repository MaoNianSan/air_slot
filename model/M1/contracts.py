from datetime import date, datetime
from typing import Literal
from pydantic import Field, model_validator, computed_field
from model.common.value_objects import FrozenModel
from model.common.value_objects import ProvenanceRef
from .semantics import external_target_name


TargetName = Literal["R_IB", "R_OB", "T_TX"]


class TargetBinContract(FrozenModel):
    target_name: TargetName
    bin_width_minutes: int = Field(gt=0)
    max_finite_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def divisible(self):
        if self.max_finite_minutes % self.bin_width_minutes: raise ValueError("finite maximum must align to bin width")
        return self

    @computed_field
    @property
    def class_count(self) -> int:
        return self.max_finite_minutes // self.bin_width_minutes + 2

    def encode(self, minutes: float) -> int:
        if minutes < 0: raise ValueError("target minutes cannot be negative")
        if minutes >= self.max_finite_minutes + self.bin_width_minutes: return self.class_count - 1
        return min(int(minutes // self.bin_width_minutes), self.class_count - 2)

    def representative(self, index: int) -> tuple[float, bool]:
        overflow = index == self.class_count - 1
        return ((self.max_finite_minutes + self.bin_width_minutes) if overflow else
                index * self.bin_width_minutes + self.bin_width_minutes / 2, overflow)


class TargetLabel(FrozenModel):
    target_name: TargetName
    active: bool
    exact_minutes: float | None = Field(default=None, ge=0)
    lower_minutes: float | None = Field(default=None, ge=0)
    upper_minutes: float | None = Field(default=None, ge=0)
    support: str = "SUPPORTED"

    @model_validator(mode="after")
    def exact_or_interval(self):
        if not self.active:
            if any(v is not None for v in (self.exact_minutes, self.lower_minutes, self.upper_minutes)):
                raise ValueError("inactive target cannot carry fabricated label")
            return self
        exact = self.exact_minutes is not None
        interval = self.lower_minutes is not None and self.upper_minutes is not None
        if exact == interval: raise ValueError("active target requires exactly one exact or interval label")
        if interval and self.lower_minutes > self.upper_minutes: raise ValueError("invalid interval")
        return self


class M1TargetLabel(TargetLabel):
    episode_id: str
    decision_node_id: str
    target_definition_id: str
    target_definition_version: str
    label_status: Literal["EXACT", "INTERVAL", "INACTIVE"]
    provenance: tuple[ProvenanceRef, ...]
    split: Literal["train", "calibration", "development", "test"]
    episode_date: date
    abstention_reason: str | None = None

    @model_validator(mode="after")
    def status_matches_value(self):
        if self.label_status == "INACTIVE" and self.active:
            raise ValueError("inactive label status cannot be active")
        if self.label_status == "EXACT" and self.exact_minutes is None:
            raise ValueError("exact label status requires exact minutes")
        if self.label_status == "INTERVAL" and self.lower_minutes is None:
            raise ValueError("interval label status requires bounds")
        return self


class AlignedScenario(FrozenModel):
    episode_id: str
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    operational_stage: str
    r_ib_minutes: float | None
    r_ob_minutes: float | None
    t_tx_minutes: float | None
    t_ib_utc: str | None = None
    t_ob_utc: str | None = None
    t_to_utc: str | None = None
    scheduled_ob_utc: str | None = None
    tx_reference_minutes: float | None = None
    ib_observed: bool
    ob_observed: bool
    ib_support: str
    ob_support: str
    tx_support: str
    overflow_ib: bool
    overflow_ob: bool
    overflow_tx: bool
    scenario_seed_key: str

    @property
    def d_to_minutes(self) -> float | None:
        """Derived total takeoff delay; never an independent stochastic head."""
        if self.t_to_utc and self.scheduled_ob_utc and self.tx_reference_minutes is not None:
            try:
                total = (
                    datetime.fromisoformat(self.t_to_utc).timestamp()
                    - datetime.fromisoformat(self.scheduled_ob_utc).timestamp()
                ) / 60.0
                return max(0.0, total - float(self.tx_reference_minutes))
            except ValueError:
                pass
        return None

    @property
    def target_semantics(self) -> dict[str, str]:
        return {name: external_target_name(name) for name in ("R_IB", "R_OB", "T_TX", "D_TO")}
