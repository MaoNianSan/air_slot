"""Train-only normalization and per-feature masking for M1 static context."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import torch

from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel
from model.PRE import PREState

STATIC_NUMERIC_FEATURE_NAMES: tuple[str, ...] = (
    "turnaround_reference_minutes",
    "taxi_reference_minutes",
)
STATIC_MISSING_MASK_NAMES: tuple[str, ...] = tuple(
    f"{name}.missing_mask" for name in STATIC_NUMERIC_FEATURE_NAMES
)
STATIC_FEATURE_NAMES: tuple[str, ...] = (
    *STATIC_NUMERIC_FEATURE_NAMES,
    *STATIC_MISSING_MASK_NAMES,
)
STATIC_FEATURE_COUNT = len(STATIC_FEATURE_NAMES)

_REFERENCE_FIELDS = (
    ("turnaround_reference", "turnaround_reference_minutes"),
    ("taxi_reference", "taxi_reference_minutes"),
)
_PUBLISHED_STATIC_REFERENCE_FIELDS = (
    "route_context",
    "carrier_context",
    "aircraft_identity",
    "schedule_reference",
    "turnaround_reference",
    "taxi_reference",
)


class StaticNormalizationValue(FrozenModel):
    count: int
    mean: float
    std: float
    min: float
    max: float


class M1StaticNormalizationArtifact(FrozenModel):
    fitted_split: str
    episode_level_fit: bool
    episode_count: int
    episode_ids_hash: str
    values: dict[str, StaticNormalizationValue]

    def normalize(self, name: str, value: float) -> float:
        if self.fitted_split != "train" or not self.episode_level_fit:
            raise ContractError("M1_STATIC_NORMALIZATION_MUST_BE_TRAIN_EPISODE_LEVEL")
        item = self.values.get(name)
        if item is None:
            raise ContractError(f"M1_STATIC_NORMALIZATION_MISSING:{name}")
        if item.std <= 1e-12:
            raise ContractError(f"M1_STATIC_FEATURE_CONSTANT_ON_TRAIN:{name}")
        return (float(value) - item.mean) / item.std


def _published_value(pre_state: PREState, field: str):
    value = pre_state.successor_state.get(field)
    if value is None or value.support_state is SupportState.ABSTAIN:
        return None
    return value.value if isinstance(value.value, dict) else None


def _legal_reference_value(payload) -> float | None:
    if not isinstance(payload, Mapping):
        return None
    if not payload.get("reference_id") or not payload.get("freeze_id"):
        return None
    raw = payload.get("value")
    return None if raw is None else float(raw)


def raw_static_values_from_lineage(
    lineage: Mapping[str, object] | None,
) -> dict[str, float | None]:
    payload = lineage or {}
    return {
        name: _legal_reference_value(payload.get(field))
        for field, name in _REFERENCE_FIELDS
    }


def raw_static_values_from_pre(
    pre_state: PREState,
    static_context=None,
) -> tuple[dict[str, float | None], dict[str, object]]:
    model_feature_fields = (
        set(static_context.model_feature_fields())
        if static_context is not None
        else set()
    )
    raw = {}
    for field, name in _REFERENCE_FIELDS:
        payload = _published_value(pre_state, field)
        raw[name] = (
            _legal_reference_value(payload) if field in model_feature_fields else None
        )
    lineage = {}
    for field in _PUBLISHED_STATIC_REFERENCE_FIELDS:
        payload = _published_value(pre_state, field)
        if payload is not None:
            lineage[field] = payload
    return raw, lineage


def fit_static_normalization(
    rows: Iterable[tuple[str, Mapping[str, object] | None]],
    *,
    split: str,
) -> M1StaticNormalizationArtifact:
    if split != "train":
        raise ContractError("M1_STATIC_NORMALIZATION_MUST_BE_TRAIN_ONLY")
    by_episode: dict[str, dict[str, float | None]] = {}
    for episode_id, payload in rows:
        values = (
            {name: payload.get(name) for name in STATIC_NUMERIC_FEATURE_NAMES}
            if payload is not None
            and all(name in payload for name in STATIC_NUMERIC_FEATURE_NAMES)
            else raw_static_values_from_lineage(payload)
        )
        previous = by_episode.get(episode_id)
        if previous is not None and previous != values:
            raise ContractError(
                f"M1_STATIC_REFERENCE_VARIES_WITHIN_EPISODE:{episode_id}"
            )
        by_episode[episode_id] = values
    if not by_episode:
        raise ContractError("M1_STATIC_NORMALIZATION_EMPTY_TRAIN")
    fitted = {}
    for name in STATIC_NUMERIC_FEATURE_NAMES:
        observed = [
            float(values[name])
            for values in by_episode.values()
            if values[name] is not None
        ]
        if not observed:
            raise ContractError(f"M1_STATIC_NORMALIZATION_NO_OBSERVED_VALUES:{name}")
        mean = sum(observed) / len(observed)
        variance = sum((value - mean) ** 2 for value in observed) / len(observed)
        std = variance**0.5
        if std <= 1e-12:
            raise ContractError(f"M1_STATIC_FEATURE_CONSTANT_ON_TRAIN:{name}")
        fitted[name] = StaticNormalizationValue(
            count=len(observed),
            mean=mean,
            std=std,
            min=min(observed),
            max=max(observed),
        )
    episode_ids = tuple(sorted(by_episode))
    return M1StaticNormalizationArtifact(
        fitted_split="train",
        episode_level_fit=True,
        episode_count=len(episode_ids),
        episode_ids_hash=content_id({"split": "train", "episode_ids": episode_ids}),
        values=fitted,
    )


def encode_static_values(
    raw_values: Mapping[str, float | None],
    normalization: M1StaticNormalizationArtifact,
) -> torch.Tensor:
    numeric = []
    masks = []
    for name in STATIC_NUMERIC_FEATURE_NAMES:
        raw = raw_values.get(name)
        observed = raw is not None
        numeric.append(normalization.normalize(name, float(raw)) if observed else 0.0)
        masks.append(0.0 if observed else 1.0)
    return torch.tensor([numeric + masks], dtype=torch.float32)


def static_reference_features_from_pre(
    pre_state: PREState,
    static_context,
    normalization: M1StaticNormalizationArtifact,
) -> tuple[torch.Tensor, dict[str, object]]:
    raw, lineage = raw_static_values_from_pre(pre_state, static_context)
    return encode_static_values(raw, normalization), lineage


__all__ = [
    "M1StaticNormalizationArtifact",
    "STATIC_FEATURE_COUNT",
    "STATIC_FEATURE_NAMES",
    "STATIC_MISSING_MASK_NAMES",
    "STATIC_NUMERIC_FEATURE_NAMES",
    "StaticNormalizationValue",
    "encode_static_values",
    "fit_static_normalization",
    "raw_static_values_from_lineage",
    "raw_static_values_from_pre",
    "static_reference_features_from_pre",
]
