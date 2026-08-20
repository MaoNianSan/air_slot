"""Preparation-only freeze contract for an Exp2 scientific action set.

This module validates a caller-declared comparison set.  It never selects an
action, upgrades response evidence, or removes unsupported actions to make a
manifest pass.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.common.identity import content_id


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ActionSupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    ABSTAIN = "ABSTAIN"


class ActionFreezeStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class ActionSupportRecord(BaseModel):
    """Support declared by a future typed M3 response artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str = Field(min_length=1)
    support_status: ActionSupportStatus
    provenance: tuple[str, ...] = ()


class ScientificActionManifest(BaseModel):
    """An exact action set; no implicit action-membership policy exists."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "AIR_SLOT_EXP2_SCIENTIFIC_ACTION_MANIFEST_V1"
    action_ids: tuple[str, ...] = Field(min_length=1)
    action_registry_hash: str = Field(pattern=SHA256_PATTERN)
    response_bundle_hash: str = Field(pattern=SHA256_PATTERN)
    support_records: tuple[ActionSupportRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def exact_support_record_coverage(self):
        record_ids = tuple(item.action_id for item in self.support_records)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("EXP2_ACTION_SUPPORT_RECORD_DUPLICATE")
        if set(record_ids) != set(self.action_ids):
            raise ValueError("EXP2_ACTION_SUPPORT_RECORD_COVERAGE_MISMATCH")
        return self

    @property
    def manifest_hash(self) -> str:
        return content_id(self.model_dump(mode="json"))


class ActionFreezeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ActionFreezeStatus
    reason_codes: tuple[str, ...]
    manifest_hash: str = Field(pattern=SHA256_PATTERN)


class ActionManifestPreparer:
    """Fail-closed validator for a supplied scientific action manifest."""

    def prepare(self, manifest: ScientificActionManifest) -> ActionFreezeResult:
        if not isinstance(manifest, ScientificActionManifest):
            raise TypeError("EXP2_SCIENTIFIC_ACTION_MANIFEST_REQUIRED")

        reasons: list[str] = []
        action_ids = manifest.action_ids
        if "A00" not in action_ids:
            reasons.append("A00_REQUIRED")
        elif action_ids[0] != "A00":
            reasons.append("A00_MUST_BE_FIRST")
        if len(action_ids) < 2 or not any(item != "A00" for item in action_ids):
            reasons.append("NON_A00_REQUIRED")
        if len(action_ids) != len(set(action_ids)):
            reasons.append("ACTION_ID_DUPLICATE")
        elif "A00" in action_ids and action_ids[1:] != tuple(sorted(action_ids[1:])):
            reasons.append("ACTION_ORDER_NOT_DETERMINISTIC")

        records = {item.action_id: item for item in manifest.support_records}
        unsupported = tuple(
            action_id
            for action_id in action_ids
            if records[action_id].support_status is not ActionSupportStatus.SUPPORTED
        )
        if unsupported:
            reasons.extend(
                f"ACTION_NOT_SUPPORTED:{action_id}" for action_id in unsupported
            )
        non_a00_supported = tuple(
            action_id
            for action_id in action_ids
            if action_id != "A00"
            and records[action_id].support_status is ActionSupportStatus.SUPPORTED
        )
        if not non_a00_supported:
            reasons.append("NO_SUPPORTED_NON_A00_ACTION")

        return ActionFreezeResult(
            status=(
                ActionFreezeStatus.READY if not reasons else ActionFreezeStatus.BLOCKED
            ),
            reason_codes=tuple(reasons) or ("ACTION_SET_FROZEN",),
            manifest_hash=manifest.manifest_hash,
        )


__all__ = [
    "ActionFreezeResult",
    "ActionFreezeStatus",
    "ActionManifestPreparer",
    "ActionSupportRecord",
    "ActionSupportStatus",
    "ScientificActionManifest",
]
