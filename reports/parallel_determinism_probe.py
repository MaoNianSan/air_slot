from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ATOL = 1e-10
RTOL = 1e-12

MODULES = ("overall_run", "overall_adv", "part_adv")
N1_NAME = "fast_code_audit_n1"
N14_NAME = "fast_three_change_dev"

NON_SCIENTIFIC_COLUMNS = {
    "run_id",
    "config_hash",
    "implementation_hash",
    "requested_n_jobs",
    "resolved_n_jobs",
    "outer_workers",
    "inner_model_threads",
    "worker_count",
    "lightgbm_n_jobs",
    "parallel_backend",
    "process_id",
    "started_at",
    "updated_at",
    "completed_at",
    "created_at",
    "generated_at",
    "timestamp",
    "wall_time",
    "wall_time_seconds",
    "elapsed",
    "elapsed_seconds",
    "runtime_seconds",
    "fit_seconds",
    "predict_seconds",
    "prediction_ms_per_snapshot",
    "output_path",
    "output_dir",
    "source_path",
    "artifact_path",
}

NON_SCIENTIFIC_JSON_KEYS = NON_SCIENTIFIC_COLUMNS | {
    "mode",
    "output_name",
    "output_id",
    "profile_id",
    "upstream_run_id",
    "task_seed_hash",
    "input_hash",
    "artifact_hash",
    "sha256",
    "path",
    "relative_path",
    "absolute_path",
    "file",
    "file_size",
    "parallel_model_count",
}

REGISTRY_FILES = ("run_summary.json", "artifact_registry.json")


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return [_jsonable(item) for item in list(value)]
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, (bool, np.bool_)) and bool(missing):
        return None
    return value


def _canonical_text(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)


def _drop_non_scientific_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    ignored = [
        column
        for column in frame.columns
        if column.lower() in NON_SCIENTIFIC_COLUMNS
        or column.lower().startswith("prediction_ms_per_snapshot")
    ]
    return frame.drop(columns=ignored), ignored


def _canonical_sort(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or not len(frame.columns):
        return frame.reset_index(drop=True)
    sort_frame = pd.DataFrame(index=frame.index)
    for column in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[column].dtype):
            values = pd.to_numeric(frame[column], errors="coerce").astype(float)
            sort_frame[column] = values.round(10).map(_canonical_text)
        else:
            sort_frame[column] = frame[column].map(_canonical_text)
    order = sort_frame.sort_values(list(sort_frame.columns), kind="mergesort").index
    return frame.loc[order].reset_index(drop=True)


