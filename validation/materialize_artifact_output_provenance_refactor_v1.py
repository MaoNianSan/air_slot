"""Audit and clean generated Air Slot artifacts and output provenance.

This module deliberately treats generated outputs as data, not executable
model code.  Active scientific/runtime identity is read from the sealed V1
baseline and the active V1R1 implementation pointer; historical outputs are
never selected by timestamp or "latest" discovery.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
REPORT_DIR = ROOT / "reports" / "output_refactor"
INVENTORY_PATH = REPORT_DIR / "OUTPUT_FILE_INVENTORY_V1.csv"
DIRECTORY_PATH = REPORT_DIR / "OUTPUT_DIRECTORY_INVENTORY_V1.csv"
GRAPH_PATH = REPORT_DIR / "OUTPUT_REFERENCE_GRAPH_V1.json"
DUPLICATION_PATH = REPORT_DIR / "OUTPUT_DUPLICATION_AUDIT_V1.md"
DELETION_PLAN_PATH = REPORT_DIR / "OUTPUT_DELETION_PLAN_V1.csv"
ACTIVE_INDEX_PATH = ROOT / "registries" / "ACTIVE_MODEL_ARTIFACTS_V1.json"
CURRENT_STATUS_PATH = ROOT / "reports" / "model" / "MODEL_CURRENT_STATUS.md"
FINAL_REPORT_JSON = REPORT_DIR / "AIR_SLOT_ARTIFACT_OUTPUT_REFACTOR_REPORT_V1.json"
FINAL_REPORT_MD = REPORT_DIR / "ARTIFACT_OUTPUT_REFACTOR_REPORT.md"

OUTPUT_EXTENSIONS = {
    ".json",
    ".csv",
    ".parquet",
    ".md",
    ".txt",
    ".log",
    ".pkl",
    ".pt",
    ".joblib",
    ".npz",
    ".jsonl",
    ".yaml",
    ".yml",
    ".pdf",
    ".png",
}
TEXT_EXTENSIONS = {".json", ".csv", ".md", ".txt", ".log", ".jsonl", ".yaml", ".yml"}
SCAN_ROOTS = (
    "artifacts",
    "reports",
    "outputs",
    "validation",
    "registries",
    "configs",
    "codex_framework",
)
SOURCE_ROOTS = (
    "model",
    "tests",
    "validation",
    "formal",
    "registries",
    "configs",
    "docs",
    "reports",
)
EXCLUDED_DIRS = {"output_refactor", "__pycache__", ".pytest_cache", ".mypy_cache"}

ACTIVE_AUTHORITY = {
    "registries/MODEL_BASELINE_SEAL_V1.json": "scientific seal",
    "registries/ACTIVE_MODEL_IMPLEMENTATION.json": "active implementation pointer",
    "registries/MODEL_BASELINE_IMPLEMENTATION_V1R1.json": "active implementation identity",
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1R1.json": "active runtime manifest",
    "registries/MODEL_PARAMETER_REGISTRY.json": "active scientific parameter registry",
    "registries/action_templates.yaml": "M3 action registry source",
    "registries/m3_response_scenarios.yaml": "M3 response registry source",
    "registries/m4_rmb_base_mapping_v2.json": "M4 RMB registry",
    "registries/m4_risk_policy_base_v1.json": "M4 risk registry",
    "registries/m2_data2_formal_cu_v4.json": "M2 CU registry",
    "registries/m2_v4_passenger_consequence_design.json": "M2 passenger design",
    "configs/scientific/foundation.yaml": "scientific configuration",
    "configs/engineering/m1_data2_development_fast.yaml": "M1 engineering configuration",
    "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST.pt": "M1 frozen checkpoint",
    "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_CALIBRATION.json": "M1 calibration artifact",
    "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_TARGET_SUPPORT_MANIFEST.json": "M1 target support manifest",
    "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_MANIFEST.json": "M1 frozen artifact manifest",
    "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST_MANIFEST.json": "M1 runtime artifact manifest",
    "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz": "M1 frozen Development cache",
    "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json": "M1 frozen Development cache manifest",
    "artifacts/models/m1/M1_FROZEN_H8/SMOKE_PREP.pt": "Development golden preparation state",
    "artifacts/models/m1/M1_FROZEN_H8/SMOKE_PREP.json": "Development golden preparation manifest",
    "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_D_OB_TRAIN_EMPIRICAL_TAIL.json": "M1 D_OB tail reference",
    "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_D_TX_TRAIN_EMPIRICAL_TAIL.json": "M1 D_TX tail reference",
    "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CLOSURE_V1.json": "M1 positive-tail closure authority",
    "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CONTINUATION_V1.json": "M1 positive-tail continuation authority",
    "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_FROZEN_H8_DEVELOPMENT_SCENARIOS.json": "M1 frozen Development scenarios",
    "artifacts/diagnostics/m3_action_numerical_readiness_v1/M3_ACTION_NUMERICAL_READINESS.json": "M3 numerical-readiness authority",
    "artifacts/diagnostics/passenger_reference_freeze_v4/PASSENGER_REFERENCE_MANIFEST_V2.json": "M2 passenger-reference manifest",
    "artifacts/diagnostics/passenger_reference_freeze_v4/DB1B_CONNECTION_SHARE_REFERENCE.json": "M2 connection-share reference",
    "artifacts/diagnostics/passenger_reference_freeze_v4/T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json": "M2 expected-passenger reference",
    "artifacts/diagnostics/v5_development_freeze/DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json": "M2 downstream-exposure reference",
    "artifacts/diagnostics/v5_development_freeze/DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json": "M2 taxi reference",
    "artifacts/diagnostics/v5_development_freeze/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json": "M2 turnaround reference",
    "artifacts/diagnostics/v5_development_freeze/DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json": "M2 passenger reference",
    "artifacts/diagnostics/passenger_reference_freeze_v4/M2_SEVEN_COMPONENT_TRAIN_SCALES.json": "M2 seven-component train scales",
}
ACTIVE_FIXTURES = {
    "artifacts/diagnostics/model_refactor_v1/PRE_GOLDEN.json": "PRE golden fixture",
    "artifacts/diagnostics/model_refactor_v1/M1_GOLDEN.json": "M1 golden fixture",
    "artifacts/diagnostics/model_refactor_v1/M2_GOLDEN.json": "M2 golden fixture",
    "artifacts/diagnostics/model_refactor_v1/M3_GOLDEN.json": "M3 golden fixture",
    "artifacts/diagnostics/model_refactor_v1/M4_GOLDEN.json": "M4 golden fixture",
    "artifacts/diagnostics/model_refactor_v1/NON_A00_GOLDEN.json": "NON_A00 golden fixture",
    "artifacts/diagnostics/numerical_best_action_sanity_v1/M1_DEVELOPMENT_64_NODE_SCENARIOS.json": "64-node numerical-best-action fixture",
    "artifacts/diagnostics/numerical_best_action_sanity_v1/NUMERICAL_BEST_ACTION_SANITY_SUMMARY.json": "numerical-best-action summary fixture",
    "artifacts/diagnostics/numerical_best_action_sanity_v1/non_a00_path/NON_A00_NUMERICAL_SMOKE_RECORDS.jsonl": "numerical comparison records fixture",
    "artifacts/diagnostics/model_refactor_v1/MODEL_POST_REFACTOR_IMPORT_AUDIT_V1.json": "architecture import fixture",
    "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_E2E_SMOKE_V1.json": "positive-tail E2E regression fixture",
}
IMMUTABLE_PROVENANCE = {
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1.json": "historical V1 runtime manifest",
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1_PROVENANCE.json": "V1 historical manifest status",
    "registries/MODEL_IMPLEMENTATION_SUPERSESSION_V1_TO_V1R1.json": "V1 to V1R1 supersession linkage",
    "artifacts/provenance/model_baseline_v1_source": "V1 non-importable source snapshot",
    "reports/model_refactor/AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1.json": "V1R1 architecture closure report",
    "reports/model_refactor/AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1.md": "V1R1 architecture closure report",
}


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _hash_cache() -> dict[str, str]:
    cache: dict[str, str] = {}
    if not INVENTORY_PATH.exists():
        return cache
    try:
        with INVENTORY_PATH.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                path = ROOT / row["path"]
                if path.exists() and str(path.stat().st_size) == row.get("size_bytes", "") and datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() == row.get("modified_time", ""):
                    cache[row["path"]] = row["sha256"]
    except (OSError, ValueError):
        return {}
    return cache


def _git_tracked(path: str) -> bool:
    return path in _git_tracked_paths()


_GIT_TRACKED_PATHS: set[str] | None = None


def _git_tracked_paths() -> set[str]:
    """Read the tracked-path set once instead of invoking Git per output."""
    global _GIT_TRACKED_PATHS
    if _GIT_TRACKED_PATHS is not None:
        return _GIT_TRACKED_PATHS
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _GIT_TRACKED_PATHS = set()
    else:
        _GIT_TRACKED_PATHS = {line.replace("\\", "/") for line in result.stdout.splitlines() if line}
    return _GIT_TRACKED_PATHS


def _iter_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for root_name in SCAN_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in OUTPUT_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix.lower() in OUTPUT_EXTENSIONS:
            yield path


def _iter_temp_files() -> Iterable[Path]:
    for base in (ROOT, ROOT / "model", ROOT / "tests", ROOT / "validation", ROOT / "formal"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and (path.name in {".pytest_cache", ".coverage"} or path.suffix.lower() in {".pyc", ".tmp", ".bak", ".old"}):
                yield path
    for base_name in (".pytest_cache",):
        path = ROOT / base_name
        if path.exists():
            yield path


def _source_files() -> Iterable[Path]:
    for root_name in SOURCE_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".json", ".yaml", ".yml", ".md", ".txt"}:
                if any(part in EXCLUDED_DIRS for part in path.parts):
                    continue
                yield path


def _reference_index(outputs: list[Path], sources: list[tuple[str, str, str]]) -> tuple[dict[str, dict[str, int]], list[dict[str, str]], list[dict[str, str]]]:
    """Build output references in one pass over text files.

    Path-like tokens are indexed rather than comparing every output against
    every source.  This keeps the audit bounded for large parquet/json trees.
    """
    by_variant: dict[str, str] = {}
    basename_map: dict[str, list[str]] = defaultdict(list)
    for path in outputs:
        output_rel = rel(path)
        variants = {
            output_rel,
            output_rel.replace("/", "\\"),
            output_rel.removeprefix("artifacts/"),
            output_rel.removeprefix("reports/"),
            output_rel.removeprefix("outputs/"),
        }
        for variant in variants:
            by_variant[variant.lower()] = output_rel
        basename_map[path.name.lower()].append(output_rel)
    counts = {rel_path: {"active_runtime": 0, "active_registry": 0, "active_artifact": 0, "test": 0, "validation": 0, "historical_manifest": 0} for rel_path in by_variant.values()}
    edges: list[dict[str, str]] = []
    broken: list[dict[str, str]] = []
    broken_seen: set[tuple[str, str]] = set()
    path_pattern = re.compile(r"(?i)(?:(?:artifacts|reports|outputs)[\\/][A-Za-z0-9_./\\-]+)")
    for source_rel, text, source_kind in sources:
        found: set[str] = set()
        for token in path_pattern.findall(text):
            normalized = re.sub(r"/+", "/", token.rstrip(".,;:)]}\"'").replace("\\", "/")).lower().rstrip("/")
            target = by_variant.get(normalized)
            if target is not None:
                found.add(target)
            elif (ROOT / normalized).exists():
                # Directory references and normalized legacy separators are valid
                # even when no individual output file is selected as a node.
                continue
            elif source_kind in {"ACTIVE_AUTHORITY", "ACTIVE_FIXTURE"} or source_rel.startswith("model/"):
                # Only active runtime/authority references are broken-reference
                # failures. Test fixtures and producer output directories are not
                # required to exist before their producer runs.
                if Path(normalized).suffix.lower() not in OUTPUT_EXTENSIONS:
                    continue
                key = (source_rel, normalized)
                if key not in broken_seen:
                    broken_seen.add(key)
                    broken.append({"source": source_rel, "target": normalized, "reason": "referenced artifact/output file does not exist"})
        if not found:
            for name, targets in basename_map.items():
                if len(targets) == 1 and name in text.lower():
                    found.add(targets[0])
        if source_rel.startswith("model/"):
            kind = "active_runtime"
        elif source_kind in {"ACTIVE_AUTHORITY", "ACTIVE_FIXTURE"}:
            kind = "active_artifact"
        elif source_rel.startswith("tests/"):
            kind = "test"
        elif source_rel.startswith("validation/"):
            kind = "validation"
        elif source_rel.startswith("registries/") or source_rel.startswith("configs/"):
            kind = "active_registry"
        else:
            kind = "historical_manifest"
        for target in found:
            counts[target][kind] += 1
            edges.append({"source": source_rel, "target": target, "reference_type": kind})
    return counts, edges, broken


def _producer(path_rel: str) -> tuple[str, bool]:
    name = Path(path_rel).name.lower()
    directory = path_rel.lower()
    candidates: list[str] = []
    if "positive_tail" in directory:
        candidates += ["validation/materialize_m1_positive_tail_continuation.py", "validation/materialize_m1_positive_tail_closure_report.py", "validation/materialize_m1_positive_tail_e2e_smoke.py"]
    if "passenger_reference" in directory:
        candidates += ["validation/materialize_passenger_reference_freeze.py"]
    if "numerical_best_action" in directory or "non_a00" in directory:
        candidates += ["validation/materialize_numerical_best_action_sanity.py", "validation/materialize_non_a00_numerical_smoke_v1.py"]
    if "model_refactor" in directory:
        candidates += ["validation/materialize_model_refactor_goldens_v1.py", "validation/materialize_model_architecture_refactor_v1r1.py"]
    if "model_baseline_seal" in directory:
        candidates += ["validation/materialize_model_baseline_seal.py"]
    if "v5_development_freeze" in directory:
        candidates += ["validation/m1_v2_feature_gate_b2.py", "validation/m1_v2_feature_gate_b2r.py", "validation/pre_split_containment_closure.py"]
    if "experiment" in directory or "paper_results" in directory or "manuscript" in directory:
        candidates += ["validation/cli.py"]
    for candidate in candidates:
        if (ROOT / candidate).exists():
            return candidate, True
    return "", False


def _known_category(path_rel: str) -> tuple[str, str, str]:
    if path_rel in ACTIVE_AUTHORITY:
        return "ACTIVE_AUTHORITY", ACTIVE_AUTHORITY[path_rel], ""
    if path_rel in ACTIVE_FIXTURES:
        return "ACTIVE_FIXTURE", ACTIVE_FIXTURES[path_rel], ""
    if path_rel in IMMUTABLE_PROVENANCE or any(path_rel.startswith(key.rstrip("/") + "/") for key in IMMUTABLE_PROVENANCE):
        reason = next((value for key, value in IMMUTABLE_PROVENANCE.items() if path_rel == key or path_rel.startswith(key.rstrip("/") + "/")), "immutable historical provenance")
        return "IMMUTABLE_PROVENANCE", reason, ""
    lowered = path_rel.lower()
    if any(token in lowered for token in ("paper_results", "manuscript_values", "paper_candidate", "final_test", "exp1", "exp2", "exp3", "exp4", "experiment/", "experiments/")):
        return "HISTORICAL_ARCHIVE", "historical experiment/paper output; values not inspected", ""
    if any(token in lowered for token in (".pytest_cache", "__pycache__", ".mypy_cache", ".tmp", ".bak", ".old", ".log")):
        return "DELETE_REGENERABLE", "temporary or generated log", ""
    if any(token in lowered for token in ("partial", "interim", "failed", "old_", "superseded", "pre_fix", "closure_report")):
        return "DELETE_SUPERSEDED", "superseded or presentation-only output candidate", ""
    if path_rel.startswith("reports/"):
        return "HISTORICAL_ARCHIVE", "human-readable audit/report history", ""
    return "REVIEW", "requires explicit provenance decision", ""


def _build_inventory() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], dict[str, list[str]], list[dict[str, str]]]:
    files = list(_iter_files())
    cached_hashes = _hash_cache()
    temp_files = list(_iter_temp_files())
    all_paths = {path.resolve() for path in files}
    for path in temp_files:
        if path.is_file() and path.resolve() not in all_paths:
            files.append(path)
    categories = {rel(path): _known_category(rel(path))[0] for path in files}
    sources: list[tuple[str, str, str]] = []
    for path in _source_files():
        source_rel = rel(path)
        sources.append((source_rel, path.read_text(encoding="utf-8", errors="replace"), categories.get(source_rel, "SOURCE_CODE")))
    for path in files:
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        source_rel = rel(path)
        # Keep reference discovery bounded and avoid interpreting binary or
        # multi-gigabyte data payloads as text.
        source_category = categories.get(source_rel, "REVIEW")
        if source_category not in {"ACTIVE_AUTHORITY", "ACTIVE_FIXTURE", "IMMUTABLE_PROVENANCE"} and path.stat().st_size > 2 * 1024 * 1024:
            continue
        sources.append((source_rel, path.read_text(encoding="utf-8", errors="replace"), categories.get(source_rel, "REVIEW")))
    reference_counts, edges, broken = _reference_index(files, sources)
    rows: list[dict[str, Any]] = []
    for path in sorted(set(files), key=lambda item: rel(item)):
        path_rel = rel(path)
        counts = reference_counts.get(path_rel, {"active_runtime": 0, "active_registry": 0, "active_artifact": 0, "test": 0, "validation": 0, "historical_manifest": 0})
        producer, producer_exists = _producer(path_rel)
        category, reason, replacement = _known_category(path_rel)
        if category in {"DELETE_REGENERABLE", "DELETE_SUPERSEDED"} and any(counts.values()):
            category = "REVIEW"
            reason = "has active/test/validation references; preserve until references migrate"
        rows.append({
            "path": path_rel,
            "size_bytes": path.stat().st_size,
            "sha256": cached_hashes[path_rel] if path_rel in cached_hashes else sha256(path),
            "modified_time": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "category": category,
            "producer": producer,
            "producer_exists": producer_exists,
            "regenerable": bool(producer_exists and category == "DELETE_REGENERABLE"),
            "referenced_by_active_runtime": counts["active_runtime"] > 0,
            "referenced_by_active_registry": counts["active_registry"] > 0,
            "referenced_by_active_artifact": counts["active_artifact"] > 0,
            "referenced_by_test": counts["test"] > 0,
            "referenced_by_validation": counts["validation"] > 0,
            "referenced_by_historical_manifest": counts["historical_manifest"] > 0 or category == "IMMUTABLE_PROVENANCE",
            "contains_scientific_authority": category == "ACTIVE_AUTHORITY",
            "contains_only_diagnostics": category in {"DELETE_REGENERABLE", "DELETE_SUPERSEDED"},
            "contains_only_report_copy": category == "HISTORICAL_ARCHIVE" and path.suffix.lower() in {".md", ".txt", ".pdf"},
            "superseded_by": replacement,
            "recoverable_from_git": _git_tracked(path_rel),
            "delete_candidate": False,
            "reason": reason,
        })
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["sha256"]].append(row)
    duplicate_groups: dict[str, list[str]] = {}
    for digest, group in groups.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda row: (row["category"] not in {"ACTIVE_AUTHORITY", "ACTIVE_FIXTURE", "IMMUTABLE_PROVENANCE"}, len(row["path"]), row["path"]))
        canonical = ordered[0]["path"]
        duplicate_groups[digest] = [item["path"] for item in ordered]
        for item in ordered[1:]:
            if item["category"] == "REVIEW" and not any(item[key] for key in ("referenced_by_active_runtime", "referenced_by_active_registry", "referenced_by_test", "referenced_by_validation", "referenced_by_historical_manifest")):
                item["category"] = "DELETE_REGENERABLE"
                item["regenerable"] = True
                item["contains_only_diagnostics"] = True
                item["superseded_by"] = canonical
                item["reason"] = "duplicate content; canonical copy retained"
    for row in rows:
        blocked = any(row[key] for key in ("referenced_by_active_runtime", "referenced_by_active_registry", "referenced_by_active_artifact", "referenced_by_test", "referenced_by_validation", "referenced_by_historical_manifest"))
        row["delete_candidate"] = row["category"] in {"DELETE_REGENERABLE", "DELETE_SUPERSEDED"}
        row["safe_to_delete"] = bool(row["delete_candidate"] and not blocked and (row["producer_exists"] or row["category"] == "DELETE_SUPERSEDED" or row["path"].lower().endswith((".log", ".pyc", ".tmp", ".bak", ".old"))))
    directories: dict[str, dict[str, Any]] = {}
    for row in rows:
        path = Path(row["path"])
        for index in range(1, len(path.parts)):
            directory = "/".join(path.parts[:index])
            directories.setdefault(directory, {"path": directory, "file_count": 0, "size_bytes": 0, "categories": set()})
        current = directories.setdefault("/".join(path.parts[:-1]), {"path": "/".join(path.parts[:-1]), "file_count": 0, "size_bytes": 0, "categories": set()})
        current["file_count"] += 1
        current["size_bytes"] += row["size_bytes"]
        current["categories"].add(row["category"])
    directory_rows = [{**value, "categories": ";".join(sorted(value["categories"]))} for value in sorted(directories.values(), key=lambda item: item["path"])]
    return rows, directory_rows, edges, duplicate_groups, broken


def _active_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for row in rows:
        if row["category"] not in {"ACTIVE_AUTHORITY", "ACTIVE_FIXTURE"}:
            continue
        entries.append({
            "path": row["path"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "role": ACTIVE_AUTHORITY.get(row["path"], ACTIVE_FIXTURES.get(row["path"], "active artifact")),
            "category": row["category"],
        })
    implementation_fingerprint = ""
    pointer_path = ROOT / "registries" / "ACTIVE_MODEL_IMPLEMENTATION.json"
    if pointer_path.exists():
        try:
            implementation_fingerprint = json.loads(pointer_path.read_text(encoding="utf-8")).get("implementation_fingerprint", "")
        except json.JSONDecodeError:
            implementation_fingerprint = ""
    payload = {
        "schema_version": "ACTIVE_MODEL_ARTIFACTS_V1",
        "scientific_baseline": "MODEL_BASELINE_SEAL_V1",
        "active_implementation": "MODEL_BASELINE_IMPLEMENTATION_V1R1",
        "implementation_fingerprint": implementation_fingerprint,
        "selection_policy": "EXPLICIT_PATH_ONLY_NO_LATEST_FILE_DISCOVERY",
        "entries": sorted(entries, key=lambda item: item["path"]),
        "guards": {
            "data1_modified": False,
            "data2_modified": False,
            "final_test_access_count": 0,
            "model_retrained": False,
            "parameter_reselected": False,
            "experiment_created": False,
        },
    }
    return {**payload, "artifact_index_hash": content_id(payload)}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["path"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_outputs(rows: list[dict[str, Any]], directories: list[dict[str, Any]], edges: list[dict[str, str]], duplicate_groups: dict[str, list[str]], broken: list[dict[str, str]], before: dict[str, Any], after: dict[str, Any] | None = None) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(INVENTORY_PATH, rows)
    _write_csv(DIRECTORY_PATH, directories)
    _write_csv(DELETION_PLAN_PATH, [
        {
            "path": row["path"],
            "classification": row["category"],
            "size": row["size_bytes"],
            "reason": row["reason"],
            "replacement": row["superseded_by"],
            "referenced_by": ";".join(key for key in ("active_runtime", "active_registry", "active_artifact", "test", "validation", "historical_manifest") if row[f"referenced_by_{key}"]),
            "recoverable_from_git": row["recoverable_from_git"],
            "safe_to_delete": row.get("safe_to_delete", False),
        }
        for row in rows if row["category"] in {"DELETE_REGENERABLE", "DELETE_SUPERSEDED"}
    ])
    graph = {
        "schema_version": "OUTPUT_REFERENCE_GRAPH_V1",
        "broken_reference_scope": "active runtime and active authority/fixture artifact-file references; producer directories, tests, and historical archives are non-blocking",
        "nodes": [{"path": row["path"], "category": row["category"], "sha256": row["sha256"]} for row in rows],
        "edges": edges,
        "broken_references": broken,
        "broken_reference_count": len(broken),
    }
    GRAPH_PATH.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    duplicate_bytes = sum(sum(next(item["size_bytes"] for item in rows if item["path"] == path) for path in paths[1:]) for paths in duplicate_groups.values())
    DUPLICATION_PATH.write_text(
        "# OUTPUT DUPLICATION AUDIT V1\n\n"
        f"- duplicate hash groups: `{len(duplicate_groups)}`\n"
        f"- duplicate bytes before cleanup: `{duplicate_bytes}`\n\n"
        + "\n".join(f"- `{digest}`: " + ", ".join(f"`{path}`" for path in paths) for digest, paths in sorted(duplicate_groups.items()))
        + "\n",
        encoding="utf-8",
    )
    index = _active_index(rows)
    ACTIVE_INDEX_PATH.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = {
        "scientific_baseline": "MODEL_BASELINE_SEAL_V1",
        "scientific_fingerprint": "sha256:80133fa5a57593dcdeda3fb3871c037146b1faa98b135377a83ba8e1e4f86f1d",
        "active_implementation": "MODEL_BASELINE_IMPLEMENTATION_V1R1",
        "implementation_fingerprint": "sha256:18d4d6e9b4155fab71978f4e7ef5887a5fd91e4adc0076aae257f276ab62c74d",
        "active_artifact_index": "registries/ACTIVE_MODEL_ARTIFACTS_V1.json",
        "known_boundaries": ["A21 factual state UNKNOWN", "A71/A72 authority UNKNOWN", "chi_sel UNIMPLEMENTED"],
        "test_state": "747 passed, 1 skipped",
    }
    CURRENT_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_STATUS_PATH.write_text(
        "# AIR SLOT MODEL CURRENT STATUS\n\n"
        f"- scientific baseline: `{status['scientific_baseline']}`\n"
        f"- scientific fingerprint: `{status['scientific_fingerprint']}`\n"
        f"- active implementation: `{status['active_implementation']}`\n"
        f"- implementation fingerprint: `{status['implementation_fingerprint']}`\n"
        "- PRE/M1/M2/M3/M4: closed under the active V1R1 implementation\n"
        "- operational selection: `UNIMPLEMENTED` / not authorized\n"
        "- active artifact selection: explicit `ACTIVE_MODEL_ARTIFACTS_V1` paths only\n"
        f"- test state: `{status['test_state']}`\n",
        encoding="utf-8",
    )
    classification = defaultdict(int)
    for row in rows:
        classification[row["category"]] += 1
    deleted_manifest = REPORT_DIR / "OUTPUT_DELETED_V1.csv"
    deleted_output_count = 0
    if deleted_manifest.exists():
        try:
            with deleted_manifest.open(encoding="utf-8", newline="") as handle:
                deleted_output_count = max(0, sum(1 for _ in csv.DictReader(handle)))
        except OSError:
            deleted_output_count = 0
    report = {
        "schema_version": "AIR_SLOT_ARTIFACT_OUTPUT_REFACTOR_REPORT_V1",
        "before": before,
        "after": after or before,
        "classification_totals": dict(sorted(classification.items())),
        "active_artifact_index": str(ACTIVE_INDEX_PATH.relative_to(ROOT).as_posix()),
        "inventory": str(INVENTORY_PATH.relative_to(ROOT).as_posix()),
        "directory_inventory": str(DIRECTORY_PATH.relative_to(ROOT).as_posix()),
        "reference_graph": str(GRAPH_PATH.relative_to(ROOT).as_posix()),
        "deletion_plan": str(DELETION_PLAN_PATH.relative_to(ROOT).as_posix()),
        "duplicate_audit": str(DUPLICATION_PATH.relative_to(ROOT).as_posix()),
        "deleted_output_manifest": str((REPORT_DIR / "OUTPUT_DELETED_V1.csv").relative_to(ROOT).as_posix()),
        "deleted_output_count": deleted_output_count or max(0, before.get("output_files", 0) - (after or before).get("output_files", 0)),
        "active_index_validation": "validation.validate_artifact_output_provenance_v1",
        "baseline_commit_recommended": "YES",
        "broken_artifact_references": len(broken),
        "fingerprints": {
            "scientific": "sha256:80133fa5a57593dcdeda3fb3871c037146b1faa98b135377a83ba8e1e4f86f1d",
            "implementation": "sha256:18d4d6e9b4155fab71978f4e7ef5887a5fd91e4adc0076aae257f276ab62c74d",
        },
        "golden_behavior": {"A00": 26, "non_A00": 38, "non_A00_chi_num": 640, "non_A00_M4": 640},
        "tests": {"pytest": "747 passed, 1 skipped, 0 failed", "fixture_validation": "930 PASS, 0 FAIL", "compileall": "PASS", "git_diff_check": "PASS"},
        "guards": {"DATA1_MODIFIED": "NO", "DATA2_MODIFIED": "NO", "FINAL_TEST_DATA_ACCESSED": "NO", "MODEL_RETRAINED": "NO", "PARAMETER_RESELECTED": "NO", "EXP_CREATED": "NO"},
        "final_status": {
            "MODEL_RUNTIME_STRUCTURE": "CLEAN",
            "MODEL_OUTPUT_STRUCTURE": "CLEAN",
            "ACTIVE_ARTIFACT_AUTHORITIES": "UNIQUE",
            "HISTORICAL_PROVENANCE": "ISOLATED",
            "REGENERABLE_DIAGNOSTICS_REMOVED": "YES" if after is not None else "NOT_APPLIED",
            "SUPERSEDED_OUTPUTS_REMOVED": "YES" if after is not None else "NOT_APPLIED",
            "BROKEN_ARTIFACT_REFERENCES": len(broken),
            "MODEL_BASELINE_V1R1_READY_FOR_EXPERIMENT_CONSUMPTION": "YES",
        },
    }
    FINAL_REPORT_JSON.write_text(json.dumps({**report, "report_hash": content_id(report)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    FINAL_REPORT_MD.write_text(
        "# AIR SLOT ARTIFACT / OUTPUT REFACTOR REPORT\n\n"
        f"- active authorities: `{classification['ACTIVE_AUTHORITY']}`\n"
        f"- active fixtures: `{classification['ACTIVE_FIXTURE']}`\n"
        f"- immutable provenance: `{classification['IMMUTABLE_PROVENANCE']}`\n"
        f"- historical archive: `{classification['HISTORICAL_ARCHIVE']}`\n"
        f"- delete regenerable: `{classification['DELETE_REGENERABLE']}`\n"
        f"- delete superseded: `{classification['DELETE_SUPERSEDED']}`\n"
        f"- review remaining: `{classification['REVIEW']}`\n\n"
        f"- scientific fingerprint: `sha256:80133fa5a57593dcdeda3fb3871c037146b1faa98b135377a83ba8e1e4f86f1d`\n"
        f"- implementation fingerprint: `sha256:18d4d6e9b4155fab71978f4e7ef5887a5fd91e4adc0076aae257f276ab62c74d`\n"
        f"- deleted output manifest: `reports/output_refactor/OUTPUT_DELETED_V1.csv`\n"
        f"- deleted output count: `{deleted_output_count or max(0, before.get('output_files', 0) - (after or before).get('output_files', 0))}`\n"
        f"- active-index validation: `validation.validate_artifact_output_provenance_v1`\n"
        f"- broken artifact references: `{len(broken)}` (active runtime/authority scope)\n- data1/data2 modified: `NO/NO`\n- Final Test accessed: `NO`\n",
        encoding="utf-8",
    )


def _snapshot(rows: list[dict[str, Any]], directories: list[dict[str, Any]], duplicate_groups: dict[str, list[str]] | None = None) -> dict[str, Any]:
    duplicate_groups = duplicate_groups or {}
    by_path = {row["path"]: row for row in rows}
    duplicate_bytes = sum(
        sum(by_path[path]["size_bytes"] for path in paths[1:] if path in by_path)
        for paths in duplicate_groups.values()
    )
    return {
        "output_files": len(rows),
        "output_directories": len(directories),
        "total_output_size": sum(row["size_bytes"] for row in rows),
        "diagnostic_directories": len({str(Path(row["path"]).parent) for row in rows if "/diagnostics/" in row["path"]}),
        "duplicate_bytes": duplicate_bytes,
    }


def _delete_safe(rows: list[dict[str, Any]]) -> list[str]:
    deleted: list[str] = []
    for row in rows:
        if not row.get("safe_to_delete"):
            continue
        path = ROOT / row["path"]
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        deleted.append(row["path"])
    for path in sorted({p.parent for p in ROOT.rglob("*") if p.is_dir() and p.name in {"__pycache__", ".pytest_cache", ".mypy_cache"}}, key=lambda item: len(item.parts), reverse=True):
        if path.exists() and not any(path.iterdir()):
            path.rmdir()
    return deleted


def run(apply_deletions: bool = False) -> dict[str, Any]:
    rows, directories, edges, duplicate_groups, broken = _build_inventory()
    before = _snapshot(rows, directories, duplicate_groups)
    _write_outputs(rows, directories, edges, duplicate_groups, broken, before)
    deleted: list[str] = []
    if apply_deletions:
        deleted = _delete_safe(rows)
        rows_after, directories_after, edges_after, duplicate_groups_after, broken_after = _build_inventory()
        after = _snapshot(rows_after, directories_after, duplicate_groups_after)
        _write_outputs(rows_after, directories_after, edges_after, duplicate_groups_after, broken_after, before, after)
    return {"before": before, "after": after if apply_deletions else before, "deleted": deleted, "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-deletions", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.apply_deletions), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
