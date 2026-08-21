"""Train-only deterministic and near-linear redundancy diagnostics for B1."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES, V2_WEATHER_FIELDS
from validation.m1_v2_feature_profile import current_rows, static_rows


def _train_matrix(cache: M1DevelopmentBaseCache) -> tuple[np.ndarray, tuple[str, ...]]:
    dynamic, splits = current_rows(cache)
    static, _, _ = static_rows(cache)
    selected = splits == "train"
    return np.concatenate((dynamic[selected], static[selected]), axis=1), (
        *FEATURE_NAMES_V2,
        *STATIC_FEATURE_NAMES,
    )


def _exact_groups(matrix: np.ndarray, names: tuple[str, ...]) -> list[dict]:
    groups: dict[bytes, list[int]] = defaultdict(list)
    for column in range(matrix.shape[1]):
        values = np.ascontiguousarray(matrix[:, column])
        groups[values.tobytes()].append(column)
    output = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        output.append(
            {
                "classification": "EXACT_DUPLICATE",
                "features": [names[index] for index in indices],
                "constant_group": bool(np.nanstd(matrix[:, indices[0]]) <= 1e-12),
            }
        )
    return sorted(output, key=lambda row: row["features"])


def _complements(matrix: np.ndarray, names: tuple[str, ...]) -> list[dict]:
    output = []
    binary = [
        column
        for column in range(matrix.shape[1])
        if set(np.unique(matrix[:, column][np.isfinite(matrix[:, column])])) <= {0.0, 1.0}
        and np.nanstd(matrix[:, column]) > 1e-12
    ]
    for offset, left in enumerate(binary):
        for right in binary[offset + 1:]:
            valid = np.isfinite(matrix[:, left]) & np.isfinite(matrix[:, right])
            if valid.all() and np.array_equal(
                matrix[valid, left] + matrix[valid, right], np.ones(int(valid.sum()))
            ):
                output.append(
                    {
                        "classification": "DETERMINISTIC_COMPLEMENT",
                        "left": names[left],
                        "right": names[right],
                    }
                )
    return output


def _near_linear(matrix: np.ndarray, names: tuple[str, ...]) -> list[dict]:
    output = []
    for left in range(matrix.shape[1]):
        if np.nanstd(matrix[:, left]) <= 1e-12:
            continue
        for right in range(left + 1, matrix.shape[1]):
            if np.nanstd(matrix[:, right]) <= 1e-12:
                continue
            valid = np.isfinite(matrix[:, left]) & np.isfinite(matrix[:, right])
            if int(valid.sum()) < 3:
                continue
            x = matrix[valid, left]
            y = matrix[valid, right]
            if np.array_equal(x, y) or np.array_equal(x + y, np.ones(len(x))):
                continue
            correlation = float(np.corrcoef(x, y)[0, 1])
            if np.isfinite(correlation) and abs(correlation) >= 0.999:
                output.append(
                    {
                        "classification": "NEAR_LINEAR_REDUNDANCY",
                        "left": names[left],
                        "right": names[right],
                        "pearson_correlation": correlation,
                        "automatic_removal": False,
                    }
                )
    return output


def _repeated_weather_masks(matrix: np.ndarray, names: tuple[str, ...]) -> dict:
    name_index = {name: index for index, name in enumerate(names)}
    fields = tuple(V2_WEATHER_FIELDS)
    output = {}
    for kind in ("stale", "fallback"):
        feature_names = tuple(f"weather.{field}.{kind}_mask" for field in fields)
        reference = matrix[:, name_index[feature_names[0]]]
        equal = all(
            np.array_equal(reference, matrix[:, name_index[name]])
            for name in feature_names[1:]
        )
        output[kind] = {
            "features": list(feature_names),
            "all_train_rows_exactly_equal": equal,
            "classification": (
                "DETERMINISTIC_DUPLICATE_OBJECT_LEVEL_MASK" if equal else "FIELD_LEVEL_VARIATION"
            ),
            "recommendation": "COLLAPSE_OBJECT_LEVEL" if equal else "REPEAT",
        }
    return output


def redundancy_audit(cache: M1DevelopmentBaseCache) -> dict:
    matrix, names = _train_matrix(cache)
    return {
        "basis": "TRAIN_CURRENT_ROWS_ONLY_NO_LABELS",
        "row_count": int(len(matrix)),
        "feature_count": len(names),
        "exact_duplicate_groups": _exact_groups(matrix, names),
        "deterministic_complements": _complements(matrix, names),
        "near_linear_pairs": _near_linear(matrix, names),
        "weather_object_level_masks": _repeated_weather_masks(matrix, names),
        "near_linear_action": "REPORT_ONLY",
    }


__all__ = ["redundancy_audit"]
