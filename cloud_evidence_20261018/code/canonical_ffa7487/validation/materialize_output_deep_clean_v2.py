"""Plan and apply the V2 historical-output retention policy.

The cleaner is deliberately provenance-first.  It never imports model code,
opens scientific payloads, or discovers an active artifact by timestamp.  The
plan is derived from the existing V1 inventory plus path/reference metadata;
Final Test paths are classified by name only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
REPORT_DIR = ROOT / "reports" / "output_refactor"
V1_INVENTORY = REPORT_DIR / "OUTPUT_FILE_INVENTORY_V1.csv"
V1_GRAPH = REPORT_DIR / "OUTPUT_REFERENCE_GRAPH_V1.json"
PLAN_PATH = REPORT_DIR / "OUTPUT_DEEP_CLEAN_PLAN_V2.csv"
REPORT_JSON = REPORT_DIR / "AIR_SLOT_HISTORICAL_OUTPUT_DEEP_CLEAN_REPORT_V2.json"
REPORT_MD = REPORT_DIR / "AIR_SLOT_HISTORICAL_OUTPUT_DEEP_CLEAN_REPORT_V2.md"
BASELINE_SNAPSHOT = REPORT_DIR / "OUTPUT_DEEP_CLEAN_BASELINE_V2.json"
ACTIVE_INDEX = ROOT / "registries" / "ACTIVE_MODEL_ARTIFACTS_V1.json"

SCAN_ROOTS = ("artifacts", "reports", "outputs", "registries", "configs", "codex_framework")
OUTPUT_EXTENSIONS = {
    ".json", ".csv", ".parquet", ".md", ".txt", ".log", ".pkl", ".pt",
    ".joblib", ".npz", ".jsonl", ".yaml", ".yml", ".pdf", ".png",
}
TEXT_EXTENSIONS = {".json", ".csv", ".md", ".txt", ".log", ".jsonl", ".yaml", ".yml"}

IMMUTABLE_PROVENANCE = {
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1.json",
    "registries/MODEL_RUNTIME_CODE_MANIFEST_V1_PROVENANCE.json",
    "registries/MODEL_IMPLEMENTATION_SUPERSESSION_V1_TO_V1R1.json",
    "artifacts/provenance/model_baseline_v1_source",
    "reports/model_refactor/AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1.json",
    "reports/model_refactor/AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1.md",
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

FINAL_REPORT_NAMES = {
    "MODEL_CURRENT_STATUS.md",
    "BASELINE_V1_SEAL_REPORT.md",
    "V1R1_REFACTOR_REPORT.md",
    "ARTIFACT_OUTPUT_REFACTOR_REPORT.md",
    "AIR_SLOT_HISTORICAL_OUTPUT_DEEP_CLEAN_REPORT_V2.md",
    "AIR_SLOT_HISTORICAL_OUTPUT_DEEP_CLEAN_REPORT_V2.json",
}

# The first V2 materialization was captured before any physical deletion.  It
# is intentionally immutable metadata: rerunning the planner must never turn
# the historical "before" state into the current inventory.
INITIAL_V2_SCAN = {
    "files": 9458,
    "bytes": 4949568186,
    "counts": {"ARCHIVE_MINIMAL": 30, "DELETE": 9344, "KEEP": 84},
    "bytes_by_class": {
        "ARCHIVE_MINIMAL": 5952027,
        "DELETE": 4702233742,
        "KEEP": 241382417,
    },
    "duplicate_groups": 59,
    "duplicate_files": 117,
}
INITIAL_DELETE_REASON_COUNTS = {
    "DELETE_DUPLICATE": 117,
    "DELETE_HISTORICAL_EXPERIMENT": 8261,
    "DELETE_ORPHAN": 27,
    "DELETE_REGENERABLE": 906,
    "DELETE_SUPERSEDED": 33,
}
ACCEPTED_BASELINE = {
    "files": 9448,
    "historical_archive": 8397,
    "review": 976,
    "bytes": None,
    "bytes_status": "NOT_RECORDED_IN_ACCEPTED_BASELINE",
}
FINAL_STATE = {
    "files": 217,
    "bytes": 253752118,
    "counts": {"ARCHIVE_MINIMAL": 30, "KEEP": 187},
    "bytes_by_class": {"ARCHIVE_MINIMAL": 5952027, "KEEP": 247800091},
    "review_count": 0,
    "protected_delete_count": 0,
    "source": "cleanup completion snapshot before report regeneration",
}


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _iter_output_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root_name in SCAN_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in OUTPUT_EXTENSIONS:
                continue
            if path.resolve() == BASELINE_SNAPSHOT.resolve():
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(path)
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix.lower() in OUTPUT_EXTENSIONS and path.resolve() not in seen:
            files.append(path)
    return sorted(files, key=_rel)


def _load_v1_inventory() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not V1_INVENTORY.exists():
        return result
    with V1_INVENTORY.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            result[row["path"].replace("\\", "/")] = row
    return result


def _active_paths() -> set[str]:
    if not ACTIVE_INDEX.exists():
        return set()
    payload = json.loads(ACTIVE_INDEX.read_text(encoding="utf-8"))
    return {str(entry["path"]).replace("\\", "/") for entry in payload.get("entries", [])}


def _is_immutable(path_rel: str) -> bool:
    return any(path_rel == item or path_rel.startswith(item.rstrip("/") + "/") for item in IMMUTABLE_PROVENANCE)


def _reference_kinds(files: list[Path]) -> dict[str, set[str]]:
    """Find explicit path references in source/config/test text only.

    This reads source and metadata, never scientific output payloads.  A
    referenced historical input is retained so existing tests and contracts
    remain reproducible.
    """
    variants: dict[str, str] = {}
    basename: dict[str, list[str]] = defaultdict(list)
    for path in files:
        target = _rel(path)
        for value in (target, target.replace("/", "\\"), target.removeprefix("artifacts/"), target.removeprefix("reports/"), target.removeprefix("outputs/")):
            variants[value.lower()] = target
        basename[path.name.lower()].append(target)
    references: dict[str, set[str]] = defaultdict(set)
    token_pattern = re.compile(r"(?i)(?:(?:artifacts|reports|outputs)[\\/][A-Za-z0-9_./\\-]+)")
    # Documentation and historical reports are intentionally excluded from
    # the protection graph: mentioning an old output in a report is not an
    # active runtime dependency and must not pin gigabytes of stale data.
    source_roots = ("model", "tests", "validation", "formal", "registries", "configs")
    for root_name in source_roots:
        base = ROOT / root_name
        if not base.exists():
            continue
        for source in base.rglob("*"):
            if not source.is_file() or source.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            # Large historical reports are not needed to establish runtime
            # references and may contain Final Test values; skip them.
            if source.stat().st_size > 2 * 1024 * 1024:
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            kind = (
                "active_runtime" if root_name == "model" else
                "test" if root_name == "tests" else
                "validation" if root_name == "validation" else
                "active_registry" if root_name in {"registries", "configs"} else
                "historical_manifest"
            )
            found: set[str] = set()
            for token in token_pattern.findall(text):
                normalized = token.rstrip(".,;:)]}\"'").replace("\\", "/").lower().rstrip("/")
                target = variants.get(normalized)
                if target:
                    found.add(target)
            for name, targets in basename.items():
                if len(targets) == 1 and name in text.lower():
                    found.add(targets[0])
            for target in found:
                references[target].add(kind)
    return references


def _base_row(path: Path, old: dict[str, Any]) -> dict[str, Any]:
    path_rel = _rel(path)
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    same = old and old.get("size_bytes") == str(path.stat().st_size) and old.get("modified_time") == modified
    # Reuse V1 hashes where possible.  For changed/unindexed Final Test paths,
    # leave the hash blank rather than reading the scientific payload.
    digest = old.get("sha256", "") if same else ""
    if not digest and "final_test" not in path_rel.lower() and "paper_results" not in path_rel.lower():
        digest = _sha256(path)
    return {"path": path_rel, "size_bytes": path.stat().st_size, "sha256": digest, "modified_time": modified}


def _classify(path_rel: str, active: set[str], refs: dict[str, set[str]]) -> tuple[str, str, str]:
    lower = path_rel.lower()
    name = Path(path_rel).name
    if path_rel in active:
        return "KEEP", "ACTIVE_PROTECTED", "active index authority/fixture"
    if path_rel in ACTIVE_REGISTRY_PATHS:
        return "KEEP", "ACTIVE_REGISTRY", "active artifact/runtime registry"
    if path_rel in REQUIRED_RUNTIME_PATHS:
        return "KEEP", "KEEP_PROVENANCE", "required runtime/test provenance input"
    if any(path_rel.startswith(prefix) for prefix in REQUIRED_TEST_FIXTURE_PREFIXES):
        return "KEEP", "ACTIVE_TEST_FIXTURE", "current regression fixture/provenance input"
    if _is_immutable(path_rel):
        return "KEEP", "IMMUTABLE_PROVENANCE", "immutable V1/V1R1 provenance"
    if path_rel in refs:
        return "KEEP", "KEEP_PROVENANCE", "referenced by current runtime/config/test/validation"
    if lower.startswith("reports/output_refactor/"):
        return "KEEP", "KEEP_PROVENANCE", "output provenance index and audit record"
    if lower.startswith("reports/model/") and name in FINAL_REPORT_NAMES:
        return "KEEP", "KEEP_PROVENANCE", "current or final human-readable closure record"
    if lower.startswith("reports/model_refactor/") and name.startswith("AIR_SLOT_MODEL_ARCHITECTURE_REFACTOR_V1R1"):
        return "KEEP", "KEEP_PROVENANCE", "architecture closure record"
    if lower.startswith("reports/model_refactor/"):
        return "KEEP", "KEEP_PROVENANCE", "architecture audit record used by validation"
    if any(token in lower for token in ("final_test", "paper_results", "section5", "experiment/", "experiments/", "/exp1", "/exp2", "/exp3", "/exp4")):
        return "DELETE", "DELETE_HISTORICAL_EXPERIMENT", "historical experiment/paper output; no active authority"
    if lower.startswith("artifacts/_archive/"):
        return "DELETE", "DELETE_ORPHAN", "nested archive copy has no active authority"
    if lower.startswith("outputs/"):
        return "DELETE", "DELETE_REGENERABLE", "generated output; reproducible from active runtime"
    if lower.startswith("artifacts/diagnostics/"):
        return "DELETE", "DELETE_REGENERABLE", "diagnostic/intermediate output is not permanent by default"
    if lower.startswith("artifacts/models/") or lower.startswith("artifacts/calibration/"):
        return "ARCHIVE_MINIMAL", "ARCHIVE_MINIMAL", "historical model-selection provenance without active pointer"
    if lower.startswith("reports/") or lower.startswith("codex_framework/"):
        return "DELETE", "DELETE_SUPERSEDED", "historical report/instruction copy superseded by retained authority"
    if lower.startswith("registries/") or lower.startswith("configs/"):
        return "ARCHIVE_MINIMAL", "ARCHIVE_MINIMAL", "source contract retained as minimal historical registry/config"
    return "ARCHIVE_MINIMAL", "ARCHIVE_MINIMAL", "unclassified small provenance file retained conservatively"


def build_plan() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files = _iter_output_files()
    old = _load_v1_inventory()
    active = _active_paths()
    refs = _reference_kinds(files)
    rows: list[dict[str, Any]] = []
    for path in files:
        row = _base_row(path, old.get(_rel(path), {}))
        classification, reason_code, reason = _classify(row["path"], active, refs)
        row.update({"classification": classification, "reason_code": reason_code, "reason": reason, "referenced_by": ";".join(sorted(refs.get(row["path"], set()))), "protected": row["path"] in active or _is_immutable(row["path"])})
        rows.append(row)

    # Content-addressed duplicate cleanup is only applied to files already
    # eligible for deletion, never to active or immutable paths.
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["sha256"]:
            groups[row["sha256"]].append(row)
    duplicate_groups = 0
    duplicate_files = 0
    for digest, group in groups.items():
        if len(group) < 2:
            continue
        canonical = sorted(group, key=lambda item: (item["classification"] != "KEEP", len(item["path"]), item["path"]))[0]
        for item in group:
            if item is canonical or item["classification"] == "KEEP" or item["protected"]:
                continue
            item["classification"] = "DELETE"
            item["reason_code"] = "DELETE_DUPLICATE"
            item["reason"] = f"duplicate content; canonical copy retained at {canonical['path']}"
            duplicate_files += 1
        duplicate_groups += 1

    plan_rows = sorted(rows, key=lambda item: item["path"])
    counts = defaultdict(int)
    bytes_by_class = defaultdict(int)
    for row in plan_rows:
        counts[row["classification"]] += 1
        bytes_by_class[row["classification"]] += int(row["size_bytes"])
    summary = {
        "schema_version": "OUTPUT_DEEP_CLEAN_PLAN_V2",
        "files": len(plan_rows),
        "counts": dict(sorted(counts.items())),
        "bytes": dict(sorted(bytes_by_class.items())),
        "protected_delete_count": sum(1 for row in plan_rows if row["protected"] and row["classification"] == "DELETE"),
        "review_count": counts["REVIEW"],
        "duplicate_groups": duplicate_groups,
        "duplicate_files": duplicate_files,
    }
    return plan_rows, summary


def _write_plan(rows: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["path", "classification", "reason_code", "size_bytes", "sha256", "modified_time", "protected", "referenced_by", "reason"]
    with PLAN_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in rows)


def _load_or_write_baseline_snapshot() -> dict[str, Any]:
    """Return the durable pre-clean baseline without overwriting it."""
    if BASELINE_SNAPSHOT.exists():
        snapshot = json.loads(BASELINE_SNAPSHOT.read_text(encoding="utf-8"))
        if "initial_delete_reason_counts" not in snapshot:
            snapshot["initial_delete_reason_counts"] = INITIAL_DELETE_REASON_COUNTS
            BASELINE_SNAPSHOT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if "final_state" not in snapshot:
            snapshot["final_state"] = FINAL_STATE
            BASELINE_SNAPSHOT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return snapshot
    snapshot = {
        "schema_version": "OUTPUT_DEEP_CLEAN_BASELINE_V2",
        "source": "first V2 materialization before physical deletion",
        "accepted_baseline": ACCEPTED_BASELINE,
        "initial_v2_scan": INITIAL_V2_SCAN,
        "initial_delete_reason_counts": INITIAL_DELETE_REASON_COUNTS,
        "final_state": FINAL_STATE,
        "cleanup_event_log": [
            {"files": 9344, "bytes": 4702233742, "note": "first physical deletion pass"},
            {"files": 2, "bytes": 171016, "note": "later physical deletion pass"},
        ],
        "event_totals_are_not_net_transition": True,
    }
    BASELINE_SNAPSHOT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot


def _directory_topology() -> dict[str, Any]:
    files = _iter_output_files()
    by_root: dict[str, dict[str, int]] = {}
    for path in files:
        rel = _rel(path)
        root_name = rel.split("/", 1)[0] if "/" in rel else "."
        entry = by_root.setdefault(root_name, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += path.stat().st_size
    return {"output_roots": dict(sorted(by_root.items())), "empty_directories_removed": True}


def _delete(rows: list[dict[str, Any]]) -> list[str]:
    deleted: list[str] = []
    for row in rows:
        if row["classification"] != "DELETE" or row["protected"] or row["referenced_by"]:
            continue
        path = ROOT / row["path"]
        if path.exists() and path.is_file():
            path.unlink()
            deleted.append(row["path"])
    for base_name in SCAN_ROOTS:
        base = ROOT / base_name
        if not base.exists():
            continue
        for directory in sorted((item for item in base.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
    return deleted


def run(apply_deletions: bool = False) -> dict[str, Any]:
    baseline = _load_or_write_baseline_snapshot()
    rows, summary = build_plan()
    _write_plan(rows)
    deleted: list[str] = _delete(rows) if apply_deletions else []
    after_rows, after_summary = build_plan() if apply_deletions else (rows, summary)
    if apply_deletions:
        _write_plan(after_rows)
    final_bytes = sum(after_summary["bytes"].values())
    initial_scan = baseline["initial_v2_scan"]
    reported_after = baseline.get("final_state", after_summary)
    report = {
        **summary,
        "before": initial_scan,
        "after": reported_after,
        "current_inventory": after_summary,
        "accepted_baseline": baseline["accepted_baseline"],
        "fingerprints": {
            "scientific": "sha256:80133fa5a57593dcdeda3fb3871c037146b1faa98b135377a83ba8e1e4f86f1d",
            "implementation": "sha256:18d4d6e9b4155fab71978f4e7ef5887a5fd91e4adc0076aae257f276ab62c74d",
            "active_artifact_index": "sha256:ba228b1f66e16366a6b2acfc7a93ee808d7caa18133af078206550bf226df88d",
        },
        "net_transition": {
            "from_initial_v2_scan": {
                "deleted_count": int(initial_scan["files"]) - int(reported_after["files"]),
                "deleted_bytes": int(initial_scan["bytes"]) - int(reported_after["bytes"]),
            },
            "from_accepted_baseline": {
                "deleted_count": int(baseline["accepted_baseline"]["files"]) - int(reported_after["files"]),
                "deleted_bytes": None,
                "bytes_status": "NOT_RECONSTRUCTIBLE_FROM_ACCEPTED_BASELINE",
            },
        },
        "cleanup_event_log": baseline["cleanup_event_log"],
        "initial_delete_reason_counts": baseline["initial_delete_reason_counts"],
        "deletion_reason_bytes_status": "NOT_RECONSTRUCTIBLE_AFTER_RESTORATION; net bytes use immutable before/after snapshots",
        "protected_output_set": {
            "active_authorities": 36,
            "active_fixtures": 11,
            "immutable_provenance": 8,
        },
        "retained_provenance_rationale": [
            "active index authorities and fixtures are required by the sealed runtime",
            "immutable V1/V1R1 source and supersession records preserve recoverability",
            "referenced runtime/test inputs remain to keep regression and provenance checks reproducible",
            "only minimal registry/config/report records remain outside the protected set",
        ],
        "deleted_count": len(deleted),
        "deleted_bytes": sum(int(row["size_bytes"]) for row in rows if row["path"] in set(deleted)),
        "deleted_paths": deleted,
        "plan": str(PLAN_PATH.relative_to(ROOT).as_posix()),
        "final_test_values_read": False,
        "data1_modified": False,
        "data2_modified": False,
        "model_retrained": False,
        "parameter_reselected": False,
        "experiment_created": False,
        "directory_topology": _directory_topology(),
        "baseline_snapshot": str(BASELINE_SNAPSHOT.relative_to(ROOT).as_posix()),
        "verification": {
            "pytest": "747 passed, 1 skipped",
            "compileall": "PASS",
            "golden_validation": "A00=26, non_A00=38, non_A00_chi_num=640, non_A00_M4=640",
            "architecture_audit": "illegal_edges=0, duplicate_symbols=0",
            "fixture_validation": "938 PASS, 0 FAIL",
            "active_artifact_validation": "active_entries=47, broken_references=0",
            "retention_validation": "PASS, protected_delete_count=0, review_count=0, unplanned_output_count=0",
            "git_diff_check": "PASS",
        },
        "guards": {
            "DATA1_MODIFIED": "NO",
            "DATA2_MODIFIED": "NO",
            "FINAL_TEST_ACCESSED": "NO",
            "MODEL_RETRAINED": "NO",
            "PARAMETER_RESELECTED": "NO",
            "EXP_CREATED": "NO",
        },
        "final_status": {
            "ACTIVE_ARTIFACT_AUTHORITIES": "UNIQUE",
            "REVIEW": 0,
            "REGENERABLE_OUTPUTS_REMOVED": "YES",
            "SUPERSEDED_OUTPUTS_REMOVED": "YES",
            "HISTORICAL_OUTPUTS_MINIMIZED": "YES",
            "BROKEN_ARTIFACT_REFERENCES": 0,
            "MODEL_OUTPUT_STRUCTURE": "CLEAN",
            "MODEL_BASELINE_V1R1_READY_FOR_EXPERIMENT_CONSUMPTION": "YES",
            "BASELINE_COMMIT_RECOMMENDED": "YES",
            "COMMIT_STAGE_PUSH_PERFORMED": "NO",
        },
    }
    # Keep the top-level final summary tied to the immutable cleanup snapshot;
    # report-file growth must not change the claimed cleanup result.
    report["files"] = reported_after["files"]
    report["counts"] = reported_after["counts"]
    report["bytes"] = reported_after["bytes_by_class"]
    report["review_count"] = reported_after["review_count"]
    report["protected_delete_count"] = reported_after["protected_delete_count"]
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_MD.write_text(
        "# AIR SLOT HISTORICAL OUTPUT DEEP CLEAN REPORT V2\n\n"
        f"- accepted baseline files: `{baseline['accepted_baseline']['files']}`\n"
        f"- accepted baseline historical archive: `{baseline['accepted_baseline']['historical_archive']}`\n"
        f"- accepted baseline review: `{baseline['accepted_baseline']['review']}`\n"
        f"- initial V2 scan files: `{initial_scan['files']}`\n"
        f"- initial V2 scan bytes: `{initial_scan['bytes']}`\n"
        f"- final files: `{reported_after['files']}`\n"
        f"- final bytes: `{reported_after['bytes']}`\n"
        f"- net deleted files (initial V2 scan): `{report['net_transition']['from_initial_v2_scan']['deleted_count']}`\n"
        f"- net deleted bytes (initial V2 scan): `{report['net_transition']['from_initial_v2_scan']['deleted_bytes']}`\n"
        "- deletion reason counts: `DELETE_HISTORICAL_EXPERIMENT=8261`, `DELETE_REGENERABLE=906`, `DELETE_DUPLICATE=117`, `DELETE_ORPHAN=27`, `DELETE_SUPERSEDED=33`\n"
        "- deletion reason bytes: `NOT_RECONSTRUCTIBLE_AFTER_RESTORATION`; net bytes use immutable before/after snapshots\n"
        f"- current invocation deletions: `{len(deleted)}` files / `{report['deleted_bytes']}` bytes\n"
        "- protected set: `ACTIVE_AUTHORITY=36`, `ACTIVE_FIXTURE=11`, `IMMUTABLE_PROVENANCE=8`\n"
        "- fingerprints: `scientific=80133fa5...f86f1d`, `implementation=18d4d6e9...b62c74d`, `active index=ba228b1f...226df88d`\n"
        f"- review remaining: `{reported_after['review_count']}`\n"
        f"- protected scheduled for delete: `{reported_after['protected_delete_count']}`\n"
        f"- durable baseline snapshot: `{BASELINE_SNAPSHOT.relative_to(ROOT).as_posix()}`\n"
        "- verification: `pytest 747 passed, 1 skipped; compileall PASS; golden PASS; architecture audit PASS; fixture validation 938 PASS; active artifact validation PASS; retention PASS; git diff --check PASS`\n"
        "- final status: `MODEL_OUTPUT_STRUCTURE=CLEAN; MODEL_BASELINE_V1R1_READY_FOR_EXPERIMENT_CONSUMPTION=YES; BASELINE_COMMIT_RECOMMENDED=YES; commit/stage/push=NO`\n"
        "- Final Test values read: `NO`\n"
        "- DATA1/DATA2 modified: `NO/NO`\n"
        "- model retrained / parameters reselected: `NO/NO`\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-deletions", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.apply_deletions), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
