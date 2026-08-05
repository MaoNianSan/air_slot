from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file, write_json
from .contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
    ResumeContract,
    frozen_config_hash,
    git_metadata,
    implementation_hash,
)
from .observation_requests import observation_request_hashes


RESUME_MANIFEST_NAME = "staging_resume_manifest.json"
PARTITION_MANIFEST_NAME = "observation_partition_manifest.json"


def expected_observation_partitions(requests: pd.DataFrame) -> tuple[str, ...]:
    if requests.empty:
        return ()
    partitions: set[str] = set()
    for request in requests.itertuples(index=False):
        start = pd.Timestamp(request.request_start).normalize()
        end = pd.Timestamp(request.request_end).normalize()
        for date in pd.date_range(start, end, freq="D"):
            partitions.add(
                f"source={request.source}/observation_date={date.strftime('%Y-%m-%d')}"
            )
    return tuple(sorted(partitions))


def build_resume_contract(
    cfg: dict[str, Any],
    raw_inventory: pd.DataFrame,
    requests: pd.DataFrame,
    *,
    cache_key: str = "",
    episode_interval_hash: str | None = None,
) -> ResumeContract:
    source_records = []
    if not raw_inventory.empty:
        columns = [value for value in ["source", "relative_path", "sha256", "size_bytes"] if value in raw_inventory]
        source_records = raw_inventory[columns].astype(str).to_dict("records")
    request_hash_payload = observation_request_hashes(requests)
    request_columns = [value for value in ["chain_episode_id", "source", "request_start", "request_end"] if value in requests]
    request_rows = requests[request_columns].astype(str).to_dict("records") if not requests.empty else []
    interval_hashes = sorted(requests.get("episode_interval_hash", pd.Series(dtype="string")).dropna().astype(str).unique())
    implementation = implementation_hash(cfg.get("project_root"))
    git = git_metadata(cfg.get("project_root"))
    return ResumeContract(
        contract_id=CONTRACT_ID,
        schema_version=SCHEMA_VERSION,
        research_code_revision=RESEARCH_CODE_REVISION,
        frozen_config_hash=frozen_config_hash(cfg),
        source_manifest_hash=object_hash(source_records),
        source_schema_hash=object_hash(cfg.get("sources", {})),
        request_contract_hash=request_hash_payload["request_contract_hash"],
        request_rows_hash=request_hash_payload["request_rows_hash"] or object_hash(request_rows),
        episode_interval_hash=episode_interval_hash or request_hash_payload["episode_interval_hash"] or object_hash(interval_hashes),
        cache_key=str(cache_key),
        expected_partitions=expected_observation_partitions(requests),
        git_commit=str(git["git_commit"]),
        git_dirty=bool(git["git_dirty"]),
        implementation_hash=implementation["hash"],
        implementation_hash_status=str(implementation["status"]),
        implementation_file_count=int(implementation["file_count"]),
    )


def write_resume_manifest(staging: Path, contract: ResumeContract) -> Path:
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / RESUME_MANIFEST_NAME
    write_json(contract.as_dict(), path)
    return path


def read_resume_manifest(staging: Path) -> ResumeContract:
    path = staging / RESUME_MANIFEST_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ResumeContract.from_dict(payload)


def compare_resume_contract(expected: ResumeContract, actual: ResumeContract) -> dict[str, Any]:
    expected_dict = expected.as_dict()
    actual_dict = actual.as_dict()
    hard_fields = {
        "contract_id", "schema_version", "research_code_revision",
        "frozen_config_hash", "source_manifest_hash", "source_schema_hash",
        "request_contract_hash", "request_rows_hash", "episode_interval_hash",
        "cache_key", "expected_partitions",
    }
    differences = {
        field: {"expected": expected_dict.get(field), "actual": actual_dict.get(field)}
        for field in hard_fields
        if expected_dict.get(field) != actual_dict.get(field)
    }
    warning_fields = {
        "git_commit": "GIT_COMMIT_CHANGED_WARNING",
        "git_dirty": "GIT_DIRTY_STATUS_CHANGED_WARNING",
        "implementation_hash": "IMPLEMENTATION_HASH_CHANGED_WARNING",
        "implementation_hash_status": "IMPLEMENTATION_HASH_STATUS_WARNING",
        "implementation_file_count": "IMPLEMENTATION_FILE_COUNT_CHANGED_WARNING",
    }
    warnings = [
        {
            "code": code,
            "field": field,
            "expected": expected_dict.get(field),
            "actual": actual_dict.get(field),
        }
        for field, code in warning_fields.items()
        if expected_dict.get(field) != actual_dict.get(field)
    ]
    return {
        "compatible": not differences,
        "differences": differences,
        "warnings": warnings,
    }


