from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import computed_field, Field, model_validator

from model.common.errors import ContractError
from model.common.value_objects import FrozenModel, ProvenanceRef
from .semantics import (
    M1_V2_ALL_TARGETS,
    M1_V2_HAZARD_COORDINATE_TARGET,
    M1_V2_LEGACY_AUXILIARY_TARGETS,
    derived_d_ob_minutes,
    remaining_hazard_coordinate_minutes,
    derived_d_to_from_primitives,
    derived_d_to_minutes,
    derived_d_tx_minutes,
    derived_r_ib_minutes,
    external_target_name,
)


TargetName = Literal["R_IB", "DELTA_OB", "T_TX"]
STOCHASTIC_TARGETS: tuple[TargetName, ...] = ("R_IB", "DELTA_OB", "T_TX")
# Internal auxiliary heads only: the formal successor contract is
# D_OB / D_TX / D_TO(derived).  See model/M1/semantics.py.
AUXILIARY_TARGETS: tuple[str, ...] = ("DELTA_OB", "T_TX")


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
    # Public absolute predecessor in-block event time (ISO UTC) and the
    # decision time.  Only the internal hazard-coordinate label carries them;
    # they preserve the public T_IB_A00 identity even when R_IB == 0.
    t_ib_a00_utc: str | None = None
    decision_time_utc: str | None = None

    @model_validator(mode="after")
    def status_matches_value(self):
        if self.label_status == "INACTIVE" and self.active:
            raise ValueError("inactive label status cannot be active")
        if self.label_status == "EXACT" and self.exact_minutes is None:
            raise ValueError("exact label status requires exact minutes")
        if self.label_status == "INTERVAL" and self.lower_minutes is None:
            raise ValueError("interval label status requires bounds")
        return self

    @model_validator(mode="after")
    def hazard_label_coordinate_contract(self):
        if self.target_name != M1_V2_HAZARD_COORDINATE_TARGET:
            return self
        if self.exact_minutes is not None:
            if self.t_ib_a00_utc is None or self.decision_time_utc is None:
                raise ValueError(
                    "hazard-coordinate label requires the public T_IB_A00 and decision time"
                )
            expected = remaining_hazard_coordinate_minutes(
                self.t_ib_a00_utc, self.decision_time_utc
            )
            if expected is None or abs(expected - self.exact_minutes) > 1e-6:
                raise ValueError("hazard-coordinate label inconsistent with T_IB_A00")
        return self


