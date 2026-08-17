from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import computed_field, Field, model_validator

from model.common.value_objects import FrozenModel, ProvenanceRef
from .semantics import external_target_name


TargetName = Literal["R_IB", "DELTA_OB", "T_TX"]
STOCHASTIC_TARGETS: tuple[TargetName, ...] = ("R_IB", "DELTA_OB", "T_TX")


class TargetBinContract(FrozenModel):
    """Categorical support with explicit signed tails where the target requires it."""

    target_name: TargetName
    bin_width_minutes: int = Field(gt=0)
    max_finite_minutes: int = Field(gt=0)
    min_finite_minutes: int | None = None
    signed: bool = False

    @model_validator(mode="after")
    def validate_support(self):
        minimum = 0 if self.min_finite_minutes is None else self.min_finite_minutes
        if minimum % self.bin_width_minutes or self.max_finite_minutes % self.bin_width_minutes:
            raise ValueError("finite support must align to bin width")
        if self.target_name == "DELTA_OB":
            if not self.signed or minimum >= 0:
                raise ValueError("DELTA_OB requires explicit signed finite support")
            if minimum != -self.max_finite_minutes:
                raise ValueError("DELTA_OB signed support must be symmetric")
        elif self.signed or minimum != 0:
            raise ValueError("only DELTA_OB may use signed support")
        return self

    @property
    def finite_minimum_minutes(self) -> int:
        return 0 if self.min_finite_minutes is None else self.min_finite_minutes

    @computed_field
    @property
    def class_count(self) -> int:
        finite = (self.max_finite_minutes - self.finite_minimum_minutes) // self.bin_width_minutes + 1
        return finite + (2 if self.signed else 1)

    @property
    def underflow_index(self) -> int | None:
        return 0 if self.signed else None

    @property
    def finite_start_index(self) -> int:
        return 1 if self.signed else 0

    @property
    def overflow_index(self) -> int:
        return self.class_count - 1

    def encode(self, minutes: float) -> int:
        value = float(minutes)
        if self.signed:
            if value < self.finite_minimum_minutes:
                return self.underflow_index  # type: ignore[return-value]
            if value >= self.max_finite_minutes + self.bin_width_minutes:
                return self.overflow_index
            return self.finite_start_index + min(
                int((value - self.finite_minimum_minutes) // self.bin_width_minutes),
                self.overflow_index - self.finite_start_index - 1,
            )
        if value < 0:
            raise ValueError("nonnegative target minutes cannot be negative")
        if value >= self.max_finite_minutes + self.bin_width_minutes:
            return self.overflow_index
        return min(int(value // self.bin_width_minutes), self.overflow_index - 1)

    def tail_state(self, index: int) -> Literal["UNDERFLOW", "OVERFLOW"] | None:
        if index < 0 or index >= self.class_count:
            raise ValueError("target bin index outside support")
        if self.signed and index == self.underflow_index:
            return "UNDERFLOW"
        if index == self.overflow_index:
            return "OVERFLOW"
        return None

    def representative(self, index: int) -> tuple[float, bool, bool]:
        """Return representative minutes and explicit underflow/overflow flags."""
        tail = self.tail_state(index)
        if tail == "UNDERFLOW":
            return self.finite_minimum_minutes - self.bin_width_minutes / 2, True, False
        if tail == "OVERFLOW":
            return self.max_finite_minutes + self.bin_width_minutes, False, True
        start = self.finite_minimum_minutes + (
            index - self.finite_start_index
        ) * self.bin_width_minutes
        return start + self.bin_width_minutes / 2, False, False


class TargetLabel(FrozenModel):
    target_name: TargetName
    active: bool
    exact_minutes: float | None = None
    lower_minutes: float | None = None
    upper_minutes: float | None = None
    support: str = "SUPPORTED"

    @model_validator(mode="after")
    def exact_or_interval(self):
        values = (self.exact_minutes, self.lower_minutes, self.upper_minutes)
        if self.target_name != "DELTA_OB" and any(
            value is not None and value < 0 for value in values
        ):
            raise ValueError("nonnegative target label cannot be negative")
        if not self.active:
            if any(value is not None for value in values):
                raise ValueError("inactive target cannot carry fabricated label")
            return self
        exact = self.exact_minutes is not None
        interval = self.lower_minutes is not None and self.upper_minutes is not None
        if exact == interval:
            raise ValueError("active target requires exactly one exact or interval label")
        if interval and self.lower_minutes > self.upper_minutes:
            raise ValueError("invalid interval")
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
    """One joint draw from the signed M1 chain and its derived quantities."""

    episode_id: str
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    operational_stage: str
    r_ib_minutes: float | None
    delta_ob_minutes: float | None
    t_tx_minutes: float | None
    scheduled_ob_utc: str | None = None
    tx_reference_minutes: float | None = None
    taxi_reference_id: str | None = None
    taxi_reference_hash: str | None = None
    taxi_reference_fallback_level: str | None = None
    taxi_reference_support_state: str | None = None
    ib_observed: bool = False
    delta_ob_observed: bool = False
    ib_support: str = "ABSTAIN"
    delta_ob_support: str = "ABSTAIN"
    tx_support: str = "ABSTAIN"
    overflow_ib: bool = False
    underflow_delta_ob: bool = False
    overflow_delta_ob: bool = False
    overflow_tx: bool = False
    scenario_seed_key: str

    @computed_field
    @property
    def r_ob_minutes(self) -> float | None:
        return None if self.delta_ob_minutes is None else max(0.0, self.delta_ob_minutes)

    @computed_field
    @property
    def t_ob_utc(self) -> str | None:
        if self.scheduled_ob_utc is None or self.delta_ob_minutes is None:
            return None
        try:
            return (datetime.fromisoformat(self.scheduled_ob_utc) + timedelta(
                minutes=self.delta_ob_minutes
            )).isoformat()
        except ValueError:
            return None

    @computed_field
    @property
    def t_to_utc(self) -> str | None:
        if self.t_ob_utc is None or self.t_tx_minutes is None:
            return None
        try:
            return (datetime.fromisoformat(self.t_ob_utc) + timedelta(
                minutes=self.t_tx_minutes
            )).isoformat()
        except ValueError:
            return None

    @computed_field
    @property
    def d_to_minutes(self) -> float | None:
        if (
            self.delta_ob_minutes is None
            or self.t_tx_minutes is None
            or self.tx_reference_minutes is None
        ):
            return None
        return max(
            0.0,
            self.delta_ob_minutes + self.t_tx_minutes - self.tx_reference_minutes,
        )

    @property
    def ob_observed(self) -> bool:
        """Compatibility alias for consumers that only need the observed state."""
        return self.delta_ob_observed

    @property
    def ob_support(self) -> str:
        """Compatibility alias for consumers that consume derived R_OB."""
        return self.delta_ob_support

    @property
    def overflow_ob(self) -> bool:
        return self.overflow_delta_ob

    @property
    def target_semantics(self) -> dict[str, str]:
        names = ("R_IB", "DELTA_OB", "T_TX", "R_OB", "T_OB", "T_TO", "D_TO")
        return {name: external_target_name(name) for name in names}
