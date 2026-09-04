"""Canonical constructed-RMB mapping from intermediate CU values.

This module is the corrected monetary boundary:

    C_k (consequence component) -> CU_k -> RMB_k -> risk

``CU`` and ``RMB`` are both constructed representations. ``RMB`` is not
observed currency and this registry never claims monetary ground truth.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

from pydantic import Field, model_validator

from .consequence_ontology import CONSEQUENCE_COMPONENTS
from .identity import content_id
from .value_objects import FrozenModel


class RMBMappingStatus(str, Enum):
    FROZEN = "FROZEN"
    TEST_ONLY = "TEST_ONLY"
    NOT_FROZEN = "NOT_FROZEN"


class RMBMappingFunction(str, Enum):
    LINEAR_SCALE = "LINEAR_SCALE"


class RMBSourceType(str, Enum):
    LITERATURE = "LITERATURE"
    OPERATIONAL_RULE = "OPERATIONAL_RULE"
    REGULATORY_REFERENCE = "REGULATORY_REFERENCE"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    EXPERT_JUDGEMENT = "EXPERT_JUDGEMENT"
    HYBRID = "HYBRID"
    TEST_ONLY = "TEST_ONLY"


class RMBMappingParameter(FrozenModel):
    parameter_name: str = Field(min_length=1)
    value: float = Field(ge=0)
    unit: str = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)


class RMBMappingRule(FrozenModel):
    """One explicit ``f_k(CU_k)`` rule producing a constructed RMB value."""

    constructed_unit_id: str = "RMB"
    input_unit_id: str = "CU"
    component_id: str = Field(min_length=1)
    mapping_function: RMBMappingFunction
    parameter_version: str = Field(min_length=1)
    source_type: RMBSourceType
    reference: tuple[str, ...] = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    parameters: tuple[RMBMappingParameter, ...] = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **values) -> "RMBMappingRule":
        payload = {
            "constructed_unit_id": values.get("constructed_unit_id", "RMB"),
            "input_unit_id": values.get("input_unit_id", "CU"),
            **values,
            "mapping_function": (
                values["mapping_function"].value
                if isinstance(values["mapping_function"], RMBMappingFunction)
                else values["mapping_function"]
            ),
            "source_type": (
                values["source_type"].value
                if isinstance(values["source_type"], RMBSourceType)
                else values["source_type"]
            ),
        }
        return cls(**payload, rule_hash=content_id(payload))

    @model_validator(mode="after")
    def complete_mapping(self):
        if self.constructed_unit_id != "RMB" or self.input_unit_id != "CU":
            raise ValueError("RMB_MAPPING_UNIT_ID_INVALID")
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("RMB_MAPPING_UNKNOWN_COMPONENT")
        names = tuple(item.parameter_name for item in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError("RMB_MAPPING_DUPLICATE_PARAMETER")
        if self.mapping_function is RMBMappingFunction.LINEAR_SCALE and names != (
            "rmb_per_cu",
        ):
            raise ValueError("RMB_LINEAR_MAPPING_PARAMETER_NAME_INVALID")
        payload = self.model_dump(mode="json", exclude={"rule_hash"})
        if self.rule_hash != content_id(payload):
            raise ValueError("RMB_MAPPING_RULE_HASH_MISMATCH")
        return self

    def map_cu(self, value_cu: float) -> float:
        if self.mapping_function is RMBMappingFunction.LINEAR_SCALE:
            return float(value_cu) * self.parameters[0].value
        raise ValueError("RMB_MAPPING_FUNCTION_NOT_IMPLEMENTED")


class RMBMappingRegistry(FrozenModel):
    """Versioned constructed-RMB mappings over intermediate CU values."""

    constructed_unit_id: str = "RMB"
    input_unit_id: str = "CU"
    registry_id: str = Field(min_length=1)
    registry_version: str = Field(default="UNFROZEN", min_length=1)
    registry_hash: str = ""
    status: RMBMappingStatus = RMBMappingStatus.NOT_FROZEN
    freeze_id: str | None = None
    reference_period: str | None = None
    component_mappings: dict[str, RMBMappingRule] = {}
    provenance: tuple[str, ...] = ()
    monetary_ground_truth_claim: bool = False
    scenario_dependent: bool = True
    final_test_access_count: int = 0
    paper_full_run: bool = False

    @model_validator(mode="after")
    def strict_mapping(self):
        if self.constructed_unit_id != "RMB" or self.input_unit_id != "CU":
            raise ValueError("RMB_MAPPING_UNIT_ID_INVALID")
        if self.monetary_ground_truth_claim:
            raise ValueError("RMB_MONETARY_GROUND_TRUTH_CLAIM_FORBIDDEN")
        if self.final_test_access_count != 0 or self.paper_full_run:
            raise ValueError("RMB_MAPPING_SAFETY_VIOLATION")
        executable = self.status in {
            RMBMappingStatus.FROZEN,
            RMBMappingStatus.TEST_ONLY,
        }
        if executable and (
            not self.component_mappings
            or not self.freeze_id
            or not self.reference_period
            or not self.provenance
        ):
            raise ValueError("RMB_EXECUTABLE_MAPPING_REQUIRES_LINEAGE")
        if not executable and self.component_mappings:
            raise ValueError("RMB_UNFROZEN_MAPPING_MUST_HAVE_NO_RULES")
        if set(self.component_mappings) - set(CONSEQUENCE_COMPONENTS):
            raise ValueError("RMB_MAPPING_UNKNOWN_COMPONENT")
        for component, rule in self.component_mappings.items():
            if (
                component != rule.component_id
                or rule.constructed_unit_id != "RMB"
                or rule.input_unit_id != "CU"
            ):
                raise ValueError("RMB_MAPPING_RULE_COMPONENT_MISMATCH")
        if self.registry_hash and self.registry_hash != self.digest():
            raise ValueError("RMB_MAPPING_REGISTRY_HASH_MISMATCH")
        return self

    @property
    def executable(self) -> bool:
        return self.status in {RMBMappingStatus.FROZEN, RMBMappingStatus.TEST_ONLY}

    @property
    def authoritative(self) -> bool:
        return self.status is RMBMappingStatus.FROZEN

    def registry_payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload.pop("registry_hash", None)
        return payload

    def digest(self) -> str:
        return content_id(self.registry_payload())

    def to_component_rmb(
        self, cu_by_component: Mapping[str, float]
    ) -> dict[str, float] | None:
        if not self.executable:
            return None
        if set(cu_by_component) - set(CONSEQUENCE_COMPONENTS):
            raise ValueError("RMB_MAPPING_INPUT_UNKNOWN_COMPONENT")
        values: dict[str, float] = {}
        for component, value_cu in cu_by_component.items():
            rule = self.component_mappings.get(component)
            if rule is None:
                raise ValueError(f"RMB_MAPPING_COMPONENT_MISSING:{component}")
            values[component] = rule.map_cu(float(value_cu))
        return values

    def to_rmb(self, cu_by_component: Mapping[str, float]) -> float | None:
        mapped = self.to_component_rmb(cu_by_component)
        return None if mapped is None else sum(mapped.values())

    @classmethod
    def not_frozen(
        cls, *, registry_id: str = "RMB_NOT_FROZEN_V1"
    ) -> "RMBMappingRegistry":
        return cls(registry_id=registry_id)


__all__ = [
    "RMBMappingFunction",
    "RMBMappingParameter",
    "RMBMappingRegistry",
    "RMBMappingRule",
    "RMBMappingStatus",
    "RMBSourceType",
]