def _partition_completion(staging: Path, expected: ResumeContract) -> dict[str, Any]:
    manifests = {
        "observations": staging / "observations" / PARTITION_MANIFEST_NAME,
        "observation_membership": (
            staging
            / "observation_membership"
            / "observation_membership_partition_manifest.json"
        ),
    }
    totals = {"PASS": 0, "PASS_EMPTY": 0, "FAIL": 0, "IN_PROGRESS": 0}
    missing: list[str] = []
    dataset_completion: dict[str, Any] = {}
    for dataset, manifest_path in manifests.items():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            partitions = payload.get("partitions", payload)
        except (OSError, json.JSONDecodeError):
            partitions = {}
        counts = {"PASS": 0, "PASS_EMPTY": 0, "FAIL": 0, "IN_PROGRESS": 0}
        dataset_missing: list[str] = []
        for key in expected.expected_partitions:
            record = partitions.get(key)
            if not isinstance(record, dict):
                dataset_missing.append(key)
                continue
            status = str(record.get("status", ""))
            if status in counts:
                counts[status] += 1
            else:
                dataset_missing.append(key)
        for status, count in counts.items():
            totals[status] += count
        missing.extend(f"{dataset}:{key}" for key in dataset_missing)
        dataset_completion[dataset] = {
            "pass_nonempty": counts["PASS"],
            "pass_empty": counts["PASS_EMPTY"],
            "failed": counts["FAIL"],
            "in_progress": counts["IN_PROGRESS"],
            "missing": dataset_missing,
            "total": len(expected.expected_partitions),
        }
    complete = totals["PASS"] + totals["PASS_EMPTY"]
    return {
        "complete_partitions": complete,
        "pass_nonempty": totals["PASS"],
        "pass_empty": totals["PASS_EMPTY"],
        "failed": totals["FAIL"],
        "in_progress": totals["IN_PROGRESS"],
        "missing_partitions": missing,
        "expected_partitions": len(expected.expected_partitions) * len(manifests),
        "dataset_completion": dataset_completion,
    }


def select_compatible_staging(
    output_root: Path,
    expected: ResumeContract,
    *,
    audit_root: Path | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    """Select a compatible staging directory, never by mtime alone."""
    candidates = sorted(output_root.parent.glob(f".{output_root.name}.staging-*"))
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for path in candidates:
        entry: dict[str, Any] = {"path": str(path), "reason": ""}
        try:
            actual = read_resume_manifest(path)
        except FileNotFoundError:
            entry["reason"] = "MISSING_RESUME_MANIFEST"
            rejected.append(entry)
            continue
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            entry["reason"] = "INVALID_RESUME_MANIFEST"
            entry["detail"] = str(exc)
            rejected.append(entry)
            continue
        comparison = compare_resume_contract(expected, actual)
        if not comparison["compatible"]:
            entry["reason"] = "RESUME_CONTRACT_MISMATCH"
            entry["differences"] = comparison["differences"]
            rejected.append(entry)
            continue
        entry["warnings"] = comparison["warnings"]
        entry.update(_partition_completion(path, expected))
        entry["mtime"] = path.stat().st_mtime
        accepted.append(entry)
    selected = None
    if accepted:
        selected = Path(
            max(accepted, key=lambda item: (item["complete_partitions"], item["mtime"]))["path"]
        )
    audit = {
        "status": "PASS" if selected is not None else "NO_COMPATIBLE_STAGING",
        "contract": expected.as_dict(),
        "selected": str(selected) if selected else None,
        "accepted": accepted,
        "rejected": rejected,
    }
    destination = audit_root or (output_root.parent / "reports")
    destination.mkdir(parents=True, exist_ok=True)
    write_json(audit, destination / "staging_resume_audit.json")
    return selected, audit


def resume_contract_diff(expected: ResumeContract, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return compare_resume_contract(expected, ResumeContract.from_dict(payload))
    except (KeyError, TypeError, ValueError) as exc:
        return {"compatible": False, "differences": {"manifest": str(exc)}}
