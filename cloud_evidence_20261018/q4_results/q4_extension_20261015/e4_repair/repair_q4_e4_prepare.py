"""Preflight and correct the Q4 manifests before the E4-only repair run."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from model.common.identity import content_id


YEARS = tuple(range(2017, 2023))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def valid_summary(path: Path, *, year: int, cohort_hash: str, section: str) -> dict:
    payload = read_json(path)
    recorded_hash = payload.pop("artifact_hash")
    if content_id(payload) != recorded_hash:
        raise RuntimeError(f"SUMMARY_CONTENT_HASH_MISMATCH:{year}:{section}")
    if payload.get("year") != year or payload.get("split") != "test":
        raise RuntimeError(f"SUMMARY_SCOPE_MISMATCH:{year}:{section}")
    observed_hash = (
        payload.get("evaluation_cohort_hash")
        if section == "E1"
        else (payload.get("input_contract") or {}).get("evaluation_cohort_hash")
    )
    if observed_hash != cohort_hash or payload.get("status") != "TEST_COMPLETE":
        raise RuntimeError(f"SUMMARY_COHORT_OR_STATUS_MISMATCH:{year}:{section}")
    return read_json(path)


def pass_access_count(year_root: Path, year: int) -> int:
    pass_root = year_root / "E4" / str(year) / "passes"
    total = 0
    if not pass_root.exists():
        return total
    for receipt_path in pass_root.glob("fitN*/PASS_MANIFEST.json"):
        receipt = read_json(receipt_path)
        if (receipt.get("status") == "PASS"
                and receipt.get("split") == "test"
                and receipt.get("pass_id", "").startswith(f"{year}_test_fitN")
                and int(receipt.get("case_count", 0)) == 4096):
            total += int(receipt.get("final_test_access_count", 0))
    return total


def main() -> None:
    repo = Path("/data/airslot/worktree").resolve()
    results = Path("/data/airslot/results/q4_extension_20261015").resolve()
    repair_root = results / "e4_repair"
    binding_path = repair_root / "Q4_E4_REPAIR_BINDING_20261015.json"
    binding = read_json(binding_path)
    master_path = results / "Q4_MULTIYEAR_MANIFEST.json"
    master = read_json(master_path)
    master_before_hash = sha256(master_path)

    actual_binding_hash = sha256(repo / "Q4_PRE_RUN_BINDING_MANIFEST.json")
    if actual_binding_hash != binding["parent"]["observed_pre_run_binding_sha256"]:
        raise RuntimeError("PARENT_BINDING_FILE_HASH_CHANGED")
    if (master.get("pre_run_binding_manifest_sha256")
            != binding["parent"]["multi_year_manifest_recorded_binding_sha256"]):
        raise RuntimeError("PARENT_MASTER_BINDING_HASH_CHANGED")
    if master_before_hash != binding["parent"]["multi_year_manifest_sha256_before_repair"]:
        raise RuntimeError("PARENT_MASTER_MANIFEST_HASH_CHANGED")

    backup_root = repair_root / "pre_repair_manifests"
    backup_root.mkdir(parents=True, exist_ok=True)
    for source in [master_path] + [results / str(year) / "Q4_YEAR_MANIFEST.json" for year in YEARS]:
        target = backup_root / source.name if source == master_path else backup_root / f"{source.parent.name}_Q4_YEAR_MANIFEST.json"
        if target.exists():
            if sha256(target) != sha256(source):
                raise RuntimeError(f"PRE_REPAIR_BACKUP_CONFLICT:{target}")
        else:
            target.write_bytes(source.read_bytes())

    cohort_hashes = binding["frozen_cohort_sha256"]
    year_records = {}
    for year in YEARS:
        year_root = results / str(year)
        year_manifest_path = year_root / "Q4_YEAR_MANIFEST.json"
        year_manifest = read_json(year_manifest_path)
        cohort_dir = results / "cohorts" / str(year) / "cohort"
        cohort_manifest = read_json(cohort_dir / "Q4_COHORT_MANIFEST.json")
        if (cohort_manifest.get("selected_episode_count") != 4096
                or cohort_manifest.get("selected_ids_sha256") != cohort_hashes[str(year)]
                or sha256(cohort_dir / "Q4_SELECTED_COHORT.jsonl")
                != cohort_hashes[str(year)]):
            raise RuntimeError(f"FROZEN_COHORT_INVALID:{year}")

        e1 = valid_summary(
            year_root / "E1" / "E1_SUMMARY.json", year=year,
            cohort_hash=cohort_hashes[str(year)], section="E1",
        )
        e2 = valid_summary(
            year_root / "E2_E3" / "E2_E3_SUMMARY.json", year=year,
            cohort_hash=cohort_hashes[str(year)], section="E2_E3",
        )
        e4 = read_json(year_root / "E4" / "E4_DEVELOPMENT_MANIFEST.json")
        if e4.get("status") != "ENGINEERING_INCOMPLETE":
            raise RuntimeError(f"EXPECTED_E4_FAILURE_STATE_MISSING:{year}")
        observed_e4_accesses = pass_access_count(year_root, year)
        previous_e2_manifest = year_manifest.get("E2_E3") or {}
        counts = {
            "E1": int(e1.get("final_test_access_count", 0)),
            "E2_E3_first_pass": int(previous_e2_manifest.get("first_pass_episode_accesses", 0)),
            "E2_E3_second_pass": int(previous_e2_manifest.get("second_pass_episode_accesses", 0)),
            "E4": observed_e4_accesses,
        }
        if counts["E1"] != 4096 or counts["E2_E3_first_pass"] != 4096 or counts["E2_E3_second_pass"] != 4096:
            raise RuntimeError(f"PREVIOUS_E1_E2_E3_ACCESS_LEDGER_INVALID:{year}")

        year_manifest["pre_repair_reported_status"] = year_manifest.get("status")
        year_manifest["pre_repair_completed_stages"] = year_manifest.get("completed_stages", [])
        year_manifest["status"] = "ENGINEERING_INCOMPLETE"
        year_manifest["current_stage"] = "E4_REPAIR_REQUIRED"
        year_manifest["completed_stages"] = ["COHORT_FROZEN", "E1", "E2_E3"]
        year_manifest["E4"] = {
            "status": "ENGINEERING_INCOMPLETE",
            "manifest": str(year_root / "E4" / "E4_DEVELOPMENT_MANIFEST.json"),
            "access_count": observed_e4_accesses,
            "access_count_unit": "selected_q4_episode_model_evaluations",
        }
        year_manifest["final_test_access_ledger"] = {
            "raw_q4_ontime_source_rows_read": int(
                (year_manifest.get("final_test_access_ledger") or {}).get(
                    "raw_q4_ontime_source_rows_read", 0
                )
            ),
            "selected_q4_episode_evaluations": counts,
        }
        year_manifest["final_test_access_count"] = sum(counts.values())
        year_manifest["final_test_access_count_unit"] = "selected_q4_episode_evaluations"
        year_manifest["repair_note"] = (
            "E1 and E2_E3 summaries passed content-hash and cohort checks. "
            "The prior E4 attempt has no completed test-labelled model-pass receipts."
        )
        year_manifest["updated_at"] = now()
        atomic_json(year_manifest_path, year_manifest)

        year_records[str(year)] = {
            "cohort_hash": cohort_hashes[str(year)],
            "e1_artifact_hash": e1["artifact_hash"],
            "e2_e3_artifact_hash": e2["artifact_hash"],
            "e4_status_before_repair": e4.get("status"),
            "e4_error": (e4.get("years") or [{}])[0].get("error"),
            "completed_e4_test_model_evaluations_before_repair": observed_e4_accesses,
            "q4_year_manifest_sha256_before_repair": sha256(
                backup_root / f"{year}_Q4_YEAR_MANIFEST.json"
            ),
        }

    master["pre_repair_status"] = master.get("status")
    master["pre_repair_year_status"] = master.get("year_status", {})
    master["status"] = "E4_REPAIR_REQUIRED"
    master["year_status"] = {str(year): "ENGINEERING_INCOMPLETE" for year in YEARS}
    master["pre_run_binding_manifest_sha256_observed"] = actual_binding_hash
    master["pre_run_binding_hash_discrepancy"] = (
        "The recorded digest differs from the current on-server binding file; "
        "the discrepancy is retained and the E4 repair is separately bound."
    )
    master["e4_repair_binding_manifest"] = str(binding_path)
    master["e4_repair_binding_manifest_sha256"] = sha256(binding_path)
    master["e4_repair_started_at"] = now()
    master["e4_repair_preflight"] = "PASS"
    master["updated_at"] = now()
    atomic_json(master_path, master)

    report = {
        "schema_version": "JATM_S34_Q4_E4_REPAIR_PREFLIGHT_V1",
        "status": "PASS",
        "created_at": now(),
        "parent_master_manifest_sha256_before_repair": master_before_hash,
        "observed_parent_binding_manifest_sha256": actual_binding_hash,
        "recorded_parent_binding_manifest_sha256": binding["parent"]["multi_year_manifest_recorded_binding_sha256"],
        "e4_repair_binding_manifest_sha256": sha256(binding_path),
        "results_root": str(results),
        "years": year_records,
        "action": "Mark the prior overall result incomplete and authorize E4-only resume using frozen cohorts and hash-validated E1/E2_E3 summaries.",
    }
    atomic_json(repair_root / "Q4_E4_REPAIR_PREFLIGHT.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