class AlignedScenario(FrozenModel):
    """One joint draw from the M1 chain and its derived formal quantities.

    Formal successor contract: D_OB >= 0, D_TX >= 0, D_TO = D_OB + D_TX per
    scenario.  ``delta_ob_minutes`` / ``t_tx_minutes`` are internal auxiliary
    values and are not formal downstream estimands.
    """

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

    @model_validator(mode="after")
    def formal_delay_contract(self):
        if self.d_ob_minutes is not None and self.d_ob_minutes < 0:
            raise ValueError("D_OB must be nonnegative")
        if self.d_tx_minutes is not None and self.d_tx_minutes < 0:
            raise ValueError("D_TX must be nonnegative")
        d_to = self.d_to_minutes
        if d_to is not None and (d_to < 0 or abs(d_to - (self.d_ob_minutes + self.d_tx_minutes)) > 1e-6):
            raise ValueError("D_TO must equal D_OB + D_TX per scenario")
        return self

    @computed_field
    @property
    def r_ob_minutes(self) -> float | None:
        """Compatibility alias of formal D_OB."""
        return self.d_ob_minutes

    @computed_field
    @property
    def d_ob_minutes(self) -> float | None:
        """Formal nonnegative successor off-block delay D_OB = max(0, DELTA_OB)."""
        return derived_d_ob_minutes(self.delta_ob_minutes)

    @computed_field
    @property
    def d_tx_minutes(self) -> float | None:
        """Formal nonnegative successor excess taxi delay D_TX."""
        return derived_d_tx_minutes(self.t_tx_minutes, self.tx_reference_minutes)

    @computed_field
    @property
    def d_to_minutes(self) -> float | None:
        """Formal total takeoff delay D_TO = D_OB + D_TX (manuscript identity)."""
        return derived_d_to_minutes(
            self.delta_ob_minutes, self.t_tx_minutes, self.tx_reference_minutes
        )

    @computed_field
    @property
    def d_ob_support(self) -> str:
        if self.d_ob_minutes is None:
            return "ABSTAIN"
        return self.delta_ob_support if self.delta_ob_support != "ABSTAIN" else "SUPPORTED"

    @computed_field
    @property
    def d_tx_support(self) -> str:
        if self.d_tx_minutes is None:
            return "ABSTAIN"
        return self.tx_support if self.tx_support != "ABSTAIN" else "SUPPORTED"

    @computed_field
    @property
    def d_to_support(self) -> str:
        if self.d_to_minutes is None:
            return "ABSTAIN"
        if "ABSTAIN" in {self.d_ob_support, self.d_tx_support}:
            return "ABSTAIN"
        return "SUPPORTED"

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

    @property
    def ob_observed(self) -> bool:
        """Compatibility alias for consumers that only need the observed state."""
        return self.delta_ob_observed

    @property
    def ob_support(self) -> str:
        """Compatibility alias for consumers that consume derived R_OB/D_OB."""
        return self.d_ob_support

    @property
    def overflow_ob(self) -> bool:
        return self.overflow_delta_ob

    @property
    def target_semantics(self) -> dict[str, str]:
        names = ("R_IB", "D_OB", "D_TX", "D_TO", "DELTA_OB", "T_TX", "R_OB", "T_OB", "T_TO")
        return {name: external_target_name(name) for name in names}



# ---------------------------------------------------------------------------
# V2 principal contracts (Round-2 M1 V2 real estimator).
#
# Formal primitive chain: T_IB_A00 -> D_OB -> D_TX
# Derived: R_IB = max(0, T_IB_A00 - t); D_TO = D_OB + D_TX.
# The V1 classes above (TargetBinContract / AlignedScenario / ...) remain as
# LEGACY_V1 contracts for historical artifacts and legacy provenance; they are
# not the V2 principal estimator semantics.
# ---------------------------------------------------------------------------

V2TargetName = Literal["T_IB_REMAINING_HAZARD", "D_OB", "D_TX"]
# Internal head/label target names.  The public primitive T_IB_A00 (absolute
# ISO UTC event time) is distinct from the internal remaining-time hazard
# coordinate ``T_IB_REMAINING_HAZARD`` (minutes from the decision node).
V2_TARGETS: tuple[V2TargetName, ...] = (
    "T_IB_REMAINING_HAZARD", "D_OB", "D_TX",
)
M1_V2_HAZARD_COORDINATE = M1_V2_HAZARD_COORDINATE_TARGET

# ---------------------------------------------------------------------------
# Calibration temperature registry keys (Tranche 3).
#
# - ``M1_TEMPERATURE_HAZARD``      scales the hazard logits only (event-time
#   NLL temperature, ``T_IB_REMAINING_HAZARD``).
# - ``M1_TEMPERATURE_D_OB_ZERO``   scales ONLY the D_OB hurdle Bernoulli zero
#   logit (binary-CE temperature).  It NEVER scales the positive quantile
#   values/logits.
# - ``M1_TEMPERATURE_D_TX_ZERO``   same discipline for the D_TX hurdle zero
#   logit.
# Positive quantile values/logits are never temperature-scaled by a
# zero-mass calibration temperature (``QUANTILE_CALIBRATION_NOT_APPLIED``;
# calibration-split coverage diagnostic only).
# ---------------------------------------------------------------------------
M1_TEMPERATURE_HAZARD: str = M1_V2_HAZARD_COORDINATE_TARGET
M1_TEMPERATURE_D_OB_ZERO: str = "D_OB_ZERO"
M1_TEMPERATURE_D_TX_ZERO: str = "D_TX_ZERO"
M1_CALIBRATION_TEMPERATURE_KEYS: tuple[str, ...] = (
    M1_TEMPERATURE_HAZARD,
    M1_TEMPERATURE_D_OB_ZERO,
    M1_TEMPERATURE_D_TX_ZERO,
)


