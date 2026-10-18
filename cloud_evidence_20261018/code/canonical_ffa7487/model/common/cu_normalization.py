"""CU normalization contract: native quantity ``q_k`` -> consequence unit ``C_k^CU``.

The normalization parameters ``c_k^CU`` are train-frozen only.  Using
test-period empirical normalization, future information, or evaluation
outcomes to construct CU is prohibited by the scientific contract.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .identity import content_id
from .value_objects import FrozenModel


class CUNormalizationStatus(str, Enum):
    CU_FROZEN = "CU_FROZEN"
    CU_NOT_FROZEN = "CU_NOT_FROZEN"
    CU_NOT_REQUIRED_FOR_SCOPE = "CU_NOT_REQUIRED_FOR_SCOPE"
    CU_UNSUPPORTED = "CU_UNSUPPORTED"


class CUNormalizationRule(FrozenModel):
    """One train-frozen normalization parameter for one consequence component."""

    component_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    normalization_parameter: float = Field(gt=0)
    freeze_id: str = Field(min_length=1)
    reference_period: str = Field(min_length=1)
    support: str = "SUPPORTED"
    provenance: tuple[str, ...] = ()


class CUNormalizationRegistry(FrozenModel):
    """Train-frozen mapping ``q_k -> C_k^CU = q_k / c_k^CU``.

    The registry is a single source of truth for CU normalization and is
    deliberately distinct from any monetary mapping registry.
    """

    registry_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    reference_period: str = Field(min_length=1)
    rules: dict[str, CUNormalizationRule]
    registry_hash: str = ""
    final_test_access_count: int = 0
    paper_full_run: bool = False

    @model_validator(mode="after")
    def strict_registry_contract(self):
        if not self.rules:
            raise ValueError("CU_NORMALIZATION_EMPTY_REGISTRY")
        if any(
            rule.component_id != component for component, rule in self.rules.items()
        ):
            raise ValueError("CU_NORMALIZATION_RULE_IDENTITY_MISMATCH")
        if self.final_test_access_count != 0:
            raise ValueError("CU_NORMALIZATION_FINAL_TEST_ACCESS_VIOLATION")
        if self.paper_full_run:
            raise ValueError("CU_NORMALIZATION_PAPER_FULL_VIOLATION")
        if self.registry_hash and self.registry_hash != self.digest():
            raise ValueError("CU_NORMALIZATION_REGISTRY_HASH_MISMATCH")
        return self

    def registry_payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload.pop("registry_hash", None)
        return payload

    def digest(self) -> str:
        return content_id(self.registry_payload())

    def rule(self, component_id: str) -> CUNormalizationRule:
        try:
            return self.rules[component_id]
        except KeyError as exc:
            raise ValueError(
                f"CU_NORMALIZATION_COMPONENT_UNKNOWN:{component_id}"
            ) from exc

    def to_cu(self, component_id: str, native_value: float | None) -> float | None:
        """Return ``C_k^CU = q_k / c_k^CU``; None propagates abstention."""
        if native_value is None:
            return None
        rule = self.rule(component_id)
        return float(native_value) / rule.normalization_parameter

    @classmethod
    def from_scales(
        cls,
        *,
        registry_id: str,
        version: str,
        freeze_id: str,
        reference_period: str,
        scales: dict[str, float],
        provenance: tuple[str, ...] = (),
    ) -> "CUNormalizationRegistry":
        if not scales:
            raise ValueError("CU_NORMALIZATION_EMPTY_SCALES")
        rules = {
            component: CUNormalizationRule(
                component_id=component,
                rule_id=f"{component}_TRAIN_MEDIAN_CU",
                version=version,
                normalization_parameter=float(scale),
                freeze_id=freeze_id,
                reference_period=reference_period,
                support="SUPPORTED",
                provenance=provenance,
            )
            for component, scale in scales.items()
        }
        return cls(
            registry_id=registry_id,
            version=version,
            freeze_id=freeze_id,
            reference_period=reference_period,
            rules=rules,
        )


__all__ = [
    "CUNormalizationRegistry",
    "CUNormalizationRule",
    "CUNormalizationStatus",
]
