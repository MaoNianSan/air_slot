"""Train profiles, shift diagnostics, and encoding checks for Feature Gate B1."""

from __future__ import annotations

from collections import Counter

import numpy as np

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.m1_v2_feature_semantics import semantic_group


SPLITS = ("train", "calibration", "development")
QUANTILES = (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99)


def current_rows(cache: M1DevelopmentBaseCache) -> tuple[np.ndarray, np.ndarray]:
    store = cache.store
    rows = []
    for sample_index in range(len(store.sample_splits)):
        episode_index = int(store.sample_episode_indices[sample_index])
        episode_start = int(store.episode_offsets[episode_index])
        end = int(store.sample_end_offsets[sample_index])
        rows.append(store.values_flat[episode_start + end - 1].numpy())
    return np.asarray(rows, dtype=np.float64), np.asarray(store.sample_splits)


def static_rows(cache: M1DevelopmentBaseCache) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    store = cache.store
    if store.static_values is None:
        values = np.full((len(store.sample_splits), len(STATIC_FEATURE_NAMES)), np.nan)
    else:
        values = store.static_values.numpy().astype(np.float64, copy=True)
    valid = np.ones_like(values, dtype=bool)
    violations = []
    lineage_keys = ("turnaround_reference", "taxi_reference")
    for row_index, lineage in enumerate(store.static_context_lineages):
        payload = lineage or {}
        expected = []
        for column, key in enumerate(lineage_keys):
            item = payload.get(key)
            raw = item.get("value") if isinstance(item, dict) else None
            valid[row_index, column] = raw is not None
            expected.append(None if raw is None else float(raw))
        if all(item is not None for item in expected):
            if not np.array_equal(values[row_index], np.asarray(expected, dtype=np.float64)):
                violations.append(
                    {
                        "sample_index": row_index,
                        "split": store.sample_splits[row_index],
                        "episode_id": store.sample_episode_ids[row_index],
                        "decision_node_id": store.sample_decision_node_ids[row_index],
                        "kind": "STATIC_CACHE_VALUE_LINEAGE_MISMATCH",
                        "cached": values[row_index].tolist(),
                        "lineage_expected": expected,
                    }
                )
        else:
            valid[row_index, :] = False
            violations.append(
                {
                    "sample_index": row_index,
                    "split": store.sample_splits[row_index],
                    "episode_id": store.sample_episode_ids[row_index],
                    "decision_node_id": store.sample_decision_node_ids[row_index],
                    "kind": (
                        "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"
                        if np.all(values[row_index] == 0.0)
                        else "STATIC_PARTIAL_LINEAGE_WITH_UNMASKED_NUMERIC_BLOCK"
                    ),
                    "cached": values[row_index].tolist(),
                    "lineage_expected": expected,
                }
            )
    values[~valid] = np.nan
    return values, valid, violations


def _dynamic_invalid_masks(matrix: np.ndarray) -> dict[str, np.ndarray]:
    index = {name: position for position, name in enumerate(FEATURE_NAMES_V2)}
    masks: dict[str, np.ndarray] = {}
    for name in FEATURE_NAMES_V2:
        invalid = np.zeros(len(matrix), dtype=bool)
        group = semantic_group(name)
        if group == "CURRENT_SCHEDULE" and not name.endswith("_mask"):
            invalid = matrix[:, index[f"{name}.missing_mask"]] > 0.5
        elif group == "CURRENT_WEATHER":
            base = name.removesuffix(".sin").removesuffix(".cos")
            invalid = matrix[:, index[f"{base}.missing_mask"]] > 0.5
            if name == "weather.ceiling_base_m":
                invalid |= matrix[:, index[f"{name}.unlimited_mask"]] > 0.5
        elif group in {"LOCAL_DELTA", "AR_SUMMARY"}:
            invalid = matrix[:, index[f"{name}.derived_missing_mask"]] > 0.5
        elif group == "OBSERVATION_AGE":
            invalid = matrix[:, index["current_weather.support.ABSTAIN"]] > 0.5
        masks[name] = invalid
    return masks


def _skewness(values: np.ndarray) -> float | None:
    if not len(values):
        return None
    std = float(np.std(values))
    if std <= 1e-12:
        return 0.0
    centered = (values - float(np.mean(values))) / std
    return float(np.mean(centered ** 3))


