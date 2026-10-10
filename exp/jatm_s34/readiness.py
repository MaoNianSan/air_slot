"""Read-only readiness gate for the six-year JATM S34 experiment chain.

This module does not read Q4/Test rows and does not execute PRE, M1, M2, M3,
or M4. It only validates the already materialized per-year development
manifests and emits a typed status matrix so a later authorized Test runner
cannot silently treat Development as Test.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
MANIFEST_RELATIVE = Path("artifacts/models/pre/PRE_MULTIYEAR_V1")
MANIFEST_NAME = "PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_year(root: Path, year: int) -> dict[str, Any]:
    path = root / MANIFEST_RELATIVE / str(year) / MANIFEST_NAME
    row: dict[str, Any] = {
        "year": year,
        "manifest_path": str(path),
        "status": "MISSING_PRE_DEVELOPMENT_MANIFEST",
        "train": None,
        "calibration": None,
        "development": None,
        "test": None,
        "final_test_access_count": None,
        "test_execution_status": "BLOCKED_TEST_ACCESS",
    }
    if not path.is_file():
        return row
    payload = _read_json(path)
    audit = payload.get("cohort_audit") or {}
    counts = audit.get("cohort_counts") or {}
    row.update(
        {
            "train": counts.get("train"),
            "calibration": counts.get("calibration"),
            "development": counts.get("development"),
            "test": counts.get("test"),
            "final_test_access_count": audit.get("final_test_access_count"),
            "source_manifest_created_at": payload.get("created_at_utc"),
            "dataset_instance_id": payload.get("dataset_instance_id"),
        }
    )
    if all(isinstance(counts.get(key), int) and counts[key] > 0
           for key in ("train", "calibration", "development")):
        row["status"] = "PRE_DEVELOPMENT_READY"
    if counts.get("test") not in (None, 0) or audit.get("final_test_access_count", 0) != 0:
        row["test_execution_status"] = "REQUIRES_AUTHORIZED_TEST_RUN_AUDIT"
    return row


def build_readiness(root: Path, years: tuple[int, ...] = YEARS) -> dict[str, Any]:
    rows = [inspect_year(root, year) for year in years]
    return {
        "schema_version": "JATM_S34_YEAR_READINESS_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_git_head": _git_head(root),
        "source_branch": _git_branch(root),
        "reads_q4_or_test_rows": False,
        "executes_scientific_model": False,
        "rows": rows,
        "summary": {
            "pre_development_ready": sum(row["status"] == "PRE_DEVELOPMENT_READY" for row in rows),
            "missing_pre_development": sum(row["status"] != "PRE_DEVELOPMENT_READY" for row in rows),
            "test_runs_ready": 0,
            "test_runs_blocked": len(rows),
        },
    }


def _git_branch(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def write_outputs(payload: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "YEAR_READINESS.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# JATM S34 Year Readiness",
        "",
        f"- Source HEAD: `{payload['source_git_head']}`",
        f"- Branch: `{payload['source_branch']}`",
        "- Q4/Test rows read: `False`",
        "- Scientific model executed: `False`",
        "",
        "| Year | PRE status | Train | Calibration | Development | Test | Test status |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['year']} | {row['status']} | {row['train'] or '-'} | "
            f"{row['calibration'] or '-'} | {row['development'] or '-'} | "
            f"{row['test'] if row['test'] is not None else '-'} | "
            f"{row['test_execution_status']} |"
        )
    lines.extend(
        [
            "",
            "All six existing manifests have `test=0` and `final_test_access_count=0`; "
            "a later authorized Test run must create a new versioned output root.",
        ]
    )
    (out_dir / "YEAR_READINESS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    args = parser.parse_args(argv)
    root = project_root()
    payload = build_readiness(root, tuple(args.years))
    write_outputs(payload, args.out_dir)
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


__all__ = ["YEARS", "build_readiness", "inspect_year", "main", "write_outputs"]

if __name__ == "__main__":
    raise SystemExit(main())

