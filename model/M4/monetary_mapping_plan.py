"""M-FROZEN candidate: constructed EUR monetary mapping plan (G-Monetary).

Functional form fixed by contract (G-Monetary, Path B supplement 2.2, decision
2026-08-24 D1 = OPTION_A_DUAL_LAYER with EUR-native ops labels):

    ops(k)  = c_ops(k) * CU_k                    (ops layer, per component)
    comp(D) = EU261_staircase(D)                 (compensation layer, optional flag_comp)
    J_post  = sum_k ops(k) + flag_comp * comp(D)

Both layers are EUR-native: the ops layer is a constructed scale anchored on
the EUROCONTROL 2004/2015 EUR-per-minute literature, and the compensation
layer is the EU261 EUR regulatory staircase.  J_post stays a two-part
expression without any cross-currency conversion (OPTION_A_DUAL_LAYER).

Nothing here is an empirical cost.  The paper statement is fixed:
"constructed scale anchored on EUROCONTROL EUR-basis values, not a currency
conversion".  Registry-level numeric freeze (FROZEN_ASSUMPTION_GROUNDED) is
per-component: components whose literature anchor exists carry numeric
values; components whose per-CU anchor is not in the retrieved literature
stay ``HUMAN_DECISION_REQUIRED`` with an explicit reason (no zero-fill).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.value_objects import FrozenModel

OPS_LAYER = "OPERATIONS"
PASSENGER_LAYER = "PASSENGER"

LOW_SCALE = 0.5
BASE_SCALE = 1.0
HIGH_SCALE = 2.0
SCALE_BAND_IDS = ("LOW", "BASE", "HIGH")

OPS_ANCHOR_UNIT = "constructed_EUR_per_CU"
MONETARY_SYSTEM_ID = "EUR"


class NumericFreezeStatus(str, Enum):
    AWAITING_HUMAN_CONFIRMATION = "AWAITING_HUMAN_CONFIRMATION"
    FROZEN_ASSUMPTION_GROUNDED = "FROZEN_ASSUMPTION_GROUNDED"


class NumericAnchorStatus(str, Enum):
    FROZEN_ASSUMPTION_GROUNDED = "FROZEN_ASSUMPTION_GROUNDED"
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"


class OpsCostBand(FrozenModel):
    """One c_ops sensitivity band. LOW/HIGH are global 0.5x/2.0x scales."""

    band_id: str = Field(min_length=1)
    scale_factor: float = Field(gt=0)
    per_cu_money: float | None = Field(default=None, ge=0)
    unit: str = OPS_ANCHOR_UNIT


class OpsComponentRule(FrozenModel):
    """ops(k) = c_ops(k) * CU_k for one consequence component."""

    component_id: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    base_per_cu_money: float | None = Field(default=None, ge=0)
    base_reference: tuple[str, ...] = Field(min_length=1)
    anchor_status: NumericAnchorStatus = NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED
    anchor_reason: str | None = Field(default=None, min_length=1)
    bands: tuple[OpsCostBand, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def explicit_component_and_bands(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("MONETARY_MAPPING_PLAN_UNKNOWN_COMPONENT")
        if tuple(band.band_id for band in self.bands) != SCALE_BAND_IDS:
            raise ValueError("MONETARY_MAPPING_PLAN_BANDS_MUST_BE_LOW_BASE_HIGH")
        factors = tuple(band.scale_factor for band in self.bands)
        if factors != (LOW_SCALE, BASE_SCALE, HIGH_SCALE):
            raise ValueError("MONETARY_MAPPING_PLAN_BAND_FACTORS_INVALID")
        if self.base_per_cu_money is not None:
            expected = (
                self.base_per_cu_money * LOW_SCALE,
                self.base_per_cu_money * BASE_SCALE,
                self.base_per_cu_money * HIGH_SCALE,
            )
            actual = tuple(band.per_cu_money for band in self.bands)
            if actual != expected:
                raise ValueError("MONETARY_MAPPING_PLAN_BAND_VALUES_MISMATCH")
            if self.anchor_status is not NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED:
                raise ValueError("MONETARY_MAPPING_PLAN_FROZEN_ANCHOR_REQUIRES_FROZEN_STATUS")
        else:
            if any(band.per_cu_money is not None for band in self.bands):
                raise ValueError("MONETARY_MAPPING_PLAN_PARTIAL_NUMERIC_BANDS_FORBIDDEN")
            if self.anchor_status is not NumericAnchorStatus.HUMAN_DECISION_REQUIRED:
                raise ValueError("MONETARY_MAPPING_PLAN_PENDING_ANCHOR_REQUIRES_HUMAN_STATUS")
            if not self.anchor_reason:
                raise ValueError("MONETARY_MAPPING_PLAN_PENDING_ANCHOR_REQUIRES_REASON")
        return self


class EU261Tier(FrozenModel):
    """One EU261 compensation tier (Regulation (EC) No 261/2004 Art. 7)."""

    max_distance_km: int | None = Field(default=None, ge=1)
    compensation_eur: int = Field(ge=0)

    @model_validator(mode="after")
    def distance_tier_ordering(self):
        if self.max_distance_km is None and self.compensation_eur != 600:
            raise ValueError("EU261_OPEN_ENDED_TIER_MUST_BE_600_EUR")
        return self


class EU261Staircase(FrozenModel):
    """comp(D) = EU261_staircase(D): 250/400/600 EUR tiers, 3h trigger.

    Decision 2026-08-24 D1b: tau_comp selected = 180 minutes (aligned with the
    regulation 3h trigger); 150 and 210 stay as sensitivity values.
    """

    trigger_minutes: int = Field(default=180, ge=1)
    tau_comp_options_minutes: tuple[int, ...] = (150, 180, 210)
    tau_comp_selected_minutes: int = Field(default=180, ge=1)
    tau_comp_sensitivity_minutes: tuple[int, ...] = (150, 210)
    tiers: tuple[EU261Tier, ...] = Field(min_length=3)
    regulatory_reference: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def staircase_contract(self):
        amounts = tuple(tier.compensation_eur for tier in self.tiers)
        if amounts != (250, 400, 600):
            raise ValueError("EU261_TIERS_MUST_BE_250_400_600_EUR")
        if tuple(tier.max_distance_km for tier in self.tiers[:-1]) != (1500, 3500):
            raise ValueError("EU261_DISTANCE_THRESHOLDS_MUST_BE_1500_3500_KM")
        if self.tiers[-1].max_distance_km is not None:
            raise ValueError("EU261_FINAL_TIER_MUST_BE_OPEN_ENDED")
        if self.trigger_minutes not in self.tau_comp_options_minutes:
            raise ValueError("EU261_TRIGGER_MUST_BE_IN_TAU_OPTIONS")
        if self.tau_comp_selected_minutes not in self.tau_comp_options_minutes:
            raise ValueError("EU261_SELECTED_TAU_MUST_BE_IN_TAU_OPTIONS")
        if self.tau_comp_selected_minutes in self.tau_comp_sensitivity_minutes:
            raise ValueError("EU261_SELECTED_TAU_MUST_NOT_BE_IN_SENSITIVITY")
        if not set(self.tau_comp_sensitivity_minutes) <= set(self.tau_comp_options_minutes):
            raise ValueError("EU261_TAU_SENSITIVITY_MUST_BE_IN_TAU_OPTIONS")
        return self

    def compensation_eur(
        self,
        *,
        delay_minutes: int,
        distance_km: int,
        tau_comp_minutes: int | None = None,
    ) -> float:
        tau = tau_comp_minutes or self.tau_comp_selected_minutes
        if delay_minutes < tau or distance_km < 0:
            return 0.0
        for tier in self.tiers:
            if tier.max_distance_km is None or distance_km <= tier.max_distance_km:
                return float(tier.compensation_eur)
        return 0.0


class ConversionOption(FrozenModel):
    option_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    recommended: bool = False


class MonetaryConversionPlan(FrozenModel):
    status: str = Field(default="PLAN_REQUIRING_HUMAN_CONFIRMATION", min_length=1)
    issue: str = Field(min_length=1)
    options: tuple[ConversionOption, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def single_recommendation(self):
        if sum(option.recommended for option in self.options) != 1:
            raise ValueError("MONETARY_CONVERSION_PLAN_REQUIRES_EXACTLY_ONE_RECOMMENDED_OPTION")
        return self


class MonetaryMappingPlanRegistry(FrozenModel):
    """Assumption-grounded monetary mapping registry (EUR-native, D1 frozen)."""

    schema_version: str = Field(default="M4_EUR_MAPPING_ASSUMPTION_GROUNDED_FROZEN_V1", min_length=1)
    registry_id: str = Field(default="M4_EUR_MAPPING_ASSUMPTION_GROUNDED_FROZEN_V1", min_length=1)
    monetary_system_id: str = Field(default=MONETARY_SYSTEM_ID, min_length=1)
    numeric_freeze_status: NumericFreezeStatus = NumericFreezeStatus.AWAITING_HUMAN_CONFIRMATION
    monetary_ground_truth_claim: bool = False
    claim_statement: str = ""
    ops_components: tuple[OpsComponentRule, ...] = Field(min_length=7)
    eu261: EU261Staircase
    conversion_plan: MonetaryConversionPlan
    references: tuple[str, ...] = Field(min_length=1)
    final_test_access_count: int = 0
    paper_full_run: bool = False
    registry_hash: str = ""

    @model_validator(mode="after")
    def complete_plan(self):
        if self.final_test_access_count != 0:
            raise ValueError("MONETARY_MAPPING_PLAN_FINAL_TEST_ACCESS_VIOLATION")
        if self.paper_full_run:
            raise ValueError("MONETARY_MAPPING_PLAN_PAPER_FULL_VIOLATION")
        if self.monetary_ground_truth_claim:
            raise ValueError("MONETARY_MAPPING_PLAN_CANNOT_CLAIM_MONETARY_GROUND_TRUTH")
        if tuple(rule.component_id for rule in self.ops_components) != CONSEQUENCE_COMPONENTS:
            raise ValueError("MONETARY_MAPPING_PLAN_REQUIRES_EXACT_SEVEN_COMPONENTS")
        if self.numeric_freeze_status is NumericFreezeStatus.FROZEN_ASSUMPTION_GROUNDED:
            if not any(
                rule.anchor_status is NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED
                for rule in self.ops_components
            ):
                raise ValueError(
                    "MONETARY_MAPPING_PLAN_FROZEN_REQUIRES_AT_LEAST_ONE_FROZEN_ANCHOR"
                )
            frozen_missing = [
                rule.component_id for rule in self.ops_components
                if rule.anchor_status is NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED
                and rule.base_per_cu_money is None
            ]
            if frozen_missing:
                raise ValueError(
                    "MONETARY_MAPPING_PLAN_FROZEN_REQUIRES_ALL_FROZEN_ANCHOR_VALUES:"
                    + ",".join(frozen_missing)
                )
            if self.conversion_plan.status != "FROZEN":
                raise ValueError("MONETARY_MAPPING_PLAN_FROZEN_REQUIRES_FROZEN_CONVERSION_PLAN")
            if not self.claim_statement:
                raise ValueError("MONETARY_MAPPING_PLAN_FROZEN_REQUIRES_CLAIM_STATEMENT")
        if self.registry_hash and self.registry_hash != self.digest():
            raise ValueError("MONETARY_MAPPING_PLAN_REGISTRY_HASH_MISMATCH")
        return self

    def registry_payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload.pop("registry_hash", None)
        return payload

    def digest(self) -> str:
        return content_id(self.registry_payload())

    @property
    def numeric_frozen(self) -> bool:
        return self.numeric_freeze_status is NumericFreezeStatus.FROZEN_ASSUMPTION_GROUNDED

    @property
    def pending_anchor_components(self) -> tuple[str, ...]:
        return tuple(
            rule.component_id for rule in self.ops_components
            if rule.anchor_status is NumericAnchorStatus.HUMAN_DECISION_REQUIRED
        )

    def ops_money(self, cu_by_component: dict[str, float]) -> dict[str, float] | None:
        """ops(k) = c_ops(k) * CU_k for frozen anchors; None until numbers freeze."""
        if not self.numeric_frozen:
            return None
        if set(cu_by_component) != set(CONSEQUENCE_COMPONENTS):
            raise ValueError("MONETARY_MAPPING_PLAN_COMPONENT_KEYS_INVALID")
        return {
            rule.component_id: float(cu_by_component[rule.component_id]) * rule.base_per_cu_money
            for rule in self.ops_components
            if rule.anchor_status is NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED
        }


__all__ = [
    "EU261Staircase",
    "EU261Tier",
    "MonetaryConversionPlan",
    "MonetaryMappingPlanRegistry",
    "NumericAnchorStatus",
    "NumericFreezeStatus",
    "OpsComponentRule",
    "OpsCostBand",
]