def _profile_column(name: str, column: np.ndarray, invalid: np.ndarray) -> dict:
    finite = np.isfinite(column)
    observed_mask = finite & ~invalid
    observed = column[observed_mask]
    quantiles = np.quantile(observed, QUANTILES).tolist() if len(observed) else [None] * 7
    values, counts = np.unique(column[finite], return_counts=True)
    dominant_fraction = float(counts.max() / finite.sum()) if len(counts) else None
    unique = set(float(value) for value in values)
    binary = bool(unique and unique <= {0.0, 1.0})
    zero_count = int(np.sum(column[finite] == 0.0))
    one_count = int(np.sum(column[finite] == 1.0))
    std = float(np.std(observed)) if len(observed) else None
    normalization = _normalization_class(name)
    return {
        "feature": name,
        "semantic_group": semantic_group(name),
        "count": int(len(column)),
        "observed_count": int(observed_mask.sum()),
        "missing_invalid_pct": float(100.0 * (1.0 - observed_mask.sum() / max(len(column), 1))),
        "mean": float(np.mean(observed)) if len(observed) else None,
        "std": std,
        "min": float(np.min(observed)) if len(observed) else None,
        "p1": quantiles[0],
        "p5": quantiles[1],
        "p25": quantiles[2],
        "p50": quantiles[3],
        "p75": quantiles[4],
        "p95": quantiles[5],
        "p99": quantiles[6],
        "max": float(np.max(observed)) if len(observed) else None,
        "unique_count": int(len(values)),
        "zero_fraction": float(zero_count / max(int(finite.sum()), 1)),
        "one_fraction": float(one_count / max(int(finite.sum()), 1)),
        "constant": bool(std is not None and std <= 1e-12),
        "near_constant": bool(dominant_fraction is not None and dominant_fraction >= 0.995),
        "dominant_fraction": dominant_fraction,
        "binary": binary,
        "zero_count": zero_count if binary else None,
        "one_count": one_count if binary else None,
        "minority_fraction": (
            float(min(zero_count, one_count) / max(zero_count + one_count, 1))
            if binary else None
        ),
        "normalization": normalization,
        "skewness": _skewness(observed),
        "abs_z_gt_5_fraction": (
            float(np.mean(np.abs(observed) > 5.0))
            if len(observed) and normalization in {
                "TRAIN_STANDARDIZED", "DERIVED_FROM_STANDARDIZED"
            }
            else None
        ),
        "abs_z_gt_10_fraction": (
            float(np.mean(np.abs(observed) > 10.0))
            if len(observed) and normalization in {
                "TRAIN_STANDARDIZED", "DERIVED_FROM_STANDARDIZED"
            }
            else None
        ),
        "non_finite_count": int((~finite).sum()),
    }


def _normalization_class(name: str) -> str:
    group = semantic_group(name)
    if group == "STATIC_REFERENCE":
        return "STATIC_RAW"
    if group in {
        "CURRENT_STATE", "RAW_MISSING_MASK", "STALE_MASK", "FALLBACK_MASK",
        "DERIVED_MISSING_MASK", "CEILING_STATUS", "EVIDENCE_ENCODING",
        "SUPPORT_ENCODING",
    }:
        return "BINARY_NO_SCALE"
    if name.endswith((".sin", ".cos")):
        return "SIN_COS_NO_SCALE"
    if group in {"LOCAL_DELTA", "AR_SUMMARY"}:
        return "DERIVED_FROM_STANDARDIZED"
    return "TRAIN_STANDARDIZED"


def feature_profiles(cache: M1DevelopmentBaseCache) -> dict:
    dynamic, splits = current_rows(cache)
    static, static_valid, static_violations = static_rows(cache)
    dynamic_invalid = _dynamic_invalid_masks(dynamic)
    output = {}
    for split in SPLITS:
        selected = splits == split
        records = []
        for column, name in enumerate(FEATURE_NAMES_V2):
            records.append(
                _profile_column(name, dynamic[selected, column], dynamic_invalid[name][selected])
            )
        for column, name in enumerate(STATIC_FEATURE_NAMES):
            records.append(
                _profile_column(name, static[selected, column], ~static_valid[selected, column])
            )
        output[split] = records
    return {"profiles": output, "static_contract_violations": static_violations}


