"""Typed, conditional M3 scenario-response bundle materialization for Exp2."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.M3.registry import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry
from model.common.identity import content_id


M3_BUNDLE_SCHEMA_VERSION = "AIR_SLOT_EXP2_M3_SCENARIO_BUNDLE_V1"
M3_BUNDLE_FILENAME = "DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json"
M3_RESPONSE_FREEZE_ID = "M3_RESPONSE_SCENARIO_V1_FREEZE"


class ScenarioResponseRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str = Field(min_length=1)
    response_rule_id: str = Field(min_length=1)
    rule_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    parameters: dict[str, object]
    source_type: Literal["BASELINE_IDENTITY", "PURE_SCENARIO"]
    support_state: Literal["BASELINE_IDENTITY", "SCENARIO_ASSUMPTION"]
    formal_support_upgrade: bool = False
    parameter_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_conditional_support(self) -> "ScenarioResponseRule":
        if self.formal_support_upgrade:
            raise ValueError("EXP2_M3_FORMAL_SUPPORT_UPGRADE_FORBIDDEN")
        if self.action_id == "A00":
            if self.source_type != "BASELINE_IDENTITY" or self.support_state != "BASELINE_IDENTITY":
                raise ValueError("EXP2_M3_A00_BASELINE_IDENTITY_REQUIRED")
        elif self.source_type != "PURE_SCENARIO" or self.support_state != "SCENARIO_ASSUMPTION":
            raise ValueError("EXP2_M3_NON_A00_SCENARIO_ASSUMPTION_REQUIRED")
        payload = self.model_dump(mode="json", exclude={"rule_hash"})
        if self.rule_hash != content_id(payload):
            raise ValueError("EXP2_M3_SCENARIO_RULE_HASH_MISMATCH")
        return self

    @classmethod
    def create(cls, **values) -> "ScenarioResponseRule":
        provisional = cls.model_construct(rule_hash="sha256:" + "0" * 64, **values)
        payload = provisional.model_dump(mode="json", exclude={"rule_hash"})
        return cls(**payload, rule_hash=content_id(payload))


class M3ScenarioBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = M3_BUNDLE_SCHEMA_VERSION
    bundle_id: str = "DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE_V1"
    action_registry_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_registry_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sensitivity_level: Literal["BASE"] = "BASE"
    rules: tuple[ScenarioResponseRule, ...] = Field(min_length=2)
    FINAL_TEST_ACCESS_COUNT: int = 0
    PAPER_FULL_RUN: bool = False
    bundle_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_bundle(self) -> "M3ScenarioBundle":
        action_ids = tuple(item.action_id for item in self.rules)
        if action_ids[0] != "A00" or len(action_ids) != len(set(action_ids)):
            raise ValueError("EXP2_M3_BUNDLE_ACTION_IDENTITY_INVALID")
        if self.FINAL_TEST_ACCESS_COUNT != 0 or self.PAPER_FULL_RUN:
            raise ValueError("EXP2_M3_BUNDLE_FINAL_TEST_OR_PAPER_VIOLATION")
        payload = self.model_dump(mode="json", exclude={"bundle_hash"})
        if self.bundle_hash != content_id(payload):
            raise ValueError("EXP2_M3_SCENARIO_BUNDLE_HASH_MISMATCH")
        return self

    @classmethod
    def create(cls, **values) -> "M3ScenarioBundle":
        provisional = cls.model_construct(bundle_hash="sha256:" + "0" * 64, **values)
        payload = provisional.model_dump(mode="json", exclude={"bundle_hash"})
        return cls(**payload, bundle_hash=content_id(payload))


def _write_json(path: Path, payload: dict) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) == payload:
            return
        raise RuntimeError("EXP2_M3_SCENARIO_BUNDLE_EXISTS_WITH_DIFFERENT_CONTENT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def materialize_m3_scenario_bundle(*, root: Path, output_path: Path | None = None) -> M3ScenarioBundle:
    action_registry = ActionRegistry.load(root / "registries" / "action_templates.yaml")
    response_registry = ResponseScenarioRegistry.load(
        root / "registries" / "m3_response_scenarios.yaml",
        structural_registry=action_registry,
    )
    action_ids = ("A00", *sorted(action_id for action_id in response_registry.actions if action_id != "A00"))
    rules = []
    for action_id in action_ids:
        action = response_registry.actions[action_id]
        if action_id != "A00" and action.response_parameter_status != "FROZEN":
            continue
        parameters = response_registry.parameters(action_id, sensitivity="BASE")
        values = {
            "action_id": action_id,
            "response_rule_id": f"{response_registry.registry_id}:{action_id}:BASE",
            "parameters": parameters,
            "source_type": "BASELINE_IDENTITY" if action_id == "A00" else "PURE_SCENARIO",
            "support_state": "BASELINE_IDENTITY" if action_id == "A00" else "SCENARIO_ASSUMPTION",
            "formal_support_upgrade": False,
            "parameter_version": response_registry.schema_version,
            "freeze_id": M3_RESPONSE_FREEZE_ID,
            "provenance": (
                response_registry.registry_id,
                response_registry.registry_hash,
                action.response_provenance,
            ),
        }
        rules.append(ScenarioResponseRule.create(**values))
    bundle = M3ScenarioBundle.create(
        action_registry_hash=action_registry.registry_hash,
        response_registry_hash=response_registry.registry_hash,
        rules=tuple(rules),
    )
    target = output_path or root / "artifacts" / "experiment" / "exp2" / M3_BUNDLE_FILENAME
    _write_json(target, bundle.model_dump(mode="json"))
    return bundle


__all__ = [
    "M3_BUNDLE_FILENAME",
    "M3_BUNDLE_SCHEMA_VERSION",
    "M3ScenarioBundle",
    "ScenarioResponseRule",
    "materialize_m3_scenario_bundle",
]