def _frame_digest(frame: pd.DataFrame) -> str:
    payload = {
        "columns": list(frame.columns),
        "rows": [[_jsonable(value) for value in row] for row in frame.itertuples(index=False, name=None)],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compare_parquet(module: str, relative_path: Path) -> dict[str, Any]:
    left_path = ROOT / module / "output" / N1_NAME / relative_path
    right_path = ROOT / module / "output" / N14_NAME / relative_path
    left_raw = pd.read_parquet(left_path)
    right_raw = pd.read_parquet(right_path)
    left, ignored_left = _drop_non_scientific_columns(left_raw)
    right, ignored_right = _drop_non_scientific_columns(right_raw)

    result: dict[str, Any] = {
        "module": module,
        "relative_path": relative_path.as_posix(),
        "n1_rows": len(left_raw),
        "n14_rows": len(right_raw),
        "n1_columns": len(left_raw.columns),
        "n14_columns": len(right_raw.columns),
        "ignored_columns": "|".join(sorted(set(ignored_left) | set(ignored_right))),
        "schema_equal": False,
        "row_count_equal": len(left_raw) == len(right_raw),
        "non_numeric_equal": False,
        "numeric_within_tolerance": False,
        "max_abs_diff": np.nan,
        "status": "FAIL",
        "detail": "",
    }

    if list(left.columns) != list(right.columns):
        result["detail"] = "scientific column list differs"
        return result
    result["schema_equal"] = all(str(left[column].dtype) == str(right[column].dtype) for column in left.columns)
    if not result["schema_equal"]:
        result["detail"] = "scientific dtype differs"
        return result
    if not result["row_count_equal"]:
        result["detail"] = "row count differs"
        return result

    left = _canonical_sort(left)
    right = _canonical_sort(right)
    numeric_columns = [column for column in left.columns if pd.api.types.is_numeric_dtype(left[column].dtype)]
    non_numeric_columns = [column for column in left.columns if column not in numeric_columns]

    non_numeric_equal = True
    for column in non_numeric_columns:
        if left[column].map(_canonical_text).tolist() != right[column].map(_canonical_text).tolist():
            non_numeric_equal = False
            result["detail"] = f"non-numeric values differ: {column}"
            break
    result["non_numeric_equal"] = non_numeric_equal

    max_abs_diff = 0.0
    numeric_equal = True
    if non_numeric_equal:
        for column in numeric_columns:
            left_values = pd.to_numeric(left[column], errors="coerce").to_numpy(dtype=float)
            right_values = pd.to_numeric(right[column], errors="coerce").to_numpy(dtype=float)
            same_nan = np.isnan(left_values) == np.isnan(right_values)
            if not bool(np.all(same_nan)):
                numeric_equal = False
                result["detail"] = f"numeric null pattern differs: {column}"
                break
            mask = ~np.isnan(left_values)
            if bool(np.any(mask)):
                differences = np.abs(left_values[mask] - right_values[mask])
                column_max = float(np.max(differences))
                max_abs_diff = max(max_abs_diff, column_max)
                if not bool(np.allclose(left_values[mask], right_values[mask], atol=ATOL, rtol=RTOL)):
                    numeric_equal = False
                    result["detail"] = f"numeric values differ: {column}; max_abs_diff={column_max}"
                    break
    else:
        numeric_equal = False
    result["numeric_within_tolerance"] = numeric_equal
    result["max_abs_diff"] = max_abs_diff
    if result["schema_equal"] and result["row_count_equal"] and non_numeric_equal and numeric_equal:
        result["status"] = "PASS"
        result["detail"] = "scientific content equal"
    result["n1_scientific_digest"] = _frame_digest(left)
    result["n14_scientific_digest"] = _frame_digest(right)
    return result


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            lower = str(key).lower()
            if lower in NON_SCIENTIFIC_JSON_KEYS:
                continue
            if lower.endswith("_path") or lower.endswith("_hash") or lower.endswith("_at"):
                continue
            normalized[str(key)] = _normalize_json(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, str):
        return value.replace(N1_NAME, "<DEV_OUTPUT>").replace(N14_NAME, "<DEV_OUTPUT>")
    return _jsonable(value)


def compare_registry(module: str, filename: str) -> dict[str, Any]:
    left_path = ROOT / module / "output" / N1_NAME / filename
    right_path = ROOT / module / "output" / N14_NAME / filename
    result: dict[str, Any] = {
        "module": module,
        "relative_path": filename,
        "n1_exists": left_path.exists(),
        "n14_exists": right_path.exists(),
        "status": "FAIL",
        "n1_logical_digest": "",
        "n14_logical_digest": "",
        "detail": "",
    }
    if not left_path.exists() or not right_path.exists():
        result["detail"] = "registry file missing"
        return result
    left = _normalize_json(json.loads(left_path.read_text(encoding="utf-8")))
    right = _normalize_json(json.loads(right_path.read_text(encoding="utf-8")))
    left_text = json.dumps(left, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    right_text = json.dumps(right, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    result["n1_logical_digest"] = hashlib.sha256(left_text.encode("utf-8")).hexdigest()
    result["n14_logical_digest"] = hashlib.sha256(right_text.encode("utf-8")).hexdigest()
    if left_text == right_text:
        result["status"] = "PASS"
        result["detail"] = "logical content equal after runtime metadata exclusion"
    else:
        result["detail"] = "logical content differs after runtime metadata exclusion"
    return result


def main() -> int:
    file_rows: list[dict[str, Any]] = []
    file_set_rows: list[dict[str, Any]] = []
    for module in MODULES:
        n1_root = ROOT / module / "output" / N1_NAME
        n14_root = ROOT / module / "output" / N14_NAME
        n1_files = {path.relative_to(n1_root) for path in n1_root.rglob("*.parquet")}
        n14_files = {path.relative_to(n14_root) for path in n14_root.rglob("*.parquet")}
        for relative_path in sorted(n1_files | n14_files):
            in_n1 = relative_path in n1_files
            in_n14 = relative_path in n14_files
            file_set_rows.append(
                {
                    "module": module,
                    "relative_path": relative_path.as_posix(),
                    "n1_exists": in_n1,
                    "n14_exists": in_n14,
                    "status": "PASS" if in_n1 and in_n14 else "FAIL",
                }
            )
            if in_n1 and in_n14:
                file_rows.append(compare_parquet(module, relative_path))

    registry_rows = [compare_registry(module, filename) for module in MODULES for filename in REGISTRY_FILES]
    file_set = pd.DataFrame(file_set_rows)
    files = pd.DataFrame(file_rows)
    registries = pd.DataFrame(registry_rows)
    file_set.to_csv(REPORTS / "PARALLEL_DETERMINISM_FILE_SET.csv", index=False)
    files.to_csv(REPORTS / "PARALLEL_DETERMINISM_FILE_COMPARISON.csv", index=False)
    registries.to_csv(REPORTS / "PARALLEL_DETERMINISM_REGISTRY_COMPARISON.csv", index=False)

    file_set_failures = int((file_set["status"] != "PASS").sum()) if not file_set.empty else 1
    parquet_failures = int((files["status"] != "PASS").sum()) if not files.empty else 1
    registry_failures = int((registries["status"] != "PASS").sum()) if not registries.empty else 1
    maximum_difference = float(pd.to_numeric(files["max_abs_diff"], errors="coerce").max()) if not files.empty else float("nan")
    status = "PASS" if file_set_failures == parquet_failures == registry_failures == 0 else "FAIL"

    ranking_paths = files[files["relative_path"].str.contains("ranking|candidate|recommend", case=False, regex=True)]
    ranking_failures = int((ranking_paths["status"] != "PASS").sum()) if not ranking_paths.empty else 1
    report = f"""# Parallel Determinism Audit

Audit date: 2026-08-02

PARALLEL_DETERMINISM_STATUS={status}

- Shared PRE input: `pre/output/{N14_NAME}`.
- 1-thread downstream output: `{N1_NAME}`.
- 14-thread comparison output: `{N14_NAME}`.
- Compared parquet file-set entries: {len(file_set)}; missing-side failures: {file_set_failures}.
- Compared parquet files: {len(files)}; scientific-content failures: {parquet_failures}.
- Numeric tolerance: atol={ATOL}, rtol={RTOL}.
- Maximum scientific numeric absolute difference: {maximum_difference}.
- Ranking/candidate/recommendation parquet files: {len(ranking_paths)}; failures: {ranking_failures}.
- Compared summary/registry logical files: {len(registries)}; failures: {registry_failures}.
- Runtime-only exclusions: run IDs, timestamps, paths, config/implementation/artifact hashes, worker metadata, and performance timing fields.

Detailed comparisons are in `PARALLEL_DETERMINISM_FILE_SET.csv`, `PARALLEL_DETERMINISM_FILE_COMPARISON.csv`, and `PARALLEL_DETERMINISM_REGISTRY_COMPARISON.csv`.
"""
    (REPORTS / "PARALLEL_DETERMINISM_AUDIT.md").write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status,
                "file_set_entries": len(file_set),
                "parquet_files": len(files),
                "parquet_failures": parquet_failures,
                "registry_files": len(registries),
                "registry_failures": registry_failures,
                "ranking_files": len(ranking_paths),
                "ranking_failures": ranking_failures,
                "max_abs_diff": maximum_difference,
            },
            indent=2,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
