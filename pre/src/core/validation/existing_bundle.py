from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .manifest_checks import check_file_hashes, check_manifest
from .membership_checks import check_membership
from .observation_checks import check_observations
from .report_writer import write_validation_report
from .scientific_checks import run_scientific_checks
from .statistics_checks import compare_statistics, stored_component_mismatch
from .table_checks import check_logical_hashes, check_registry, load_tables


def _record_failures(checks: dict[str, Any]) -> list[str]:
    return sorted(
        name
        for name, value in checks.items()
        if isinstance(value, dict) and value.get("status") == "FAIL"
    )


def _file_audit_summary(checks: dict[str, Any], field: str) -> dict[str, Any]:
    return {
        "observations": checks["observations"].get(field, []),
        "observation_membership": checks["membership_uniqueness"].get(field, []),
    }


def validate_existing_bundle(
    root: Path,
    cfg: dict[str, Any],
    *,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(root)
    try:
        manifest = json.loads((root / "pre_manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        result = {"status": "FAIL", "reason": "MANIFEST_UNREADABLE", "detail": str(exc)}
        if write_report:
            write_validation_report(root, result)
        return result
    checks: dict[str, Any] = check_manifest(manifest, cfg)
    checks["file_hashes"] = check_file_hashes(root, manifest)
    table_failures, tables = load_tables(root, cfg)
    checks["table_schemas_and_keys"] = {
        "status": "PASS" if not table_failures else "FAIL",
        "failures": table_failures,
    }
    checks["observations"] = check_observations(root, manifest)
    checks["membership_uniqueness"] = check_membership(root, manifest)
    checks.update(run_scientific_checks(tables, cfg))
    checks["column_registry"], registry = check_registry(root, cfg)
    checks["logical_table_hashes"] = check_logical_hashes(manifest, tables, cfg)
    failures = _record_failures(checks)
    statistics, stored = compare_statistics(
        root,
        tables,
        checks["observations"],
        checks["membership_uniqueness"],
        registry,
    )
    checks["statistics_recomputation"] = statistics
    if statistics["status"] == "FAIL":
        failures.append("statistics_recomputation")
    component_mismatch = stored_component_mismatch(stored, checks, failures)
    if component_mismatch:
        failures.append("stored_validation_mismatch")
    result = {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": sorted(set(failures)),
        "extra_unregistered_files": _file_audit_summary(checks, "extra_unregistered_files"),
        "missing_registered_files": _file_audit_summary(checks, "missing_registered_files"),
        "duplicate_partition_files": _file_audit_summary(checks, "duplicate_partition_files"),
        "pass_empty_file_conflicts": _file_audit_summary(checks, "pass_empty_file_conflicts"),
    }
    if statistics["mismatches"]:
        result["reason"] = "STORED_AND_RECOMPUTED_STATISTICS_MISMATCH"
    elif component_mismatch:
        result["reason"] = "STORED_AND_RECOMPUTED_VALIDATION_MISMATCH"
    if write_report:
        write_validation_report(root, result)
    return result
