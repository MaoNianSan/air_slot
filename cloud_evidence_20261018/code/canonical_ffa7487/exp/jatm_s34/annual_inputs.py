"""Annual Development input contracts for the JATM E1--E4 runners.

This module is deliberately an input adapter, not a second scientific model.
It validates the six annual PRE cohorts and year-local M2 references, and
records whether an annual M1 runtime artifact is available.  It never reads
Test data and never promotes the M5-b N=128 pilot to a scientific model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PRE_ROOT = ROOT / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
YEARLOCAL_ROOT = (
    ROOT / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1"
)
COHORT_ROOT = ROOT / "data2" / "reports" / "cohort_size_stability"
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)


def _hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso(value: Any) -> datetime:
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class AnnualInputContract:
    year: int
    status: str
    scientific_status: str
    pre_root: Path
    m2_root: Path
    manifest: dict[str, Any]
    m2_manifest: dict[str, Any]
    audit: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "status": self.status,
            "scientific_status": self.scientific_status,
            "pre_root": str(self.pre_root),
            "m2_root": str(self.m2_root),
            "manifest": self.manifest,
            "m2_manifest": self.m2_manifest,
            "audit": self.audit,
            "final_test_access_count": 0,
        }


def _annual_m1_candidates(year: int) -> list[Path]:
    """Return only annual main-model candidates, never the N=128 pilot."""
    root = ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}"
    return [
        root / "M1_HISTORY_PRIMARY.pt",
        root / "M1_CURRENT_COMPARATOR.pt",
    ]


def validate_year(year: int) -> AnnualInputContract:
    if int(year) not in YEARS:
        raise ValueError(f"JATM_ANNUAL_YEAR_UNSUPPORTED:{year}")
    year = int(year)
    pre_root = PRE_ROOT / str(year)
    m2_root = YEARLOCAL_ROOT / str(year) / "M2_REFERENCES"
    manifest_path = pre_root / "PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json"
    m2_path = m2_root / "M2_REFERENCE_BUNDLE_MANIFEST.json"
    audit_path = pre_root / "SPLIT_CONTAINMENT_AUDIT.json"
    states_path = pre_root / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl"
    required = {
        "pre_manifest": manifest_path,
        "m2_manifest": m2_path,
        "split_audit": audit_path,
        "states": states_path,
        "cohort_state": pre_root / "COHORT_PREPARATION_STATE.pt",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        return AnnualInputContract(
            year,
            "DATA_INSUFFICIENT",
            "DATA_INSUFFICIENT",
            pre_root,
            m2_root,
            {},
            {},
            {"missing": missing, "final_test_access_count": 0},
        )
    manifest = _read(manifest_path)
    m2_manifest = _read(m2_path)
    split_audit = _read(audit_path)
    reasons: list[str] = []
    if int(manifest.get("year", -1)) != year:
        reasons.append("YEAR_BINDING_MISMATCH")
    if manifest.get("status", "PASS") not in ("PASS", "READY"):
        reasons.append("PRE_MANIFEST_NOT_PASS")
    if int(manifest.get("final_test_access_count", -1)) != 0:
        reasons.append("FINAL_TEST_ACCESS_NONZERO")
    if int(m2_manifest.get("year", -1)) != year:
        reasons.append("M2_YEAR_BINDING_MISMATCH")
    fit = m2_manifest.get("fit_window", {})
    if fit.get("start") != f"{year}-01-01" or fit.get("end") != f"{year}-06-30":
        reasons.append("M2_FIT_WINDOW_NOT_H1")
    if m2_manifest.get("reference_contract_id") != "YEAR_SPECIFIC_H1_M2_REFERENCES_V1":
        reasons.append("M2_REFERENCE_CONTRACT_MISMATCH")
    scales = m2_manifest.get("scale_median_preview", {})
    required_scales = {
        "F_continuity", "F_execution", "F_propagation", "P_time",
        "P_itinerary", "P_service", "R_operating",
    }
    if set(scales) != required_scales or any(float(scales[k]) <= 0 for k in required_scales):
        reasons.append("M2_SEVEN_DIMENSION_SCALE_INVALID")
    counts = manifest.get("cohort_audit", {}).get("cohort_counts", {})
    if any(int(counts.get(split, 0)) <= 0 for split in ("train", "calibration", "development")):
        reasons.append("ANNUAL_SPLIT_SUPPORT_INSUFFICIENT")
    if int(counts.get("test", 0)) != 0:
        reasons.append("TEST_COHORT_PRESENT_IN_DEVELOPMENT_INPUT")
    if int(split_audit.get("final_test_access_count", 0)) != 0:
        reasons.append("SPLIT_AUDIT_FINAL_TEST_ACCESS_NONZERO")
    m1 = _annual_m1_candidates(year)
    has_main_models = all(path.is_file() for path in m1)
    audit = {
        "required_paths": {name: str(path) for name, path in required.items()},
        "input_hashes": {name: _hash(path) for name, path in required.items() if path.is_file()},
        "cohort_counts": counts,
        "m2_scale_keys": sorted(scales),
        "m2_scale_positive": not any(float(scales.get(k, 0)) <= 0 for k in required_scales),
        "annual_m1_history_path": str(m1[0]),
        "annual_m1_current_path": str(m1[1]),
        "annual_m1_main_model_available": has_main_models,
        "pilot_n128_is_scientific_model": False,
        "final_test_access_count": 0,
        "reasons": reasons,
    }
    if not has_main_models:
        reasons.append("ANNUAL_M1_MAIN_MODEL_MISSING")
    status = "READY_TO_RUN" if not reasons else "ENGINEERING_INCOMPLETE"
    scientific_status = "READY_TO_RUN" if status == "READY_TO_RUN" else "DATA_INSUFFICIENT"
    return AnnualInputContract(year, status, scientific_status, pre_root, m2_root, manifest, m2_manifest, audit)


def audit_all_years(output: Path) -> dict[str, Any]:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = [validate_year(year).as_dict() for year in YEARS]
    payload = {
        "schema_version": "JATM_ANNUAL_INPUT_CONTRACT_V1",
        "status": (
            "READY_TO_RUN"
            if all(row["status"] == "READY_TO_RUN" for row in rows)
            else "PARTIAL_ENGINEERING_INCOMPLETE"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "years": rows,
        "final_test_access_count": 0,
    }
    target = output / "ANNUAL_INPUT_AUDIT.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


__all__ = ["AnnualInputContract", "YEARS", "audit_all_years", "validate_year"]
