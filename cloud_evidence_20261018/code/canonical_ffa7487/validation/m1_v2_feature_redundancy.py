"""Semantic redundancy diagnostics for the M1 V2 feature gates."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES, V2_WEATHER_FIELDS
from validation.m1_v2_feature_profile import current_rows, static_rows
from validation.m1_v2_feature_semantics import semantic_table

CONTRACT_EXACT_DUPLICATE = "CONTRACT_EXACT_DUPLICATE"
EMPIRICAL_EXACT_DUPLICATE = "EMPIRICAL_EXACT_DUPLICATE"
TRAIN_SUPPORT_CONSTANT = "TRAIN_SUPPORT_CONSTANT"
CONTRACT_STRUCTURAL_CONSTANT = "CONTRACT_STRUCTURAL_CONSTANT"
DETERMINISTIC_COMPLEMENT = "DETERMINISTIC_COMPLEMENT"
NEAR_LINEAR_REPORT_ONLY = "NEAR_LINEAR_REPORT_ONLY"

_SCHEDULE_DELTA = "delta.schedule.signed_minutes_to_crs_departure"
_SCHEDULE_DELTA_MASK = f"{_SCHEDULE_DELTA}.derived_missing_mask"


def _feature_names(
    cache: M1DevelopmentBaseCache, feature_names: Iterable[str] | None = None
) -> tuple[str, ...]:
    if feature_names is not None:
        return tuple(feature_names)
    names = cache.manifest.get("feature_names")
    return tuple(names) if names else tuple(FEATURE_NAMES_V2)


def _static_names(cache: M1DevelopmentBaseCache) -> tuple[str, ...]:
    names = cache.manifest.get("static_feature_names")
    return tuple(names) if names else tuple(STATIC_FEATURE_NAMES)


def _train_matrix(
    cache: M1DevelopmentBaseCache, feature_names: Iterable[str] | None = None
):
    dynamic, splits = current_rows(cache)
    static, _, _ = static_rows(cache)
    names = _feature_names(cache, feature_names)
    static_names = _static_names(cache)
    if dynamic.shape[1] != len(names):
        raise ValueError("M1_REDUNDANCY_DYNAMIC_NAME_WIDTH_MISMATCH")
    if static.shape[1] != len(static_names):
        raise ValueError("M1_REDUNDANCY_STATIC_NAME_WIDTH_MISMATCH")
    return np.concatenate((dynamic, static), axis=1), splits, (*names, *static_names)


def _contract_key(name: str) -> tuple[str, ...]:
    rows = {row["FEATURE"]: row for row in semantic_table()}
    row = rows.get(name)
    if row is not None:
        return tuple(
            str(row[key])
            for key in (
                "SOURCE_PRE_VARIABLE",
                "TRANSFORMATION",
                "VALIDITY_RULE",
                "HISTORY_SCOPE",
                "EXPECTED_INFORMATION_ROLE",
            )
        )
    if name.endswith(".derived_missing_mask"):
        base = name.removesuffix(".derived_missing_mask")
        return (
            base,
            "DERIVED_VALIDITY_NEGATION",
            "SOURCE_LOCAL",
            "PREVIOUS_NODE_LOCAL",
            "DERIVED_FEATURE_VALIDITY",
        )
    return (name, "UNSPECIFIED", "UNSPECIFIED", "UNSPECIFIED", "UNSPECIFIED")


def _exact_groups(
    matrix: np.ndarray, names: tuple[str, ...], splits: np.ndarray
) -> list[dict]:
    train = splits == "train"
    groups: dict[bytes, list[int]] = defaultdict(list)
    for column in range(matrix.shape[1]):
        groups[np.ascontiguousarray(matrix[train, column]).tobytes()].append(column)
    output = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        features = [names[index] for index in indices]
        keys = {_contract_key(name) for name in features}
        constant_group = bool(np.nanstd(matrix[:, indices[0]]) <= 1e-12)
        classification = (
            CONTRACT_EXACT_DUPLICATE
            if len(keys) == 1
            else TRAIN_SUPPORT_CONSTANT if constant_group else EMPIRICAL_EXACT_DUPLICATE
        )
        equality = {
            split: bool(
                all(
                    np.array_equal(
                        matrix[splits == split, index],
                        matrix[splits == split, indices[0]],
                    )
                    for index in indices[1:]
                )
            )
            for split in ("train", "calibration", "development")
        }
        output.append(
            {
                "classification": classification,
                "features": features,
                "contract_keys": {name: list(_contract_key(name)) for name in features},
                "train_equal": equality["train"],
                "calibration_equal": equality["calibration"],
                "development_equal": equality["development"],
                "constant_group": constant_group,
            }
        )
    return sorted(output, key=lambda row: row["features"])


def _complements(
    matrix: np.ndarray, names: tuple[str, ...], splits: np.ndarray
) -> list[dict]:
    output = []
    train = splits == "train"
    binary = [
        column
        for column in range(matrix.shape[1])
        if set(np.unique(matrix[:, column][np.isfinite(matrix[:, column])]))
        <= {0.0, 1.0}
        and np.nanstd(matrix[train, column]) > 1e-12
    ]
    for offset, left in enumerate(binary):
        for right in binary[offset + 1 :]:
            valid = train & np.isfinite(matrix[:, left]) & np.isfinite(matrix[:, right])
            if valid.any() and np.array_equal(
                matrix[valid, left] + matrix[valid, right], np.ones(int(valid.sum()))
            ):
                output.append(
                    {
                        "classification": DETERMINISTIC_COMPLEMENT,
                        "left": names[left],
                        "right": names[right],
                    }
                )
    return output


def _near_linear(
    matrix: np.ndarray, names: tuple[str, ...], splits: np.ndarray
) -> list[dict]:
    output = []
    train = splits == "train"
    for left in range(matrix.shape[1]):
        if np.nanstd(matrix[train, left]) <= 1e-12:
            continue
        for right in range(left + 1, matrix.shape[1]):
            if np.nanstd(matrix[train, right]) <= 1e-12:
                continue
            valid = train & np.isfinite(matrix[:, left]) & np.isfinite(matrix[:, right])
            if int(valid.sum()) < 3:
                continue
            x, y = matrix[valid, left], matrix[valid, right]
            if np.array_equal(x, y) or np.array_equal(x + y, np.ones(len(x))):
                continue
            correlation = float(np.corrcoef(x, y)[0, 1])
            if np.isfinite(correlation) and abs(correlation) >= 0.999:
                output.append(
                    {
                        "classification": NEAR_LINEAR_REPORT_ONLY,
                        "left": names[left],
                        "right": names[right],
                        "pearson_correlation": correlation,
                        "automatic_removal": False,
                    }
                )
    return output


def _contract_affine_redundancy(names: tuple[str, ...]) -> list[dict]:
    if _SCHEDULE_DELTA not in names or _SCHEDULE_DELTA_MASK not in names:
        return []
    return [
        {
            "classification": "CONTRACT_AFFINE_REDUNDANCY",
            "features": [_SCHEDULE_DELTA, _SCHEDULE_DELTA_MASK],
            "reason": "FIXED_FIVE_MINUTE_GRID_SCHEDULE_COUNTDOWN_DELTA",
        }
    ]


def _repeated_weather_masks(names: tuple[str, ...]) -> dict:
    name_set = set(names)
    output = {}
    for kind in ("stale", "fallback"):
        object_name = f"current_weather.{kind}_mask"
        field_names = tuple(
            f"weather.{field}.{kind}_mask" for field in V2_WEATHER_FIELDS
        )
        output[kind] = {
            "object_level_feature": object_name,
            "field_level_features_present": [
                name for name in field_names if name in name_set
            ],
            "object_level_present": object_name in name_set,
            "classification": "COLLAPSED_OBJECT_LEVEL_MASK",
            "recommendation": "KEEP_OBJECT_LEVEL_ONLY",
        }
    return output


def redundancy_audit(
    cache: M1DevelopmentBaseCache, feature_names: Iterable[str] | None = None
) -> dict:
    matrix, splits, names = _train_matrix(cache, feature_names)
    groups = _exact_groups(matrix, names, splits)
    contract_groups = [
        g for g in groups if g["classification"] == CONTRACT_EXACT_DUPLICATE
    ]
    empirical_groups = [
        g for g in groups if g["classification"] == EMPIRICAL_EXACT_DUPLICATE
    ]
    support_groups = [
        g for g in groups if g["classification"] == TRAIN_SUPPORT_CONSTANT
    ]
    train = splits == "train"
    train_support_constants = [
        names[index]
        for index in range(matrix.shape[1])
        if np.nanstd(matrix[train, index]) <= 1e-12
    ]
    structural_constants = [
        name
        for name in train_support_constants
        if name.startswith("state.") and name.endswith("_mask")
    ]
    return {
        "basis": "TRAIN_CURRENT_ROWS_ONLY_NO_LABELS_WITH_SEMANTIC_CLASSIFICATION",
        "row_count": int(np.sum(splits == "train")),
        "feature_count": len(names),
        "exact_duplicate_groups": groups,
        "contract_exact_duplicate_groups": contract_groups,
        "empirical_exact_duplicate_groups": empirical_groups,
        "train_support_constant_groups": support_groups,
        "contract_exact_duplicate_count": len(contract_groups),
        "empirical_exact_duplicate_count": len(empirical_groups),
        "train_support_constant_count": len(train_support_constants),
        "contract_structural_constants": structural_constants,
        "contract_structural_constant_count": len(structural_constants),
        "train_support_constants": train_support_constants,
        "deterministic_complements": _complements(matrix, names, splits),
        "contract_affine_redundancy": _contract_affine_redundancy(names),
        "near_linear_pairs": _near_linear(matrix, names, splits),
        "weather_object_level_masks": _repeated_weather_masks(names),
        "near_linear_action": "REPORT_ONLY",
    }


__all__ = [
    "CONTRACT_EXACT_DUPLICATE",
    "EMPIRICAL_EXACT_DUPLICATE",
    "TRAIN_SUPPORT_CONSTANT",
    "CONTRACT_STRUCTURAL_CONSTANT",
    "DETERMINISTIC_COMPLEMENT",
    "NEAR_LINEAR_REPORT_ONLY",
    "redundancy_audit",
]
