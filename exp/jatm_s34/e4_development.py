"""Bounded six-year Development preflight for E4.

The preflight is intentionally fail-closed: it records which year-local and
FIXED_COMMON reference bundles are available, but never opens Test rows or
silently substitutes a different year's reference.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

YEARS = tuple(range(2017, 2023))


def _head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def inspect_year(root: Path, year: int) -> dict:
    pre = root / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1" / str(year)
    manifest_path = pre / "PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json"
    local_refs = pre / "M2_REFERENCES"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    counts = (manifest.get("cohort_audit") or {}).get("cohort_counts") or {}
    return {
        "year": year,
        "pre_manifest": str(manifest_path),
        "pre_status": "PRE_DEVELOPMENT_READY" if all(isinstance(counts.get(k), int) and counts[k] > 0 for k in ("train", "calibration", "development")) else "MISSING_PRE_DEVELOPMENT",
        "cohort_counts": counts,
        "year_local_reference_status": "READY" if any(local_refs.glob("M2_REFERENCE_BUNDLE_MANIFEST.json")) else "MISSING_YEAR_LOCAL_M2_BUNDLE",
        "year_local_reference_root": str(local_refs),
        "test_status": "BLOCKED_TEST_ACCESS",
        "final_test_access_count": (manifest.get("cohort_audit") or {}).get("final_test_access_count", 0),
    }


def run(*, root: Path, output_root: Path) -> dict:
    rows = [inspect_year(root, year) for year in YEARS]
    fixed_common = root / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1_D4_2017H1_R2" / "2017" / "M2_REFERENCES"
    fixed_status = "READY_AUDITED_2017_H1" if (fixed_common / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json").is_file() else "MISSING_AUDITED_2017_H1"
    payload = {
        "schema_version": "JATM_S34_E4_DEVELOPMENT_PREFLIGHT_V1",
        "status": "ENGINEERING_INCOMPLETE" if any(row["year_local_reference_status"] != "READY" for row in rows) else "READY_TO_RUN",
        "years": rows,
        "year_local_rule": "Train Jan-Jun; Calibration Jul; Development Aug-Sep; Test Oct-Dec",
        "fixed_common": {"status": fixed_status, "root": str(fixed_common)},
        "test_access_count": 0,
        "git_head": _head(root),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "E4_PREFLIGHT.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run(root=args.repo_root.resolve(), output_root=args.output_root.resolve())
    print(json.dumps({"status": result["status"], "year_local_ready": sum(row["year_local_reference_status"] == "READY" for row in result["years"]), "fixed_common": result["fixed_common"]["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
