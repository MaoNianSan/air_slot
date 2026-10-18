"""Machine checks for the versioned 2017 H1 FIXED_COMMON reference bundle.

This is a read-only audit: it never fits or rewrites a reference artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

EXPECTED_KINDS = {
    "taxi",
    "turnaround",
    "downstream_exposure",
    "passenger",
    "expected_passengers",
    "connection_share",
}
EXPECTED_SCALES = {
    "F_continuity": "minutes",
    "F_execution": "minutes",
    "F_propagation": "exposure_minutes",
    "P_itinerary": "expected_disrupted_connecting_passenger_exposure",
    "P_service": "expected_long_delay_passenger_service_exposure",
    "P_time": "passenger_minutes",
    "R_operating": "excess_taxi_minutes",
}


def _sha256_json(payload: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def audit(root: Path, *, year: int = 2017) -> dict:
    ref_dir = root / str(year) / "M2_REFERENCES"
    manifest = json.loads((ref_dir / "M2_REFERENCE_BUNDLE_MANIFEST.json").read_text())
    scales = json.loads((ref_dir / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json").read_text())
    expected_id = "data2_2017_2022"
    expected_period = f"{year}-H1"
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    check("manifest_identity", manifest.get("dataset_instance_id") == expected_id and manifest.get("year") == year,
          f"dataset={manifest.get('dataset_instance_id')}, year={manifest.get('year')}")
    check("fit_window", manifest.get("fit_window") == {"start": f"{year}-01-01", "end": f"{year}-06-30"},
          str(manifest.get("fit_window")))
    check("admissibility", manifest.get("t100_admissibility") == "YEAR == Y and MONTH <= 6" and
          manifest.get("db1b_admissibility") == "Q1 + Q2 of Y", "T100 H1 and DB1B Q1+Q2")

    payload_status = {}
    for path in sorted(ref_dir.glob("M2_*_REFERENCE_*.json")):
        payload = json.loads(path.read_text())
        kind = path.name.split("M2_", 1)[1].split("_REFERENCE", 1)[0].lower()
        payload_status[kind] = {"path": str(path), "artifact_hash": payload.get("artifact_hash")}
        expected_hash = payload.get("artifact_hash")
        unhashed = dict(payload)
        unhashed.pop("artifact_hash", None)
        check(f"{kind}_artifact_hash", expected_hash == _sha256_json(unhashed), str(expected_hash))
        check(f"{kind}_identity", payload.get("dataset_instance_id") == expected_id and
              payload.get("experiment_year") == year and payload.get("fit_start") == f"{year}-01-01" and
              payload.get("fit_end") == f"{year}-06-30" and "data2_2019" not in json.dumps(payload),
              f"dataset={payload.get('dataset_instance_id')}, period={payload.get('fit_period')}")
        manifest_hash = manifest.get("payload_hashes", {}).get(kind)
        check(f"{kind}_manifest_hash", manifest_hash == _sha256_json(payload), str(manifest_hash))

    check("all_reference_kinds", set(payload_status) == EXPECTED_KINDS,
          f"found={sorted(payload_status)}")
    check("scale_identity", scales.get("dataset_instance_id") == expected_id and
          scales.get("experiment_year") == year and scales.get("fit_period") == expected_period,
          f"dataset={scales.get('dataset_instance_id')}, period={scales.get('fit_period')}")
    scale_results = {}
    for name, unit in EXPECTED_SCALES.items():
        item = scales.get("scales", {}).get(name, {})
        ok = isinstance(item.get("median"), (int, float)) and item["median"] > 0
        ok = ok and isinstance(item.get("positive_n"), int) and item["positive_n"] > 0
        ok = ok and isinstance(item.get("population_rows"), int) and item["population_rows"] >= item["positive_n"]
        ok = ok and item.get("unit") == unit
        scale_results[name] = {"status": "PASS" if ok else "FAIL", "value": item}
        check(f"scale_{name}", ok, str(item))
    check("scale_bundle_hash", scales.get("bundle_hash") == _sha256_json({k: v for k, v in scales.items() if k != "bundle_hash"}),
          str(scales.get("bundle_hash")))

    passed = all(item["status"] == "PASS" for item in checks)
    return {
        "status": "PASS_FIXED_COMMON_REBUILT" if passed else "BLOCKED_FIXED_COMMON",
        "root": str(root), "year": year, "dataset_instance_id": expected_id,
        "reference_contract_id": manifest.get("reference_contract_id"),
        "checks": checks, "scales": scale_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--year", type=int, default=2017)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root, year=args.year)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [f"# D4 FIXED_COMMON audit ({result['year']} H1)", "", f"- Status: `{result['status']}`", f"- Root: `{result['root']}`", "", "| Check | Status | Detail |", "|---|---|---|"]
    lines.extend(f"| {c['name']} | {c['status']} | {c['detail']} |" for c in result["checks"])
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS_FIXED_COMMON_REBUILT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
