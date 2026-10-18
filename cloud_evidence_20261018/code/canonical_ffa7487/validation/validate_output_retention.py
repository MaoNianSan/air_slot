"""Read-only guard for the V2 output retention plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
PLAN = ROOT / "reports" / "output_refactor" / "OUTPUT_DEEP_CLEAN_PLAN_V2.csv"
BASELINE_SNAPSHOT = ROOT / "reports" / "output_refactor" / "OUTPUT_DEEP_CLEAN_BASELINE_V2.json"
INDEX = ROOT / "registries" / "ACTIVE_MODEL_ARTIFACTS_V1.json"
RUNTIME_MANIFEST = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1R1.json"
FINAL_VALIDATION_PROVENANCE_INDEX = (
    ROOT / "reports" / "provenance" / "FINAL_VALIDATION_PROVENANCE_V1R1.json"
)
FINAL_VALIDATION_PROVENANCE_CATEGORY = "FINAL_VALIDATION_PROVENANCE"
FINAL_VALIDATION_PROVENANCE_PATHS = {
    "reports/model/FINAL_PRECOMMIT_VALIDATION_V1R1.json",
    "reports/model/FINAL_PRECOMMIT_VALIDATION_V1R1.md",
    "reports/provenance/FINAL_PRECOMMIT_WORKTREE_SNAPSHOT_V1R1.json",
}
FINAL_VALIDATION_METADATA_PATHS = {
    *FINAL_VALIDATION_PROVENANCE_PATHS,
    "reports/provenance/FINAL_VALIDATION_PROVENANCE_V1R1.json",
}
SELF_METADATA = {
    "reports/output_refactor/OUTPUT_DEEP_CLEAN_PLAN_V2.csv",
    "reports/output_refactor/OUTPUT_DEEP_CLEAN_BASELINE_V2.json",
    "reports/output_refactor/AIR_SLOT_HISTORICAL_OUTPUT_DEEP_CLEAN_REPORT_V2.json",
    "reports/output_refactor/AIR_SLOT_HISTORICAL_OUTPUT_DEEP_CLEAN_REPORT_V2.md",
}
ACTIVE_REGISTRY_PATHS = {
    "registries/ACTIVE_MODEL_ARTIFACTS_V1.json",
    "registries/ACTIVE_MODEL_IMPLEMENTATION.json",
    "registries/MODEL_BASELINE_IMPLEMENTATION_V1R1.json",
    "registries/MODEL_BASELINE_SEAL_V1.json",
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1R1.json",
}
REQUIRED_RUNTIME_PATHS = {
    "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE.npz",
    "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_MANIFEST.json",
    "artifacts/diagnostics/v5_development_freeze/m1_hstar_evidence.json",
    "artifacts/diagnostics/v5_development_freeze/m1_wstar_evidence.json",
    "artifacts/diagnostics/v5_development_freeze/PRE_SPLIT_CONTAINMENT_AUDIT.json",
    "artifacts/diagnostics/v5_development_freeze/PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json",
    "artifacts/diagnostics/v5_development_freeze/PRE_DEVELOPMENT_STREAM_MANIFEST.json",
    "artifacts/diagnostics/v5_development_freeze/PRE_DEVELOPMENT_STREAM_MANIFEST_RESUME.pt",
    "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_PREPARATION_PROGRESS.json",
    "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_PREPARATION_STATE.pt",
    "artifacts/diagnostics/v5_development_freeze/runs_signed_wstar/W30_H32_seed20260813.pt",
}
REQUIRED_TEST_FIXTURE_PREFIXES = (
    "artifacts/diagnostics/data_usage_contract_audit/",
    "artifacts/diagnostics/model/m1_v2_model_closure/",
    "artifacts/diagnostics/m1_v2_data_gate_a2/",
    "artifacts/diagnostics/m1_v2_feature_gate_b1r/",
    "artifacts/diagnostics/m1_v2_feature_gate_b1/",
    "artifacts/diagnostics/m1_v2_feature_gate_b2/",
    "artifacts/diagnostics/m1_v2_feature_gate_b2r/",
    "artifacts/diagnostics/m1_v2_target_support_gate_c0/",
    "artifacts/diagnostics/m1_v2_target_support_gate_c0a/",
    "artifacts/diagnostics/v5_development_freeze/M1_SIGNED_WARNING_MODEL_V1",
)
SCAN_ROOTS = ("artifacts", "reports", "outputs", "registries", "configs", "codex_framework")
OUTPUT_EXTENSIONS = {".json", ".csv", ".parquet", ".md", ".txt", ".log", ".pkl", ".pt", ".joblib", ".npz", ".jsonl", ".yaml", ".yml", ".pdf", ".png"}
IMMUTABLE = {
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1.json",
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1_PROVENANCE.json",
    "registries/MODEL_IMPLEMENTATION_SUPERSESSION_V1_TO_V1R1.json",
    "artifacts/provenance/model_baseline_v1_source",
    "reports/model_refactor/AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1.json",
    "reports/model_refactor/AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1.md",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _is_immutable(path: str) -> bool:
    return any(path == item or path.startswith(item.rstrip("/") + "/") for item in IMMUTABLE)


def _files() -> set[str]:
    result: set[str] = set()
    for root_name in SCAN_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in OUTPUT_EXTENSIONS:
                result.add(_rel(path))
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix.lower() in OUTPUT_EXTENSIONS:
            result.add(_rel(path))
    return result


def _validate_final_validation_provenance(errors: list[str]) -> dict[str, Any]:
    """Validate the fixed, non-runtime final-validation provenance set."""
    if not FINAL_VALIDATION_PROVENANCE_INDEX.is_file():
        errors.append("MISSING_FINAL_VALIDATION_PROVENANCE_INDEX")
        return {"status": "FAIL", "entries": 0, "broken_references": 0}
    try:
        payload = json.loads(FINAL_VALIDATION_PROVENANCE_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        errors.append("INVALID_FINAL_VALIDATION_PROVENANCE_INDEX")
        return {"status": "FAIL", "entries": 0, "broken_references": 0}
    if payload.get("schema_version") != "FINAL_VALIDATION_PROVENANCE_V1R1":
        errors.append("FINAL_VALIDATION_PROVENANCE_SCHEMA_MISMATCH")
    entries = payload.get("entries", [])
    if not isinstance(entries, list) or len(entries) != len(FINAL_VALIDATION_PROVENANCE_PATHS):
        errors.append("FINAL_VALIDATION_PROVENANCE_ENTRY_COUNT_MISMATCH")
        entries = entries if isinstance(entries, list) else []
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    broken = 0
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("INVALID_FINAL_VALIDATION_PROVENANCE_ENTRY")
            broken += 1
            continue
        path_text = str(entry.get("path", "")).replace("\\", "/")
        seen_paths.add(path_text)
        artifact_id = str(entry.get("artifact_id", ""))
        if artifact_id in seen_ids or not artifact_id:
            errors.append("DUPLICATE_OR_MISSING_FINAL_VALIDATION_ARTIFACT_ID")
        seen_ids.add(artifact_id)
        if path_text not in FINAL_VALIDATION_PROVENANCE_PATHS:
            errors.append(f"UNAUTHORIZED_FINAL_VALIDATION_PROVENANCE_PATH:{path_text}")
            broken += 1
            continue
        if entry.get("category") != FINAL_VALIDATION_PROVENANCE_CATEGORY:
            errors.append(f"FINAL_VALIDATION_PROVENANCE_CATEGORY_MISMATCH:{path_text}")
        if entry.get("scientific_runtime_dependency") is not False:
            errors.append(f"FINAL_VALIDATION_RUNTIME_DEPENDENCY_NOT_FALSE:{path_text}")
        if not entry.get("purpose"):
            errors.append(f"FINAL_VALIDATION_PROVENANCE_PURPOSE_MISSING:{path_text}")
        path = ROOT / path_text
        if not path.is_file():
            errors.append(f"MISSING_FINAL_VALIDATION_PROVENANCE:{path_text}")
            broken += 1
            continue
        if int(entry.get("size", -1)) != path.stat().st_size:
            errors.append(f"FINAL_VALIDATION_PROVENANCE_SIZE_MISMATCH:{path_text}")
            broken += 1
        if entry.get("sha256") != _sha256(path):
            errors.append(f"FINAL_VALIDATION_PROVENANCE_HASH_MISMATCH:{path_text}")
            broken += 1
    if seen_paths != FINAL_VALIDATION_PROVENANCE_PATHS:
        errors.append("FINAL_VALIDATION_PROVENANCE_PATH_SET_MISMATCH")
    return {
        "status": "PASS" if not any(
            error.startswith((
                "MISSING_FINAL_VALIDATION_PROVENANCE",
                "INVALID_FINAL_VALIDATION_PROVENANCE",
                "FINAL_VALIDATION_PROVENANCE_",
                "UNAUTHORIZED_FINAL_VALIDATION_PROVENANCE",
                "DUPLICATE_OR_MISSING_FINAL_VALIDATION",
            ))
            for error in errors
        ) else "FAIL",
        "entries": len(entries),
        "broken_references": broken,
        "category": FINAL_VALIDATION_PROVENANCE_CATEGORY,
    }


def validate() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not PLAN.exists():
        return {"status": "FAIL", "errors": ["MISSING_OUTPUT_DEEP_CLEAN_PLAN_V2"], "warnings": []}
    if not BASELINE_SNAPSHOT.exists():
        errors.append("MISSING_OUTPUT_DEEP_CLEAN_BASELINE_V2")
    else:
        try:
            baseline = json.loads(BASELINE_SNAPSHOT.read_text(encoding="utf-8"))
            if baseline.get("schema_version") != "OUTPUT_DEEP_CLEAN_BASELINE_V2":
                errors.append("BASELINE_SNAPSHOT_SCHEMA_MISMATCH")
            initial = baseline.get("initial_v2_scan", {})
            if initial.get("files") != 9458 or initial.get("bytes") != 4949568186:
                errors.append("BASELINE_SNAPSHOT_INITIAL_SCAN_MISMATCH")
        except (OSError, json.JSONDecodeError, TypeError):
            errors.append("INVALID_OUTPUT_DEEP_CLEAN_BASELINE_V2")
    with PLAN.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_path = {row["path"].replace("\\", "/"): row for row in rows}
    active = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    active_entries = active.get("entries", [])
    active_paths = {str(entry.get("path", "")).replace("\\", "/") for entry in active_entries}
    protected_delete = [row["path"] for row in rows if row.get("classification") == "DELETE" and (row.get("protected") == "True" or _is_immutable(row["path"]) or row["path"] in ACTIVE_REGISTRY_PATHS)]
    if protected_delete:
        errors.append("PROTECTED_OBJECT_SCHEDULED_FOR_DELETE:" + ",".join(protected_delete[:10]))
    for entry in active_entries:
        path_text = str(entry.get("path", "")).replace("\\", "/")
        path = ROOT / path_text
        row = by_path.get(path_text)
        if row is None:
            errors.append(f"ACTIVE_PATH_MISSING_FROM_PLAN:{path_text}")
        if not path.is_file():
            errors.append(f"MISSING_ACTIVE_ARTIFACT:{path_text}")
            continue
        if int(entry.get("size_bytes", -1)) != path.stat().st_size:
            errors.append(f"ACTIVE_SIZE_MISMATCH:{path_text}")
        if entry.get("sha256") != _sha256(path):
            errors.append(f"ACTIVE_HASH_MISMATCH:{path_text}")
        if row and row.get("classification") != "KEEP":
            errors.append(f"ACTIVE_NOT_KEEP:{path_text}")
    for path_text in ACTIVE_REGISTRY_PATHS:
        row = by_path.get(path_text)
        if row is None:
            errors.append(f"ACTIVE_REGISTRY_MISSING_FROM_PLAN:{path_text}")
        elif row.get("classification") != "KEEP":
            errors.append(f"ACTIVE_REGISTRY_NOT_KEEP:{path_text}")
    for path_text in REQUIRED_RUNTIME_PATHS:
        path = ROOT / path_text
        row = by_path.get(path_text)
        if not path.is_file():
            errors.append(f"MISSING_REQUIRED_RUNTIME_PROVENANCE:{path_text}")
        if row is None:
            errors.append(f"REQUIRED_RUNTIME_PROVENANCE_MISSING_FROM_PLAN:{path_text}")
        elif row.get("classification") != "KEEP":
            errors.append(f"REQUIRED_RUNTIME_PROVENANCE_NOT_KEEP:{path_text}")
    for path_text, row in by_path.items():
        if any(path_text.startswith(prefix) for prefix in REQUIRED_TEST_FIXTURE_PREFIXES) and row.get("classification") != "KEEP":
            errors.append(f"TEST_FIXTURE_NOT_KEEP:{path_text}")
    if INDEX.exists() and active.get("selection_policy") != "EXPLICIT_PATH_ONLY_NO_LATEST_FILE_DISCOVERY":
        errors.append("LATEST_FILE_DISCOVERY_POLICY_MISMATCH")
    if len([row for row in rows if row.get("classification") == "REVIEW"]) > 20:
        errors.append("REVIEW_COUNT_OVER_20")
    final_validation_provenance = _validate_final_validation_provenance(errors)
    current_files = _files()
    # The plan and its report are self-describing metadata generated after the
    # inventory pass and are intentionally outside the deletion rows.
    allowed_metadata = SELF_METADATA | FINAL_VALIDATION_METADATA_PATHS
    unplanned = sorted((current_files - set(by_path)) - allowed_metadata)
    if unplanned:
        errors.append("UNPLANNED_OUTPUT_FILES:" + ",".join(unplanned[:10]))
    # Runtime code manifest is the authority for implementation files.  This
    # catches an unindexed/missing runtime object without scanning output data.
    if RUNTIME_MANIFEST.exists():
        manifest = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
        for entry in manifest.get("entries", []):
            path = ROOT / str(entry.get("relative_path", ""))
            if not path.is_file():
                errors.append("MISSING_RUNTIME_MANIFEST_FILE:" + str(entry.get("relative_path")))
            elif entry.get("sha256") and _sha256(path) != entry.get("sha256"):
                errors.append("RUNTIME_MANIFEST_HASH_MISMATCH:" + str(entry.get("relative_path")))
    # Persistent scratch is allowed only when explicitly deleted or protected
    # as a frozen fixture.
    scratch_pattern = re.compile(r"(?i)(pytest_cache|__pycache__|(^|[/_])(tmp|temp|scratch|debug|smoke)([/_.-]|$))")
    for path, row in by_path.items():
        if not (path.startswith("configs/") or path.startswith("registries/")) and scratch_pattern.search(path) and row.get("classification") in {"ARCHIVE_MINIMAL", "REVIEW"}:
            warnings.append("PERSISTENT_SCRATCH_RETAINED:" + path)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "plan_rows": len(rows),
        "active_entries": len(active_entries),
        "review_count": sum(1 for row in rows if row.get("classification") == "REVIEW"),
        "protected_delete_count": len(protected_delete),
        "unplanned_output_count": len(unplanned),
        "final_validation_provenance": final_validation_provenance,
        "newest_file_discovery": "NOT_ALLOWED_BY_ACTIVE_INDEX_POLICY",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"{result['status']}: {result['errors'] or 'retention plan is consistent'}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