class HazardBinContract(FrozenModel):
    """Discrete-hazard support for the internal remaining-time coordinate.

    The head predicts the internal hazard coordinate ``T_IB_REMAINING_HAZARD``
    (remaining minutes from the decision node), an equivalent
    re-parameterization of the public predecessor in-block event time
    ``T_IB_A00 = decision_time + coordinate``.  The head emits one hazard per
    finite bin; the last class is the survival/overflow tail, so the induced
    PMF always sums to one.  A plain categorical softmax is never used to
    imitate this hazard.
    """

    target_name: Literal["T_IB_REMAINING_HAZARD"] = "T_IB_REMAINING_HAZARD"
    bin_width_minutes: int = Field(gt=0)
    max_finite_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_support(self):
        if self.max_finite_minutes % self.bin_width_minutes:
            raise ValueError("finite support must align to bin width")
        return self

    @property
    def finite_class_count(self) -> int:
        return self.max_finite_minutes // self.bin_width_minutes

    @property
    def class_count(self) -> int:
        """Finite remaining-time bins plus the survival/overflow tail."""
        return self.finite_class_count + 1

    @property
    def overflow_index(self) -> int:
        return self.class_count - 1

    def encode(self, minutes: float) -> int:
        value = float(minutes)
        if value < 0:
            raise ValueError("remaining-time hazard target cannot be negative")
        if value >= self.max_finite_minutes:
            return self.overflow_index
        return min(int(value // self.bin_width_minutes), self.overflow_index - 1)

    def tail_state(self, index: int) -> Literal["OVERFLOW"] | None:
        if index < 0 or index >= self.class_count:
            raise ValueError("hazard bin index outside support")
        return "OVERFLOW" if index == self.overflow_index else None

    def bin_start(self, index: int) -> float:
        if index < 0 or index >= self.class_count:
            raise ValueError("hazard bin index outside support")
        return float(index) * self.bin_width_minutes

    def bin_end(self, index: int) -> float:
        if index < 0 or index >= self.class_count:
            raise ValueError("hazard bin index outside support")
        if index == self.overflow_index:
            return float("inf")
        return float(index + 1) * self.bin_width_minutes

    def representative(self, index: int) -> tuple[float, bool, bool]:
        """Return (representative minutes, underflow, overflow)."""
        tail = self.tail_state(index)
        if tail == "OVERFLOW":
            return self.max_finite_minutes + self.bin_width_minutes, False, True
        return self.bin_start(index) + self.bin_width_minutes / 2, False, False


# Round 2.1 upper-tail contract.  ``UNRESOLVED`` is the only state allowed in
# the principal scientific config: the manuscript does not freeze a positive
# tail rule, so ``Q(u)`` for ``u > q_max`` must never silently clamp to
# ``Q(q_max)``.  ``TEST_ONLY_LINEAR`` exists solely for synthetic smoke
# fixtures and is forbidden in foundation configs.
UpperTailPolicyName = Literal[
    "UNRESOLVED",
    "TEST_ONLY_LINEAR",
    "DECLARED_FROZEN",
    "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
]

M1_POSITIVE_TAIL_DECISION_REQUIRED = "M1_POSITIVE_TAIL_DECISION_REQUIRED"


class HurdleQuantileContract(FrozenModel):
    """Zero-mass hurdle plus positive conditional quantiles for D_OB / D_TX.

    P(D = 0 | parents, h) + P(D > 0 | parents, h) * Q_D(u | D > 0, parents, h)

    The positive conditional quantiles are strictly increasing and positive by
    construction of the head parameterization.  ``bin_width_minutes`` /
    ``max_finite_minutes`` also define the conditioning-embedding grid
    (positive support with an overflow tail).

    ``upper_tail_policy`` gates the behaviour of ``Q(u)`` for
    ``u > max(quantile_levels)`` (see ``model.M1.loss.quantile_value``):
    - ``UNRESOLVED``: raising/ABSTAIN in the principal path; no silent clamp.
    - ``TEST_ONLY_LINEAR``: linear extrapolation for synthetic smoke fixtures
      only; never carried by a foundation scientific config.
    - ``DECLARED_FROZEN``: a scalar frozen tail rule exists (legacy extension
      point; no scalar extrapolation is enabled by the current policy).
    - ``FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS``: values at or above
      ``max_finite_minutes`` are represented by the explicit overflow class;
      continuous quantile queries above ``q_max`` remain gated.
    """

    target_name: Literal["D_OB", "D_TX"]
    max_finite_minutes: int = Field(gt=0)
    bin_width_minutes: int = Field(gt=0)
    quantile_levels: tuple[float, ...]
    upper_tail_policy: UpperTailPolicyName = "UNRESOLVED"
    upper_tail_policy_reference: str | None = None

    @model_validator(mode="after")
    def validate_support(self):
        if self.max_finite_minutes % self.bin_width_minutes:
            raise ValueError("finite support must align to bin width")
        levels = tuple(self.quantile_levels)
        if not levels or any(not (0.0 < level < 1.0) for level in levels):
            raise ValueError("quantile levels must lie strictly inside (0, 1)")
        if any(right <= left for left, right in zip(levels, levels[1:])):
            raise ValueError("quantile levels must be strictly increasing")
        if self.upper_tail_policy == "DECLARED_FROZEN"                 and not self.upper_tail_policy_reference:
            raise ValueError("declared tail rule requires a policy reference")
        if self.upper_tail_policy in ("UNRESOLVED", "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS") \
                and self.upper_tail_policy_reference is not None:
            raise ValueError("unresolved tail policy cannot carry a reference")
        return self

    @property
    def quantile_count(self) -> int:
        return len(self.quantile_levels)

    @property
    def q_max(self) -> float:
        """Largest declared positive quantile level."""
        return float(max(self.quantile_levels))

    @property
    def positive_bin_count(self) -> int:
        return self.max_finite_minutes // self.bin_width_minutes

    @property
    def class_count(self) -> int:
        """Conditioning-embedding grid: positive bins plus the overflow tail."""
        return self.positive_bin_count + 1

    @property
    def overflow_index(self) -> int:
        return self.class_count - 1

    def encode(self, minutes: float) -> int:
        value = float(minutes)
        if value < 0:
            raise ValueError("nonnegative delay target cannot be negative")
        if value >= self.max_finite_minutes:
            return self.overflow_index
        return min(int(value // self.bin_width_minutes), self.overflow_index - 1)

    def tail_state(self, index: int) -> Literal["OVERFLOW"] | None:
        if index < 0 or index >= self.class_count:
            raise ValueError("hurdle-quantile bin index outside support")
        return "OVERFLOW" if index == self.overflow_index else None

    def representative(self, index: int) -> tuple[float, bool, bool]:
        tail = self.tail_state(index)
        if tail == "OVERFLOW":
            return self.max_finite_minutes + self.bin_width_minutes, False, True
        return (float(index) + 0.5) * self.bin_width_minutes, False, False


def cvar_support_status(contract: HurdleQuantileContract, alpha: float) -> str:
    """Return ``SUPPORTED`` / ``GATED`` for a CVaR_alpha downstream consumer.

    CVaR_alpha needs the distribution on the tail ``(alpha, 1]``.  The gate is
    closed unless every region beyond ``alpha`` is covered by a resolved
    upper-tail policy:
    - ``alpha > q_max``: the alpha-quantile itself is not declared;
    - ``upper_tail_policy == UNRESOLVED``: the tail beyond ``q_max`` is not
      representable (so ``Q(q_max)`` must never stand in for the tail).
    """
    q_max = contract.q_max
    if q_max < alpha - 1e-12:
        return "GATED"
    if contract.upper_tail_policy in ("UNRESOLVED", "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"):
        return "GATED"
    return "SUPPORTED"


def require_cvar_support(contract: HurdleQuantileContract, alpha: float) -> None:
    """Raise ``M1_POSITIVE_TAIL_DECISION_REQUIRED`` when CVaR_alpha is gated."""
    status = cvar_support_status(contract, alpha)
    if status != "SUPPORTED":
        raise ContractError(
            f"{M1_POSITIVE_TAIL_DECISION_REQUIRED}:CVAR_ALPHA={alpha}:STATUS={status}"
        )


PRE_STATIC_FIELD_STATUS = Literal[
    "AVAILABLE_ALREADY",
    "AVAILABLE_BUT_NOT_PUBLISHED_TO_M1",
    "NEEDS_PRE_REFERENCE_BINDING",
    "UNSUPPORTED",
]


class M1StaticReferenceField(FrozenModel):
    """One manuscript static/reference field of the M1 input contract.

    ``support_state`` is the M1-side support:
    - ``UPSTREAM_PRE_INTERFACE_REQUIRED``: PRE has not published a canonical
      path to M1 yet (Round 2.2 principal status for every field);
    - ``SUPPORTED``: PRE published and the field may enter the estimator as a
      typed MODEL_FEATURE;
    - ``SUPPORT_ABSTAIN``: retained for identity/provenance only.
    ``pre_status`` follows the Tranche 2.2 classification:
    AVAILABLE_ALREADY / AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 /
    NEEDS_PRE_REFERENCE_BINDING / UNSUPPORTED.
    ``publication_status`` is the Tranche 3 per-field publication state after
    PRE publishes the typed object:
    - ``PUBLISHED``: PRE publishes a typed path (provenance/freeze ids set);
    - ``RETAINED_IDENTITY``: kept for episode identity / provenance / lineage
      only, never a numeric MODEL_FEATURE (e.g. aircraft registration);
    - ``MODEL_FEATURE``: may enter ``c_static`` via a deterministic encoding
      contract (``static_reference_features_from_pre``);
    - ``MODEL_FEATURE_PENDING``: published identity/context, numeric encoding
      contract not frozen yet;
    - ``HUMAN_GATE``: publication requires an explicit human decision.
    ``model_feature_status`` mirrors the spec distinction
    RETAINED_IDENTITY / MODEL_FEATURE / MODEL_FEATURE_PENDING / HUMAN_GATE.
    """

    field: str
    support_state: str = "UPSTREAM_PRE_INTERFACE_REQUIRED"
    pre_status: str = "NEEDS_PRE_REFERENCE_BINDING"
    publication_status: str = "PUBLISHED"
    model_feature_status: str = "RETAINED_IDENTITY"
    provenance_reference_id: str | None = None
    freeze_id: str | None = None
    reference_id: str | None = None
    value: object | None = None
    unit: str | None = None
    provenance: dict | None = None
    fallback_level: str | None = None
    published: bool = False


# Tranche 2.2 typed M1 input contract.  Every manuscript static/reference
# field must be published by PRE through a typed object (never read by M1
# directly from raw/BTS/reference files).  ``schedule.signed_minutes_to_crs_departure``
# is a DYNAMIC current-AR variable (already inside the recurrent sequence) and
# is deliberately NOT a static/reference field here (Tranche 2.1 duplicated
# fusion removed).
M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE: dict[str, str] = {
    "route_context": "NEEDS_PRE_REFERENCE_BINDING",
    "carrier_context": "NEEDS_PRE_REFERENCE_BINDING",
    "aircraft_identity": "AVAILABLE_BUT_NOT_PUBLISHED_TO_M1",
    "schedule_reference": "AVAILABLE_BUT_NOT_PUBLISHED_TO_M1",
    "turnaround_reference": "AVAILABLE_BUT_NOT_PUBLISHED_TO_M1",
    "taxi_reference": "AVAILABLE_BUT_NOT_PUBLISHED_TO_M1",
}


def _static_reference_field(name: str) -> M1StaticReferenceField:
    return M1StaticReferenceField(
        field=name,
        support_state="UPSTREAM_PRE_INTERFACE_REQUIRED",
        pre_status=M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE[name],
    )


class M1StaticReferenceContext(FrozenModel):
    """Typed separately-retained static/reference context for M1.

    Manuscript Section 3-4: static context (schedule / route / aircraft /
    turnaround reference / taxi reference / carrier) is retained separately —
    ``RETAINED_IDENTITY`` (episode identity, provenance, lineage,
    routing/reference lookup) is NOT automatically a numeric MODEL_FEATURE.
    A field becomes a numeric predictor only after PRE publishes a canonical
    typed path (then a deterministic encoding contract may be designed).

    A default instance represents the typed missing state before a PRE object
    is supplied. ``static_reference_context_from_pre`` replaces it with the
    self-contained PRE publication; only MODEL_FEATURE fields may enter the
    numeric branch. The Tranche 2.1 schedule-countdown duplicate is removed.
    """

    route_context: M1StaticReferenceField = Field(
        default_factory=lambda: _static_reference_field("route_context"))
    carrier_context: M1StaticReferenceField = Field(
        default_factory=lambda: _static_reference_field("carrier_context"))
    aircraft_identity: M1StaticReferenceField = Field(
        default_factory=lambda: _static_reference_field("aircraft_identity"))
    schedule_reference: M1StaticReferenceField = Field(
        default_factory=lambda: _static_reference_field("schedule_reference"))
    turnaround_reference: M1StaticReferenceField = Field(
        default_factory=lambda: _static_reference_field("turnaround_reference"))
    taxi_reference: M1StaticReferenceField = Field(
        default_factory=lambda: _static_reference_field("taxi_reference"))
    static_context_status: str = "STATIC_REFERENCE_CONTEXT_PENDING_PRE"
    fusion: str = "CONCAT_RECURRENT_FAST_PLUS_OPTIONAL_STATIC"
    implementation_choice: str = (
        "ROUND2_2_DETERMINISTIC_CURRENT_AR_BLOCK_NO_SEARCH"
    )

    @property
    def schedule_reference_context(self) -> M1StaticReferenceField:
        """Read-only compatibility alias for pre-Tranche3 artifact readers."""
        return self.schedule_reference

    def support(self, field: str) -> str:
        if field == "schedule_reference_context":
            field = "schedule_reference"
        if field in M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE:
            return getattr(self, field).support_state
        if field in (
            "live_aircraft_availability", "gate", "crew", "slot",
            "standby_aircraft",
        ):
            raise ValueError(f"M1_STATIC_CONTEXT_FORBIDDEN:{field}")
        raise ValueError(f"M1_STATIC_CONTEXT_UNKNOWN:{field}")

    def pre_status(self, field: str) -> str:
        if field == "schedule_reference_context":
            field = "schedule_reference"
        if field not in M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE:
            raise ValueError(f"M1_STATIC_CONTEXT_UNKNOWN:{field}")
        return getattr(self, field).pre_status

    def published_fields(self) -> tuple[str, ...]:
        """Fields PRE has published (``published=True``), in canonical order."""
        return tuple(
            field for field in M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE
            if getattr(self, field).published
        )

    def model_feature_fields(self) -> tuple[str, ...]:
        """Published fields whose deterministic encoding is a MODEL_FEATURE.

        RETAINED_IDENTITY fields never enter ``c_static``; they stay in the
        M1 input lineage only.
        """
        return tuple(
            field for field in self.published_fields()
            if getattr(self, field).model_feature_status == "MODEL_FEATURE"
        )

    def with_published_field(
        self, field: str, *, publication_status: str = "PUBLISHED",
        model_feature_status: str, provenance_reference_id: str | None = None,
        freeze_id: str | None = None, reference_id: str | None = None,
        value=None, unit: str | None = None, provenance: dict | None = None,
        fallback_level: str | None = None, support_state: str = "SUPPORTED",
    ) -> "M1StaticReferenceContext":
        """Return a copy with one field published (typed PRE interface)."""
        if field == "schedule_reference_context":
            field = "schedule_reference"
        if field not in M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE:
            raise ValueError(f"M1_STATIC_CONTEXT_UNKNOWN:{field}")
        current = getattr(self, field)
        updated = current.model_copy(update={
            "support_state": support_state,
            "pre_status": "AVAILABLE_ALREADY",
            "publication_status": publication_status,
            "model_feature_status": model_feature_status,
            "provenance_reference_id": provenance_reference_id,
            "freeze_id": freeze_id,
            "reference_id": reference_id or provenance_reference_id,
            "value": value,
            "unit": unit,
            "provenance": provenance,
            "fallback_level": fallback_level,
            "published": True,
        })
        return self.model_copy(update={field: updated,
                                       "static_context_status": "PRE_PUBLISHED"})


def static_reference_context_from_pre(
    publication: dict | None,
) -> "M1StaticReferenceContext":
    """Rebuild the typed M1 context from PRE's plain publication metadata.

    PRE never imports M1; it writes ``PREState.static_reference_publication``
    as a plain per-field dict ``{publication_status, model_feature_status,
    provenance_reference_id, freeze_id}``.  This helper rebuilds the typed
    ``M1StaticReferenceContext`` at the M1 boundary so every PRE-published
    field is marked ``published=True`` (support_state SUPPORTED) and only
    MODEL_FEATURE fields may enter ``c_static``.
    """
    context = M1StaticReferenceContext()
    for field, meta in (publication or {}).items():
        if field == "schedule_reference_context":
            field = "schedule_reference"
        if field not in M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE:
            continue
        context = context.with_published_field(
            field,
            publication_status=meta.get("publication_status", "PUBLISHED"),
            model_feature_status=meta.get(
                "model_feature_status", "MODEL_FEATURE_PENDING"),
            provenance_reference_id=meta.get("provenance_reference_id"),
            freeze_id=meta.get("freeze_id"),
            reference_id=meta.get("reference_id"),
            value=meta.get("value"),
            unit=meta.get("unit"),
            provenance=meta.get("provenance"),
            fallback_level=meta.get("fallback_level"),
            support_state=meta.get("support_state", "SUPPORTED"),
        )
    return context


class M1V2TargetLabel(TargetLabel):
    """Typed V2 training label for one primitive target."""

    target_name: V2TargetName
    episode_id: str
    decision_node_id: str
    target_definition_id: str
    target_definition_version: str
    label_status: Literal["EXACT", "INTERVAL", "INACTIVE"]
    provenance: tuple[ProvenanceRef, ...]
    split: Literal["train", "calibration", "development", "test"]
    episode_date: date
    abstention_reason: str | None = None
    # Public absolute predecessor in-block event time (ISO UTC) and the
    # decision time.  Only the internal hazard-coordinate label carries them;
    # they preserve the public T_IB_A00 identity even when R_IB == 0.
    t_ib_a00_utc: str | None = None
    decision_time_utc: str | None = None

    @model_validator(mode="after")
    def status_matches_value(self):
        if self.label_status == "INACTIVE" and self.active:
            raise ValueError("inactive label status cannot be active")
        if self.label_status == "EXACT" and self.exact_minutes is None:
            raise ValueError("exact label status requires exact minutes")
        if self.label_status == "INTERVAL" and self.lower_minutes is None:
            raise ValueError("interval label status requires bounds")
        return self

    @model_validator(mode="after")
    def hazard_label_coordinate_contract(self):
        if self.target_name != M1_V2_HAZARD_COORDINATE_TARGET:
            return self
        if self.exact_minutes is not None:
            if self.t_ib_a00_utc is None or self.decision_time_utc is None:
                raise ValueError(
                    "hazard-coordinate label requires the public T_IB_A00 and decision time"
                )
            expected = remaining_hazard_coordinate_minutes(
                self.t_ib_a00_utc, self.decision_time_utc
            )
            if expected is None or abs(expected - self.exact_minutes) > 1e-6:
                raise ValueError("hazard-coordinate label inconsistent with T_IB_A00")
        return self


class M1V2Scenario(FrozenModel):
    """One V2 joint draw from the formal chain T_IB_A00 -> D_OB -> D_TX.

    Derived quantities per scenario:
        R_IB = max(0, T_IB_A00 - t)
        D_TO = D_OB + D_TX

    ``delta_ob_minutes`` / ``t_tx_minutes`` / ``tx_reference_minutes`` are
    LEGACY_V1 / LABEL_CONSTRUCTION / EVALUATION_AUXILIARY provenance only and
    never condition V2 sampling or V2 downstream quantities.
    """

    episode_id: str
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    operational_stage: str
    decision_time_utc: str | None
    t_ib_a00_utc: str | None
    d_ob_minutes: float | None
    d_tx_minutes: float | None
    scheduled_ob_utc: str | None = None
    t_ib_observed: bool = False
    d_ob_observed: bool = False
    d_tx_observed: bool = False
    t_ib_support: str = "ABSTAIN"
    d_ob_support: str = "ABSTAIN"
    d_tx_support: str = "ABSTAIN"
    overflow_t_ib: bool = False
    overflow_d_ob: bool = False
    overflow_d_tx: bool = False
    scenario_seed_key: str
    delta_ob_minutes: float | None = None
    t_tx_minutes: float | None = None
    tx_reference_minutes: float | None = None
    taxi_reference_id: str | None = None
    taxi_reference_hash: str | None = None
    taxi_reference_fallback_level: str | None = None
    taxi_reference_support_state: str | None = None

    @model_validator(mode="after")
    def formal_v2_contract(self):
        if self.d_ob_minutes is not None and self.d_ob_minutes < 0:
            raise ValueError("D_OB must be nonnegative")
        if self.d_tx_minutes is not None and self.d_tx_minutes < 0:
            raise ValueError("D_TX must be nonnegative")
        d_to = self.d_to_minutes
        if d_to is not None and (
            d_to < 0
            or self.d_ob_minutes is None
            or self.d_tx_minutes is None
            or abs(d_to - (self.d_ob_minutes + self.d_tx_minutes)) > 1e-6
        ):
            raise ValueError("D_TO must equal D_OB + D_TX per scenario")
        r_ib = self.r_ib_minutes
        if r_ib is not None and r_ib < 0:
            raise ValueError("R_IB must be nonnegative")
        return self

    @computed_field
    @property
    def r_ib_minutes(self) -> float | None:
        """Derived R_IB = max(0, T_IB_A00 - t); never a trained head."""
        return derived_r_ib_minutes(self.t_ib_a00_utc, self.decision_time_utc)

    @computed_field
    @property
    def d_to_minutes(self) -> float | None:
        """Derived D_TO = D_OB + D_TX per scenario; never a separate head."""
        return derived_d_to_from_primitives(self.d_ob_minutes, self.d_tx_minutes)

    @computed_field
    @property
    def d_to_support(self) -> str:
        if self.d_to_minutes is None:
            return "ABSTAIN"
        if "ABSTAIN" in {self.d_ob_support, self.d_tx_support}:
            return "ABSTAIN"
        return "SUPPORTED"

    @computed_field
    @property
    def t_ib_a00_minutes(self) -> float | None:
        """Absolute predecessor in-block time as minutes-since-epoch (recovery aid)."""
        if self.t_ib_a00_utc is None:
            return None
        try:
            return datetime.fromisoformat(self.t_ib_a00_utc).timestamp() / 60.0
        except ValueError:
            return None

    @property
    def target_semantics(self) -> dict[str, str]:
        names = M1_V2_ALL_TARGETS + M1_V2_LEGACY_AUXILIARY_TARGETS
        return {name: external_target_name(name) for name in names}
