from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from model.M2.contracts import ConsequenceRow, NativeQuantity
from model.common.cu_normalization import (
    CUNormalizationRegistry,
    CUNormalizationRule,
    CUNormalizationStatus,
)
from model.common.enums import SupportState


class ValuationRuleStatus(str, Enum):
    """Deprecated compatibility status; canonical rules use CUNormalizationRule."""

    FROZEN = "FROZEN"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"


@dataclass(frozen=True)
class ValuationRule:
    """Deprecated compatibility rule; canonical path uses CUNormalizationRule."""

    component_id: str
    rule_id: str
    version: str
    multiplier: float
    status: ValuationRuleStatus = ValuationRuleStatus.DEVELOPMENT_ONLY


class M2CUNormalizationAdapter:
    """Canonical M2 adapter: NativeQuantity -> ConsequenceRow through CU normalization.

    CU normalization (q_k -> C_k^CU) is strictly separate from monetary
    mapping (C_k^CU -> L_k^m), which lives in M4.
    """

    def __init__(self, registry: CUNormalizationRegistry | None = None):
        if registry is not None and not isinstance(registry, CUNormalizationRegistry):
            registry = CUNormalizationRegistry.model_validate(registry)
        self.registry = registry
        self.registry_id = registry.registry_id if registry is not None else "DEV-1"
        self.development_only = registry is None

    @classmethod
    def smoke(cls) -> "M2CUNormalizationAdapter":
        """Development-only fixture adapter; never resolves formal CU."""
        return cls(registry=None)

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
            "source_type": native.source_type,
            "reason_code": native.reason_code,
            "provenance": native.provenance,
        }
        if native.support_state is SupportState.ABSTAIN:
            return ConsequenceRow(
                **base,
                constructed_value_cu=None,
                cu_status=CUNormalizationStatus.CU_UNSUPPORTED,
            )
        if self.development_only or self.registry is None:
            base["reason_code"] = "CU_NORMALIZATION_NOT_FROZEN"
            return ConsequenceRow(
                **base,
                constructed_value_cu=None,
                cu_status=CUNormalizationStatus.CU_NOT_FROZEN,
                cu_normalization_registry_id=self.registry_id,
            )
        try:
            rule = self.registry.rule(native.component_id)
        except ValueError:
            base["reason_code"] = "CU_NORMALIZATION_NOT_FROZEN"
            return ConsequenceRow(
                **base,
                constructed_value_cu=None,
                cu_status=CUNormalizationStatus.CU_NOT_FROZEN,
                cu_normalization_registry_id=self.registry_id,
            )
        constructed = self.registry.to_cu(native.component_id, native.native_quantity)
        if constructed is None:
            base["reason_code"] = "CU_NORMALIZATION_UNAVAILABLE"
            return ConsequenceRow(
                **base,
                constructed_value_cu=None,
                cu_status=CUNormalizationStatus.CU_NOT_FROZEN,
                cu_normalization_registry_id=self.registry_id,
                cu_normalization_rule_id=rule.rule_id,
                cu_normalization_parameter_version=rule.version,
            )
        return ConsequenceRow(
            **base,
            constructed_value_cu=constructed,
            cu_status=CUNormalizationStatus.CU_FROZEN,
            cu_normalization_registry_id=self.registry_id,
            cu_normalization_rule_id=rule.rule_id,
            cu_normalization_parameter_version=rule.version,
        )


class ValuationRegistry(M2CUNormalizationAdapter):
    """Deprecated compatibility alias of M2CUNormalizationAdapter.

    The alias exists only for short-term migration; canonical code must use
    M2CUNormalizationAdapter with a CUNormalizationRegistry.
    """


__all__ = [
    "M2CUNormalizationAdapter",
    "ValuationRegistry",
    "ValuationRule",
    "ValuationRuleStatus",
]