def missing_encoding_audit(cache: M1DevelopmentBaseCache) -> dict:
    matrix, splits = current_rows(cache)
    index = {name: position for position, name in enumerate(FEATURE_NAMES_V2)}
    checks = []
    violations = []
    violation_counts: Counter[str] = Counter()

    def record_check(numeric_name: str, mask_name: str, bad: np.ndarray,
                     masked: np.ndarray, kind: str) -> None:
        checks.append(
            {
                "numeric": numeric_name,
                "mask": mask_name,
                "missing_rows": int(masked.sum()),
                "violations": int(len(bad)),
                "violations_by_split": {
                    split: int(np.sum(splits[bad] == split)) for split in SPLITS
                },
            }
        )
        violation_counts[kind] += int(len(bad))
        violations.extend(
            {"kind": kind, "feature": numeric_name, "row": int(row),
             "split": str(splits[row])}
            for row in bad[:20]
        )

    current_pairs = [
        ("schedule.signed_minutes_to_crs_departure", "schedule.signed_minutes_to_crs_departure.missing_mask"),
        *[
            (f"weather.{field}", f"weather.{field}.missing_mask")
            for field in (
                "temperature_c", "dewpoint_c", "wind_speed_mps", "qnh_hpa",
                "visibility_m", "ceiling_base_m",
            )
        ],
    ]
    for numeric_name, mask_name in current_pairs:
        missing = matrix[:, index[mask_name]] > 0.5
        bad = np.flatnonzero(missing & (matrix[:, index[numeric_name]] != 0.0))
        record_check(numeric_name, mask_name, bad, missing, "MISSING_NUMERIC_NOT_ZERO")

    wind_missing = matrix[:, index["weather.wind_direction_deg.missing_mask"]] > 0.5
    for numeric_name in ("weather.wind_direction_deg.sin", "weather.wind_direction_deg.cos"):
        bad = np.flatnonzero(wind_missing & (matrix[:, index[numeric_name]] != 0.0))
        record_check(
            numeric_name, "weather.wind_direction_deg.missing_mask", bad,
            wind_missing, "MISSING_NUMERIC_NOT_ZERO",
        )

    unlimited = matrix[:, index["weather.ceiling_base_m.unlimited_mask"]] > 0.5
    bad_unlimited = np.flatnonzero(
        unlimited & (matrix[:, index["weather.ceiling_base_m"]] != 0.0)
    )
    record_check(
        "weather.ceiling_base_m", "weather.ceiling_base_m.unlimited_mask",
        bad_unlimited, unlimited, "UNLIMITED_CEILING_NUMERIC_NOT_ZERO",
    )

    for numeric_name in FEATURE_NAMES_V2:
        if not numeric_name.startswith(("delta.", "ar.")) or numeric_name.endswith("_mask"):
            continue
        mask_name = f"{numeric_name}.derived_missing_mask"
        invalid = matrix[:, index[mask_name]] > 0.5
        bad = np.flatnonzero(invalid & (matrix[:, index[numeric_name]] != 0.0))
        record_check(
            numeric_name, mask_name, bad, invalid, "DERIVED_INVALID_NUMERIC_NOT_ZERO",
        )
    return {
        "checks": checks,
        "violations": violations,
        "violation_counts": dict(violation_counts),
        "all_checked_encodings_exact": not violations,
        "observation_age_contract_note": (
            "Missing age is zero-filled by the encoder without a dedicated age mask; "
            "current_weather.support.ABSTAIN is the only object-level proxy."
        ),
    }


def shift_diagnostics(profiles: dict[str, list[dict]], keep_features: list[str]) -> dict:
    by_split = {
        split: {row["feature"]: row for row in profiles[split]}
        for split in SPLITS
    }
    output = {}
    for split in ("calibration", "development"):
        rows = []
        for name in keep_features:
            train = by_split["train"][name]
            other = by_split[split][name]
            train_std = train["std"] or 0.0
            mean_shift = None
            if train["mean"] is not None and other["mean"] is not None:
                mean_shift = float((other["mean"] - train["mean"]) / max(train_std, 1e-12))
            range_shift = bool(
                train["min"] is not None and other["min"] is not None
                and (other["min"] < train["min"] or other["max"] > train["max"])
            )
            rows.append(
                {
                    "feature": name,
                    "missing_invalid_pct_shift": (
                        other["missing_invalid_pct"] - train["missing_invalid_pct"]
                    ),
                    "mean_shift_in_train_std": mean_shift,
                    "std_ratio_to_train": (
                        None if other["std"] is None else float(other["std"] / max(train_std, 1e-12))
                    ),
                    "extreme_range_shift": range_shift,
                    "unseen_binary_state": bool(
                        train["binary"] and other["binary"]
                        and other["unique_count"] > train["unique_count"]
                    ),
                }
            )
        output[split] = rows
    return output


def target_support_from_a2(a2_result: dict) -> dict:
    labels = {
        split: {
            target: values["new"]
            for target, values in a2_result["downstream"]["labels"][split].items()
        }
        for split in SPLITS
    }
    overflow = sum(
        values["overflow_count"]
        for split in labels.values()
        for values in split.values()
    )
    return {
        "source": "A2 downstream.labels.new",
        "splits": labels,
        "TARGET_SUPPORT_REVIEW_REQUIRED": "YES" if overflow else "NO",
        "overflow_count_all_nonfinal_splits": overflow,
        "contract_action": "DEFER_UNTIL_AFTER_FEATURE_FREEZE_BEFORE_TUNING",
    }


def support_state_counts(cache: M1DevelopmentBaseCache) -> dict:
    matrix, splits = current_rows(cache)
    index = {name: position for position, name in enumerate(FEATURE_NAMES_V2)}
    output = {}
    for split in SPLITS:
        selected = splits == split
        output[split] = {}
        for obj in ("current_weather", "schedule_reference", "current_state"):
            output[split][obj] = {
                level: int(np.sum(matrix[selected, index[f"{obj}.support.{level}"]] > 0.5))
                for level in ("SUPPORTED", "DEGRADED", "ABSTAIN")
            }
    return output


__all__ = [
    "SPLITS",
    "current_rows",
    "feature_profiles",
    "missing_encoding_audit",
    "shift_diagnostics",
    "static_rows",
    "support_state_counts",
    "target_support_from_a2",
]
