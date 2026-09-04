"""Provenance-complete monetary mapping: ``C_k^CU`` -> ``L_k^m``.

CU remains monetary-system independent. A mapping registry supplies the only
allowed interpretation under one monetary system and never mutates CU.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .consequence_ontology import CONSEQUENCE_COMPONENTS
from .identity import content_id
from .value_objects import FrozenModel


class MonetarySystem(str, Enum):
    RMB = "RMB"


class MonetaryMappingStatus(str, Enum):
    FROZEN = "FROZEN"
    TEST_ONLY = "TEST_ONLY"
    NOT_FROZEN = "NOT_FROZEN"


class MonetaryMappingFunction(str, Enum):
    LINEAR_SCALE = "LINEAR_SCALE"


class MonetarySourceType(str, Enum):
    LITERATURE = "LITERATURE"
    OPERATIONAL_RULE = "OPERATIONAL_RULE"
    REGULATORY_REFERENCE = "REGULATORY_REFERENCE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    EXPERT_JUDGEMENT = "EXPERT_JUDGEMENT"
    HYBRID = "HYBRID"
    TEST_ONLY = "TEST_ONLY"


class MonetaryMappingParameter(FrozenModel):
    """One named parameter; anonymous weight/gamma/omega is prohibited."""

    parameter_name: str = Field(min_length=1)
    value: float = Field(ge=0)
    unit: str = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)


class MonetaryMappingRule(FrozenModel):
    """One component mapping ``f_k^m`` with complete source lineage."""

    monetary_system_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    mapping_function: MonetaryMappingFunction
    parameter_version: str = Field(min_length=1)
    source_type: MonetarySourceType
    reference: tuple[str, ...] = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    parameters: tuple[MonetaryMappingParameter, ...] = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **values) -> "MonetaryMappingRule":
        payload = {
            **values,
            "mapping_function": (
                values["mapping_function"].value
                if isinstance(values["mapping_function"], MonetaryMappingFunction)
                else values["mapping_function"]
            ),
            "source_type": (
                values["source_type"].value
                if isinstance(values["source_type"], MonetarySourceType)
                else values["source_type"]
            ),
        }
        return cls(**payload, rule_hash=content_id(payload))

    @model_validator(mode="after")
    def complete_mapping(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("MONETARY_MAPPING_UNKNOWN_COMPONENT")
        names = tuple(item.parameter_name for item in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError("MONETARY_MAPPING_DUPLICATE_PARAMETER")
        if self.mapping_function is MonetaryMappingFunction.LINEAR_SCALE and names != (
            "money_per_cu",
        ):
            raise ValueError("LINEAR_MAPPING_REQUIRES_NAMED_MONEY_PER_CU")
        payload = self.model_dump(mode="json", exclude={"rule_hash"})
        if self.rule_hash != content_id(payload):
            raise ValueError("MONETARY_MAPPING_RULE_HASH_MISMATCH")
        return self

    def map_cu(self, value_cu: float) -> float:
        if self.mapping_function is MonetaryMappingFunction.LINEAR_SCALE:
            return float(value_cu) * self.parameters[0].value
        raise ValueError("MONETARY_MAPPING_FUNCTION_NOT_IMPLEMENTED")


class MonetaryMappingRegistry(FrozenModel):
    """Versioned mappings for one monetary system.

    `NOT_FROZEN` carries no mappings. `TEST_ONLY` is executable for contract
    tests but is never scientific authority. Only `FROZEN` may support an
    authoritative real-system ranking.
    """

    monetary_system_id: str = Field(min_length=1)
    registry_id: str = Field(min_length=1)
    registry_version: str = Field(default="UNFROZEN", min_length=1)
    registry_hash: str = ""
    freeze_status: MonetaryMappingStatus = MonetaryMappingStatus.NOT_FROZEN
    freeze_id: str | None = None
    reference_period: str | None = None
    component_mappings: dict[str, MonetaryMappingRule] = Field(default_factory=dict)
    provenance: tuple[str, ...] = ()
    final_test_access_count: int = 0
    paper_full_run: bool = False

    @model_validator(mode="after")
    def frozen_mapping_requires_lineage(self):
        if self.final_test_access_count != 0:
            raise ValueError("MONETARY_MAPPING_FINAL_TEST_ACCESS_VIOLATION")
        if self.paper_full_run:
            raise ValueError("MONETARY_MAPPING_PAPER_FULL_VIOLATION")
        executable = self.freeze_status in {
            MonetaryMappingStatus.FROZEN,
            MonetaryMappingStatus.TEST_ONLY,
        }
        if executable and (
            not self.component_mappings
            or not self.freeze_id
            or not self.reference_period
            or not self.provenance
        ):
            raise ValueError("EXECUTABLE_MONETARY_MAPPING_REQUIRES_LINEAGE")
        if not executable and self.component_mappings:
            raise ValueError("NOT_FROZEN_MONETARY_MAPPING_MUST_HAVE_NO_MAPPINGS")
        if set(self.component_mappings) - set(CONSEQUENCE_COMPONENTS):
            raise ValueError("MONETARY_MAPPING_REGISTRY_UNKNOWN_COMPONENT")
        if any(
            key != rule.component_id
            or rule.monetary_system_id != self.monetary_system_id
            or rule.freeze_id != self.freeze_id
            for key, rule in self.component_mappings.items()
        ):
            raise ValueError("MONETARY_MAPPING_REGISTRY_RULE_MISMATCH")
        if self.freeze_status is MonetaryMappingStatus.TEST_ONLY and any(
            rule.source_type is not MonetarySourceType.TEST_ONLY
            for rule in self.component_mappings.values()
        ):
            raise ValueError("TEST_MAPPING_REQUIRES_TEST_ONLY_SOURCE")
        if self.freeze_status is MonetaryMappingStatus.FROZEN and any(
            rule.source_type is MonetarySourceType.TEST_ONLY
            for rule in self.component_mappings.values()
        ):
            raise ValueError("SCIENTIFIC_MAPPING_CANNOT_USE_TEST_SOURCE")
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
        """Legacy executable check; TEST_ONLY remains runnable in tests."""
        return self.freeze_status in {
            MonetaryMappingStatus.FROZEN,
            MonetaryMappingStatus.TEST_ONLY,
        }

    @property
    def authoritative(self) -> bool:
        return self.freeze_status is MonetaryMappingStatus.FROZEN

    def to_component_money(
        self, cu_by_component: dict[str, float]
    ) -> dict[str, float] | None:
        if not self.frozen:
            return None
        losses = {}
        for component, cu in cu_by_component.items():
            rule = self.component_mappings.get(component)
            if rule is None:
                raise ValueError(f"MONETARY_MAPPING_COMPONENT_UNKNOWN:{component}")
            losses[component] = rule.map_cu(cu)
        return losses

    def to_money(self, cu_by_component: dict[str, float]) -> float | None:
        component_losses = self.to_component_money(cu_by_component)
        return None if component_losses is None else sum(component_losses.values())

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
    "MonetaryMappingFunction",
    "MonetaryMappingParameter",
    "MonetaryMappingRegistry",
    "MonetaryMappingRule",
    "MonetaryMappingStatus",
    "MonetarySourceType",
    "MonetarySystem",
]
