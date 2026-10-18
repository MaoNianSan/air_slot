"""M3 numerical response-scenario registry (M3_RESPONSE_SCENARIO_V1).

HUMAN-APPROVED via M3_RESPONSE_SCENARIO_V1_FREEZE.  The numerical response
contract is intentionally separate from the structural action registry;
FROZEN scenario parameters never upgrade an action to FORMAL support.
"""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import Field, model_validator

from model.M3.registry_layer.actions import ActionRegistry, PRINCIPAL_IDS
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.errors import RegistryError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel

REGISTRY_ID = "M3_RESPONSE_SCENARIO_V1"
SCHEMA_VERSION = "M3_RESPONSE_SCENARIO_V1"
# Backwards-compatible alias: the principal-23 set now lives in model.M3.registry_layer.actions.
PRINCIPAL_IDS = PRINCIPAL_IDS
SENSITIVITY_LEVELS = ("LOW", "BASE", "HIGH")
PARAMETER_BASIS = "TRANSPARENT_TIERED_SCENARIO_V1"


class ResponseSensitivity(str, Enum):
    LOW = "LOW"
    BASE = "BASE"
    HIGH = "HIGH"


class AssumptionGroundedBlock(FrozenModel):
    """Path-B literature-parameterized mechanism response provenance (G2).

    ``ASSUMPTION_GROUNDED`` marks a non-A00 response whose BASE parameters are
    scenario values justified by a mechanism formula and literature; it never
    upgrades the response to an empirical effect or FORMAL authority.
    """

    mechanism: str
    formula: str
    literature: tuple[str, ...]
    sensitivity_band: dict[str, dict[str, float]]


class ResponseScenarioAction(FrozenModel):
    template_id: str
    tier: str = ""
    response_parameter_status: str = "FROZEN"
    response_provenance: str = "PURE_SCENARIO"
    response_model: str = "BERNOULLI_BETA"
    value: float | None = None
    assumption_grounded: AssumptionGroundedBlock | None = None

    @model_validator(mode="after")
    def frozen_contract(self):
        if self.template_id == "A00":
            if self.response_parameter_status != "NOT_REQUIRED":
                raise RegistryError("M3_RESPONSE_A00_NOT_REQUIRED_VIOLATION")
            if self.response_model != "DETERMINISTIC":
                raise RegistryError("M3_RESPONSE_A00_DETERMINISTIC_REQUIRED")
            if self.value != 0.0:
                raise RegistryError("M3_RESPONSE_A00_IDENTITY_VALUE_REQUIRED")
        elif self.response_parameter_status not in {"FROZEN", "NOT_FROZEN"}:
            raise RegistryError("M3_RESPONSE_NON_A00_MUST_BE_FROZEN_OR_NOT_FROZEN")
        if (
            self.template_id != "A00"
            and self.response_parameter_status == "FROZEN"
            and self.assumption_grounded is None
        ):
            raise RegistryError("M3_RESPONSE_NON_A00_ASSUMPTION_BLOCK_REQUIRED")
        if self.response_provenance not in {
            "PURE_SCENARIO",
            "OPERATOR_INDUSTRY",
            "STRUCTURAL_BOUNDED_SCENARIO",
            "ASSUMPTION_GROUNDED",
        }:
            raise RegistryError("M3_RESPONSE_INVALID_PROVENANCE")
        if self.response_model not in {"BERNOULLI_BETA", "DETERMINISTIC"}:
            raise RegistryError("M3_RESPONSE_INVALID_RESPONSE_MODEL")
        return self


