from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from model.M2.contracts import ConsequenceRow, NativeQuantity, ValuationStatus
from model.common.enums import SupportState


class ValuationRuleStatus(str, Enum):
    FROZEN = "FROZEN"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"


@dataclass(frozen=True)
class ValuationRule:
    component_id: str
    rule_id: str
    version: str
    multiplier: float
    status: ValuationRuleStatus = ValuationRuleStatus.DEVELOPMENT_ONLY


class ValuationRegistry:
    def __init__(self, registry_id: str, rules):
        self.registry_id = registry_id
        self.rules = {rule.component_id: rule for rule in rules}

    @classmethod
    def smoke(cls):
        return cls(
            "DEV-1",
            [
                ValuationRule(name, f"{name.upper()}_LINEAR", "DEV-1", multiplier)
                for name, multiplier in {
                    "F_continuity": 2,
                    "F_execution": 1,
                    "F_propagation": 1.5,
                    "P_time": 0.01,
                    "P_itinerary": 5,
                    "P_service": 3,
                    "R_operating": 1,
                }.items()
            ],
        )

    def value(self, native: NativeQuantity) -> ConsequenceRow:
        aspect = (
            "Flight"
            if native.component_id.startswith("F_")
            else "Passenger"
            if native.component_id.startswith("P_")
            else "Resource"
        )
        base = {
            "component_id": native.component_id,
            "scenario_id": native.scenario_id,
            "aspect": aspect,
            "native_quantity": native.native_quantity,
            "native_unit": native.native_unit,
            "driver": native.driver,
            "support_state": native.support_state,
            "evidence_class": native.evidence_class,
            "reason_code": native.reason_code,
            "provenance": native.provenance,
        }
        if native.support_state is SupportState.ABSTAIN:
            return ConsequenceRow(
                **base,
                constructed_value_cu=None,
                valuation_status=ValuationStatus.VALUATION_UNSUPPORTED,
            )
        rule = self.rules.get(native.component_id)
        if rule is None or rule.status is not ValuationRuleStatus.FROZEN:
            base["reason_code"] = "VALUATION_NOT_FROZEN"
            return ConsequenceRow(
                **base,
                constructed_value_cu=None,
                valuation_status=ValuationStatus.VALUATION_NOT_FROZEN,
                valuation_registry_id=self.registry_id,
                valuation_rule_id=rule.rule_id if rule else None,
                valuation_parameter_version=rule.version if rule else None,
            )
        return ConsequenceRow(
            **base,
            constructed_value_cu=native.native_quantity * rule.multiplier,
            valuation_status=ValuationStatus.VALUATION_FROZEN,
            valuation_registry_id=self.registry_id,
            valuation_rule_id=rule.rule_id,
            valuation_parameter_version=rule.version,
        )
