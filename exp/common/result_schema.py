"""Versioned, provenance-complete result contracts for future experiments."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


class MetricLevel(str, Enum):
    STATE = "STATE"
    DECISION = "DECISION"
    SYSTEM = "SYSTEM"


class SupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    ABSTAINED = "ABSTAINED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_RUN = "NOT_RUN"
    ASSUMPTION_GROUNDED = "ASSUMPTION_GROUNDED"


class MetricObservation(BaseModel):
    """One scalar metric value with its scientific support label."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    metric_id: str = Field(min_length=1)
    level: MetricLevel
    value: float | int | bool | str | None
    unit: str = Field(min_length=1)
    support_status: SupportStatus
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value")
    @classmethod
    def finite_numeric_value(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("EXPERIMENT_METRIC_VALUE_NONFINITE")
        return value


class ExperimentResult(BaseModel):
    """Common result envelope shared by Exp1-Exp4.

    This type records results only. It does not execute a model, implement a
    variant, decide support, or promote a result to a paper claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: str = "AIR_SLOT_EXPERIMENT_RESULT_V1"
    experiment_id: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    split: str = "DEVELOPMENT"
    tier: str = "FAST"
    episode_count: int = Field(default=0, ge=0)
    node_count: int = Field(default=0, ge=0)
    seed: int
    timestamp: datetime
    model_versions: dict[str, str] = Field(min_length=1)
    model_hashes: dict[str, str] = Field(default_factory=dict)
    registry_hashes: dict[str, str] = Field(default_factory=dict)
    artifact_versions: dict[str, str] = Field(min_length=1)
    scenario_hash: str = Field(pattern=SHA256_PATTERN)
    config_hash: str = Field(pattern=SHA256_PATTERN)
    metrics: dict[str, MetricObservation] = Field(default_factory=dict)
    support_status: SupportStatus
    lineage: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    final_test_access_count: int = Field(
        default=0, ge=0, alias="FINAL_TEST_ACCESS_COUNT",
    )
    provenance: dict[str, Any] = Field(min_length=1)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("EXPERIMENT_RESULT_TIMESTAMP_TIMEZONE_REQUIRED")
        return value.astimezone(timezone.utc)

    @field_validator("model_versions", "artifact_versions")
    @classmethod
    def version_map_is_explicit(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not str(key).strip() or not str(version).strip()
               for key, version in value.items()):
            raise ValueError("EXPERIMENT_RESULT_VERSION_MAP_EMPTY_ENTRY")
        return value

    @model_validator(mode="after")
    def metric_keys_match_observations(self):
        mismatches = [
            key for key, observation in self.metrics.items()
            if key != observation.metric_id
        ]
        if mismatches:
            raise ValueError("EXPERIMENT_RESULT_METRIC_KEY_MISMATCH")
        if self.final_test_access_count != 0:
            raise ValueError("EXPERIMENT_RESULT_FINAL_TEST_ACCESS_MUST_BE_ZERO")
        return self

    @property
    def result_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return f"sha256:{sha256(encoded).hexdigest()}"


__all__ = [
    "ExperimentResult",
    "MetricLevel",
    "MetricObservation",
    "SupportStatus",
]
