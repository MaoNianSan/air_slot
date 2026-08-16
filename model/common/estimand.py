from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json

from pydantic import Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.value_objects import FrozenModel


class ScientificStrEnum(str, Enum):
    pass


class DecisionDomain(ScientificStrEnum):
    LOCAL_EPISODE = "LOCAL_EPISODE"


class ComponentScopeRole(ScientificStrEnum):
    INCLUDED = "INCLUDED"
    OUTSIDE_ESTIMAND = "OUTSIDE_ESTIMAND"


class ScopeStatus(ScientificStrEnum):
    FORMAL_READY = "FORMAL_READY"
    FORMAL_AGGREGATE_UNRESOLVED = "FORMAL_AGGREGATE_UNRESOLVED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


class FormalEstimandStatus(ScientificStrEnum):
    FORMAL_AVAILABLE = "FORMAL_AVAILABLE"
    FORMAL_AGGREGATE_UNRESOLVED = "FORMAL_AGGREGATE_UNRESOLVED"
    VALUATION_NOT_FROZEN = "VALUATION_NOT_FROZEN"
    BASELINE_COMPARATOR_INVALID = "BASELINE_COMPARATOR_INVALID"


class ComponentRoleEntry(FrozenModel):
    component_id: str
    role: ComponentScopeRole

    @model_validator(mode="after")
    def known_component(self):
        if self.component_id not in CONSEQUENCE_COMPONENTS:
            raise ValueError("UNKNOWN_CONSEQUENCE_COMPONENT")
        return self


def _scope_payload(
    *,
    estimand_id: str,
    estimand_version: str,
    decision_domain: DecisionDomain,
    included_components: tuple[str, ...],
    component_role: tuple[ComponentRoleEntry, ...],
    aggregation_rule_id: str,
    valuation_registry_id: str,
    material_coverage_contract_id: str,
    scope_status: ScopeStatus,
) -> dict:
    return {
        "aggregation_rule_id": aggregation_rule_id,
        "component_role": [
            {"component_id": item.component_id, "role": item.role.value}
            for item in component_role
        ],
        "decision_domain": decision_domain.value,
        "estimand_id": estimand_id,
        "estimand_version": estimand_version,
        "included_components": list(included_components),
        "material_coverage_contract_id": material_coverage_contract_id,
        "scope_status": scope_status.value,
        "valuation_registry_id": valuation_registry_id,
    }


def consequence_scope_hash(**kwargs) -> str:
    encoded = json.dumps(
        _scope_payload(**kwargs), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


class ConsequenceScope(FrozenModel):
    estimand_id: str = Field(min_length=1)
    estimand_version: str = Field(min_length=1)
    decision_domain: DecisionDomain
    included_components: tuple[str, ...]
    component_role: tuple[ComponentRoleEntry, ...]
    aggregation_rule_id: str = Field(min_length=1)
    valuation_registry_id: str = Field(min_length=1)
    material_coverage_contract_id: str = Field(min_length=1)
    scope_status: ScopeStatus
    scope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(
        cls,
        *,
        estimand_id: str,
        estimand_version: str,
        included_components: tuple[str, ...],
        aggregation_rule_id: str,
        valuation_registry_id: str,
        material_coverage_contract_id: str,
        scope_status: ScopeStatus = ScopeStatus.FORMAL_AGGREGATE_UNRESOLVED,
        decision_domain: DecisionDomain = DecisionDomain.LOCAL_EPISODE,
    ) -> "ConsequenceScope":
        included = tuple(included_components)
        roles = tuple(
            ComponentRoleEntry(
                component_id=component,
                role=(
                    ComponentScopeRole.INCLUDED
                    if component in included
                    else ComponentScopeRole.OUTSIDE_ESTIMAND
                ),
            )
            for component in CONSEQUENCE_COMPONENTS
        )
        values = {
            "estimand_id": estimand_id,
            "estimand_version": estimand_version,
            "decision_domain": decision_domain,
            "included_components": included,
            "component_role": roles,
            "aggregation_rule_id": aggregation_rule_id,
            "valuation_registry_id": valuation_registry_id,
            "material_coverage_contract_id": material_coverage_contract_id,
            "scope_status": scope_status,
        }
        return cls(**values, scope_hash=consequence_scope_hash(**values))

    @model_validator(mode="after")
    def validate_scope(self):
        if self.decision_domain is not DecisionDomain.LOCAL_EPISODE:
            raise ValueError("AIRLINE_NETWORK_SCOPE_PROHIBITED")
        if tuple(item.component_id for item in self.component_role) != tuple(
            CONSEQUENCE_COMPONENTS
        ):
            raise ValueError("SCOPE_REQUIRES_EXACT_SEVEN_COMPONENT_ROLES")
        expected_included = tuple(
            item.component_id
            for item in self.component_role
            if item.role is ComponentScopeRole.INCLUDED
        )
        if self.included_components != expected_included:
            raise ValueError("SCOPE_INCLUDED_COMPONENT_ROLE_MISMATCH")
        if not self.included_components:
            raise ValueError("EMPTY_FORMAL_CONSEQUENCE_SCOPE")
        values = {
            "estimand_id": self.estimand_id,
            "estimand_version": self.estimand_version,
            "decision_domain": self.decision_domain,
            "included_components": self.included_components,
            "component_role": self.component_role,
            "aggregation_rule_id": self.aggregation_rule_id,
            "valuation_registry_id": self.valuation_registry_id,
            "material_coverage_contract_id": self.material_coverage_contract_id,
            "scope_status": self.scope_status,
        }
        if self.scope_hash != consequence_scope_hash(**values):
            raise ValueError("CONSEQUENCE_SCOPE_HASH_MISMATCH")
        return self

    def compatible_with(self, other: "ConsequenceScope") -> bool:
        return (
            self.estimand_id,
            self.estimand_version,
            self.scope_hash,
            self.valuation_registry_id,
        ) == (
            other.estimand_id,
            other.estimand_version,
            other.scope_hash,
            other.valuation_registry_id,
        )