class ResponseScenarioRegistry(FrozenModel):
    schema_version: str = SCHEMA_VERSION
    registry_id: str = REGISTRY_ID
    scientific_status: str = "HUMAN_APPROVED_SCENARIO_SPECIFICATION"
    formal_support_upgrade: bool = False
    response_model: str = "BERNOULLI_BETA"
    response_provenance_default: str = "PURE_SCENARIO"
    beta_concentration: float = 12.0
    induced_score_to_cu: float = 0.10
    induced_score_unit: str = "INDUCED_SCORE"
    induced_score_to_cu_unit: str = "CU_PER_INDUCED_SCORE"
    induced_burden_semantics: str = "ACTION_ATTEMPT_BURDEN"
    induced_burden_requires_realized_mitigation: bool = False
    induced_burden_components: tuple[str, ...] = CONSEQUENCE_COMPONENTS
    sensitivity: dict[str, dict[str, float]] = Field(default_factory=dict)
    principal_sensitivity_axis: str = "RESPONSE_EFFICACY"
    secondary_burden_sensitivity: dict[str, Any] = Field(default_factory=dict)
    tiers: dict[str, dict[str, float]] = Field(default_factory=dict)
    actions: dict[str, ResponseScenarioAction] = Field(default_factory=dict)
    source_path: str = ""
    source_sha256: str = ""
    registry_hash: str = ""

    @classmethod
    def load(cls, path: Path, *, structural_registry: ActionRegistry | None = None):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        payload = dict(raw)
        sensitivity = dict(payload.get("sensitivity") or {})
        payload["principal_sensitivity_axis"] = sensitivity.pop(
            "principal_axis", "RESPONSE_EFFICACY"
        )
        payload["sensitivity"] = sensitivity
        payload["actions"] = {
            action_id: {"template_id": action_id, **(item or {})}
            for action_id, item in (payload.get("actions") or {}).items()
        }
        registry = cls.model_validate(payload)
        registry = registry.model_copy(
            update={
                "source_path": str(path),
                "source_sha256": f"sha256:{sha256(path.read_bytes()).hexdigest()}",
            }
        )
        if structural_registry is not None:
            registry.validate_against_structural(structural_registry)
        registry = registry.model_copy(update={"registry_hash": registry.digest()})
        return registry

    @model_validator(mode="after")
    def strict_registry_contract(self):
        if self.registry_id != REGISTRY_ID or self.schema_version != SCHEMA_VERSION:
            raise RegistryError("M3_RESPONSE_REGISTRY_IDENTITY_MISMATCH")
        ids = tuple(self.actions)
        if len(ids) != len(set(ids)):
            raise RegistryError("M3_RESPONSE_DUPLICATE_ACTION_ID")
        if ids != PRINCIPAL_IDS:
            raise RegistryError("M3_RESPONSE_PRINCIPAL_ACTION_EXACT_SET_MISMATCH")
        unknown = set(self.tiers) - {f"T{i}" for i in range(1, 7)}
        if unknown:
            raise RegistryError("M3_RESPONSE_UNKNOWN_TIER")
        if self.formal_support_upgrade:
            raise RegistryError("M3_RESPONSE_FORMAL_UPGRADE_FORBIDDEN")
        if self.beta_concentration <= 0:
            raise RegistryError("M3_RESPONSE_INVALID_CONCENTRATION")
        if not (0 < self.induced_score_to_cu):
            raise RegistryError("M3_RESPONSE_INVALID_INDUCED_CONVERSION")
        if self.induced_score_unit != "INDUCED_SCORE":
            raise RegistryError("M3_RESPONSE_INDUCED_SCORE_UNIT_MISMATCH")
        if self.induced_score_to_cu_unit != "CU_PER_INDUCED_SCORE":
            raise RegistryError("M3_RESPONSE_INDUCED_CONVERSION_UNIT_MISMATCH")
        if self.induced_burden_semantics != "ACTION_ATTEMPT_BURDEN":
            raise RegistryError("M3_RESPONSE_INDUCED_BURDEN_SEMANTICS_MISMATCH")
        if self.induced_burden_requires_realized_mitigation:
            raise RegistryError("M3_RESPONSE_INDUCED_BURDEN_MUST_BE_ATTEMPT_BASED")
        if tuple(self.induced_burden_components) != tuple(CONSEQUENCE_COMPONENTS):
            raise RegistryError("M3_RESPONSE_INDUCED_COMPONENT_SCOPE_MISMATCH")
        for name, item in self.actions.items():
            if name == "A00":
                continue
            if item.response_parameter_status == "NOT_FROZEN":
                # Library entry only: no numerical response contract declared yet,
                # so no tier materialization and no comparison-set eligibility.
                continue
            tier = self.tiers.get(item.tier)
            if tier is None:
                raise RegistryError("M3_RESPONSE_UNKNOWN_TIER")
            probability = float(tier["success_probability"])
            mean = float(tier["beta_mean"])
            if not 0 < probability <= 1:
                raise RegistryError("M3_RESPONSE_INVALID_PROBABILITY")
            if not 0 < mean < 1:
                raise RegistryError("M3_RESPONSE_INVALID_BETA_MEAN")
        for level in SENSITIVITY_LEVELS:
            entry = self.sensitivity.get(level.lower())
            if entry is None or set(entry) != {
                "success_probability_delta",
                "response_mean_delta",
            }:
                raise RegistryError("M3_RESPONSE_SENSITIVITY_SPEC_INVALID")
        for name, item in self.actions.items():
            if name == "A00" or item.assumption_grounded is None:
                continue
            if item.assumption_grounded.sensitivity_band != self.sensitivity:
                raise RegistryError("M3_RESPONSE_ASSUMPTION_BAND_MISMATCH")
        return self

    def validate_against_structural(self, structural: ActionRegistry) -> None:
        if tuple(structural.templates) is None:
            raise RegistryError("M3_RESPONSE_STRUCTURAL_REGISTRY_HASH_MISMATCH")
        structural_ids = tuple(item.template_id for item in structural.templates)
        if not set(PRINCIPAL_IDS) <= set(structural_ids):
            raise RegistryError("M3_RESPONSE_STRUCTURAL_PRINCIPAL_SUBSET_MISMATCH")

    def parameters(
        self, template_id: str, *, sensitivity: str = "BASE"
    ) -> dict[str, Any]:
        """Materialized response parameters for one action at one sensitivity."""
        if template_id not in self.actions:
            raise RegistryError(f"M3_RESPONSE_UNKNOWN_ACTION:{template_id}")
        action = self.actions[template_id]
        if template_id == "A00":
            return {
                "response_model": "DETERMINISTIC",
                "response_parameter_status": "NOT_REQUIRED",
                "response_provenance": action.response_provenance,
                "value": float(action.value or 0.0),
            }
        if action.response_parameter_status == "NOT_FROZEN":
            # Library entry only: no frozen response contract, so no materialized
            # numerical parameters and no comparison-set eligibility.
            return {
                "response_model": action.response_model,
                "response_parameter_status": "NOT_FROZEN",
                "response_provenance": action.response_provenance,
            }
        if sensitivity not in SENSITIVITY_LEVELS:
            raise RegistryError("M3_RESPONSE_SENSITIVITY_UNKNOWN")
        tier = self.tiers[action.tier]
        delta = self.sensitivity[sensitivity.lower()]
        probability = float(tier["success_probability"]) + float(
            delta["success_probability_delta"]
        )
        mean = float(tier["beta_mean"]) + float(delta["response_mean_delta"])
        if sensitivity == "LOW":
            probability = max(0.05, probability)
            mean = max(0.20, mean)
        else:
            probability = min(0.95, probability)
            mean = min(0.95, mean)
        if not 0.05 <= probability <= 0.95 or not 0.20 <= mean <= 0.95:
            raise RegistryError("M3_RESPONSE_SENSITIVITY_BOUNDS_VIOLATION")
        concentration = float(self.beta_concentration)
        return {
            "response_model": "BERNOULLI_BETA",
            "response_parameter_status": "FROZEN",
            "response_provenance": action.response_provenance,
            "tier": action.tier,
            "success_probability": probability,
            "mean_intensity": mean,
            "beta_mean": mean,
            "concentration": concentration,
            "alpha": mean * concentration,
            "beta": (1.0 - mean) * concentration,
            "parameter_basis": PARAMETER_BASIS,
            "sensitivity_level": sensitivity,
            # gamma single source of truth (Round 2, spec 9.2): frozen registry
            # value; sensitivity never perturbs the principal frozen parameter.
            "induced_score_to_cu": float(self.induced_score_to_cu),
            "assumption_grounded": (
                action.assumption_grounded.model_dump(mode="json")
                if action.assumption_grounded is not None
                else None
            ),
        }

    def tier_for(self, template_id: str) -> str:
        return self.actions[template_id].tier

    def registry_payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload.pop("registry_hash", None)
        payload.pop("source_path", None)
        payload.pop("source_sha256", None)
        return payload

    def digest(self) -> str:
        return content_id(self.registry_payload())

    def write_manifest(self, output_path: Path, *, overwrite: bool = False) -> Path:
        if output_path.exists() and not overwrite:
            raise RegistryError("M3_RESPONSE_MANIFEST_EXISTS")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifest_version": "1.0.0",
            "registry_id": self.registry_id,
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "registry_hash": self.digest(),
            "action_ids": list(self.actions),
            "action_tiers": {name: item.tier for name, item in self.actions.items()},
            "beta_concentration": self.beta_concentration,
            "induced_score_to_cu": self.induced_score_to_cu,
            "induced_score_unit": self.induced_score_unit,
            "induced_score_to_cu_unit": self.induced_score_to_cu_unit,
            "induced_burden_semantics": self.induced_burden_semantics,
            "induced_burden_requires_realized_mitigation": self.induced_burden_requires_realized_mitigation,
            "induced_burden_components": list(self.induced_burden_components),
            "principal_sensitivity_axis": self.principal_sensitivity_axis,
            "low_base_high_rules": {
                level: self.sensitivity.get(level.lower())
                for level in SENSITIVITY_LEVELS
            },
            "secondary_burden_sensitivity": self.secondary_burden_sensitivity,
            "response_provenance": self.response_provenance_default,
            "formal_support_upgrade": False,
            "final_test_access_count": 0,
            "paper_full_run": False,
        }
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=str(output_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, output_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return output_path


def load_response_registry(
    path: Path, *, structural_path: Path
) -> ResponseScenarioRegistry:
    structural = ActionRegistry.load(structural_path)
    return ResponseScenarioRegistry.load(path, structural_registry=structural)


__all__ = [
    "PARAMETER_BASIS",
    "PRINCIPAL_IDS",
    "REGISTRY_ID",
    "ResponseScenarioAction",
    "ResponseScenarioRegistry",
    "ResponseSensitivity",
    "SENSITIVITY_LEVELS",
    "load_response_registry",
]
