"""Monetary mapping contract: consequence unit ``C_k^CU`` -> monetary loss ``L_k^m``.

The first formal monetary system is ``RMB``.  Monetary mapping parameters are
deliberately separate from CU normalization parameters; when they are not
scientifically frozen the registry carries ``VALUATION_NOT_FROZEN`` and no
authoritative ranking may be produced.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .identity import content_id
from .value_objects import FrozenModel


class MonetarySystem(str, Enum):
    RMB = "RMB"


class MonetaryMappingStatus(str, Enum):
    FROZEN = "FROZEN"
    NOT_FROZEN = "NOT_FROZEN"


class MonetaryMappingRule(FrozenModel):
    """One monetary mapping parameter for one consequence component."""

    component_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    weight: float = Field(gt=0)
    parameter_provenance: tuple[str, ...] = ()


class MonetaryMappingRegistry(FrozenModel):
    """Train-frozen mapping ``L_k^m = omega_k^m * C_k^CU`` under system ``m``.

    A registry with ``freeze_status = NOT_FROZEN`` carries no component
    weights: the mapping is unavailable and authoritative ranking must remain
    unavailable rather than fall back to raw CU ranking.
    """

    monetary_system_id: str = Field(min_length=1)
    registry_id: str = Field(min_length=1)
    registry_hash: str = ""
    mapping_form: str = "LINEAR"
    freeze_status: MonetaryMappingStatus = MonetaryMappingStatus.NOT_FROZEN
    freeze_id: str | None = None
    reference_period: str | None = None
    component_weights: dict[str, MonetaryMappingRule] = Field(default_factory=dict)
    parameter_provenance: tuple[str, ...] = ()
    final_test_access_count: int = 0
    paper_full_run: bool = False

    @model_validator(mode="after")
    def frozen_mapping_requires_weights(self):
        if self.mapping_form != "LINEAR":
            raise ValueError("MONETARY_MAPPING_FORM_UNSUPPORTED")
        if self.final_test_access_count != 0:
            raise ValueError("MONETARY_MAPPING_FINAL_TEST_ACCESS_VIOLATION")
        if self.paper_full_run:
            raise ValueError("MONETARY_MAPPING_PAPER_FULL_VIOLATION")
        if self.freeze_status is MonetaryMappingStatus.FROZEN:
            if not self.component_weights or not self.freeze_id or not self.reference_period:
                raise ValueError("FROZEN_MONETARY_MAPPING_REQUIRES_WEIGHTS_AND_LINEAGE")
        elif self.component_weights:
            raise ValueError("NOT_FROZEN_MONETARY_MAPPING_MUST_HAVE_NO_WEIGHTS")
        if self.registry_hash and self.registry_hash != self.digest():
            raise ValueError("MONETARY_MAPPING_REGISTRY_HASH_MISMATCH")
        return self

    def registry_payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload.pop("registry_hash", None)
        return payload

    def digest(self) -> str:
        return content_id(self.registry_payload())

    @property
    def frozen(self) -> bool:
        return self.freeze_status is MonetaryMappingStatus.FROZEN

    def to_money(self, cu_by_component: dict[str, float]) -> float | None:
        """Return ``L^m = sum_k omega_k^m * C_k^CU`` or None when unfrozen."""
        if not self.frozen or not self.component_weights:
            return None
        total = 0.0
        for component, cu in cu_by_component.items():
            rule = self.component_weights.get(component)
            if rule is None:
                raise ValueError(f"MONETARY_MAPPING_COMPONENT_UNKNOWN:{component}")
            total += rule.weight * float(cu)
        return total

    @classmethod
    def not_frozen(
        cls, *, monetary_system_id: str = "RMB", registry_id: str = "RMB_NOT_FROZEN"
    ) -> "MonetaryMappingRegistry":
        return cls(
            monetary_system_id=monetary_system_id,
            registry_id=registry_id,
            freeze_status=MonetaryMappingStatus.NOT_FROZEN,
        )


__all__ = [
    "MonetaryMappingRegistry",
    "MonetaryMappingRule",
    "MonetaryMappingStatus",
    "MonetarySystem",
]
