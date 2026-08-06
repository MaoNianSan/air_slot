from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from ..contracts import FlightChainStage
from .availability import IDENTITY_COLUMNS


FEATURE_SCHEMA_VERSION = "M1_FEATURE_SCHEMA_V1"


def _allowed(
    registry: tuple[dict[str, Any], ...],
    table: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(row.get("standard_column") or row.get("column"))
                for row in registry
                if str(row.get("table")) == table
                and bool(row.get("model_input_allowed"))
                and str(row.get("standard_column") or row.get("column"))
                not in IDENTITY_COLUMNS
            }
        )
    )


def _hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class M1FeatureSchema:
    schema_version: str
    value_features: tuple[str, ...]
    mask_features: tuple[str, ...]
    age_features: tuple[str, ...]
    stale_features: tuple[str, ...]
    fallback_features: tuple[str, ...]
    stage_features: tuple[str, ...]
    static_features: tuple[str, ...]
    final_feature_order: tuple[str, ...]
    schema_hash: str

    @classmethod
    def from_column_registry(
        cls,
        registry: tuple[dict[str, Any], ...],
        *,
        schema_version: str = FEATURE_SCHEMA_VERSION,
    ) -> "M1FeatureSchema":
        values = _allowed(registry, "observations")
        static = _allowed(registry, "episodes")
        mask = tuple(f"mask__{name}" for name in values + static)
        age = tuple(f"age_minutes__{name}" for name in values)
        stale = tuple(f"stale__{name}" for name in values)
        fallback = tuple(f"fallback__{name}" for name in values)
        stages = tuple(f"stage__{stage.value}" for stage in FlightChainStage)
        final = values + static + mask + age + stale + fallback + stages + (
            "delta_t_minutes",
        )
        payload = {
            "schema_version": schema_version,
            "value_features": values,
            "mask_features": mask,
            "age_features": age,
            "stale_features": stale,
            "fallback_features": fallback,
            "stage_features": stages,
            "static_features": static,
            "final_feature_order": final,
        }
        return cls(schema_hash=_hash(payload), **payload)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "value_features": list(self.value_features),
            "mask_features": list(self.mask_features),
            "age_features": list(self.age_features),
            "stale_features": list(self.stale_features),
            "fallback_features": list(self.fallback_features),
            "stage_features": list(self.stage_features),
            "static_features": list(self.static_features),
            "final_feature_order": list(self.final_feature_order),
            "schema_hash": self.schema_hash,
        }

    def validate_vector(self, feature_vector: tuple[float, ...]) -> None:
        if len(feature_vector) != len(self.final_feature_order):
            raise ValueError("M1_FEATURE_VECTOR_SCHEMA_MISMATCH")

    def encode(
        self,
        *,
        values: Mapping[str, float],
        masks: Mapping[str, bool],
        ages: Mapping[str, float],
        stale: Mapping[str, bool],
        fallback: Mapping[str, bool],
        stage: FlightChainStage,
        delta_t_minutes: float,
        static: Mapping[str, float],
    ) -> tuple[float, ...]:
        encoded: dict[str, float] = {}
        for name in self.value_features:
            encoded[name] = float(values.get(name, 0.0))
            encoded[f"mask__{name}"] = float(bool(masks.get(name, False)))
            encoded[f"age_minutes__{name}"] = float(ages.get(name, 0.0))
            encoded[f"stale__{name}"] = float(bool(stale.get(name, False)))
            encoded[f"fallback__{name}"] = float(bool(fallback.get(name, False)))
        for name in self.static_features:
            value = float(static.get(name, 0.0))
            present = math.isfinite(value)
            encoded[name] = value if present else 0.0
            encoded[f"mask__{name}"] = float(present)
        for name in self.stage_features:
            encoded[name] = float(name == f"stage__{stage.value}")
        encoded["delta_t_minutes"] = float(delta_t_minutes)
        vector = tuple(encoded.get(name, 0.0) for name in self.final_feature_order)
        self.validate_vector(vector)
        return vector
