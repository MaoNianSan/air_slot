#!/usr/bin/env python3
"""Deep per-year B CU verification + optional PASS registration (read-only on
fit outputs; writes only the verification JSON and, with --register, the
registration record when every check passes).

Usage:
  verify_year_bcu.py <repo_root> <track:YEAR_LOCAL|FIXED_COMMON> <year> \
      <output_root_rel> <out_dir> [--register]

Checks:
  1. Official acceptance: exp.jatm_s34.annual_cu.load_annual_cu(year, track,
     JATM_F_CONTINUITY_B_V1) -- validates the bundle manifest, the seven
     scales, all six reference payload hashes, the turnaround numeric
     equality against the frozen year reference, and positive scale support.
  2. File inventory: exactly the 6 reference payloads + scales + bundle
     manifest, with SHA-256 recorded.
  3. Bundle manifest fields: year / dataset_instance_id / reference_contract_id
     / fit_window / t100_admissibility / db1b_admissibility / payload hash
     re-computation / scale median preview / rotation-exclusion count /
     continuity contract.
  4. Seven-component scales: B schema, exactly 7 components, F_continuity
     definition/driver/contract, bundle_hash re-computation, positive support.
  5. Per-payload provenance: experiment_year / fit_start / fit_end /
     dataset_instance_id / reference_contract_id / reference_kind /
     artifact_hash re-computation.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
TRACK = sys.argv[2]
YEAR = int(sys.argv[3])
OUTROOT = sys.argv[4]
OUTDIR = Path(sys.argv[5]).resolve()
REGISTER = "--register" in sys.argv[6:]
sys.path.insert(0, str(REPO))

from data2.scripts.build_year_references import sha256_json  # noqa: E402
from exp.jatm_s34.annual_cu import load_annual_cu  # noqa: E402

problems: list[str] = []
summary: dict = {"track": TRACK, "year": YEAR, "output_root": OUTROOT}
root = REPO / OUTROOT / str(YEAR) / "M2_REFERENCES"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---- 1) official acceptance -------------------------------------------------
try:
    adapter = load_annual_cu(YEAR, track=TRACK,
                             continuity_contract="JATM_F_CONTINUITY_B_V1")
    summary["official_acceptance"] = "PASS"
    summary["adapter_registry_id"] = adapter.registry_id
    summary["adapter_registry_hash"] = adapter.registry_hash
    summary["provenance"] = adapter.provenance
except Exception as error:  # noqa: BLE001
    problems.append(f"load_annual_cu FAILED: {type(error).__name__}: {error}")
    summary["official_acceptance"] = "FAIL"

# ---- 2) file inventory ------------------------------------------------------
kinds = ("taxi", "turnaround", "downstream_exposure", "passenger",
         "expected_passengers", "connection_share")
expected_names = {f"M2_{kind.upper()}_REFERENCE_{YEAR}-H1.json" for kind in kinds}
expected_names |= {"M2_SEVEN_COMPONENT_TRAIN_SCALES.json",
                   "M2_REFERENCE_BUNDLE_MANIFEST.json"}
file_hashes: dict[str, str] = {}
if not root.is_dir():
    problems.append(f"M2_REFERENCES directory missing: {root}")
else:
    names = sorted(p.name for p in root.iterdir() if p.is_file())
    summary["files"] = names
    if set(names) != expected_names:
        problems.append(f"FILE_SET_MISMATCH missing={sorted(expected_names - set(names))} "
                        f"extra={sorted(set(names) - expected_names)}")
    for name in names:
        file_hashes[name] = sha256_file(root / name)
    summary["file_sha256"] = file_hashes

# ---- 3) bundle manifest -----------------------------------------------------
manifest = None
manifest_path = root / "M2_REFERENCE_BUNDLE_MANIFEST.json"
if manifest_path.is_file():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exp = {"schema_version": "M2_REFERENCE_BUNDLE_V1", "year": YEAR,
           "dataset_instance_id": "data2_2017_2022",
           "reference_contract_id": "YEAR_SPECIFIC_H1_M2_REFERENCES_V1",
           "continuity_contract": "JATM_F_CONTINUITY_B_V1",
           "t100_admissibility": "YEAR == Y and MONTH <= 6",
           "db1b_admissibility": "Q1 + Q2 of Y",
           "fit_window": {"start": f"{YEAR}-01-01", "end": f"{YEAR}-06-30"}}
    for key, value in exp.items():
        if manifest.get(key) != value:
            problems.append(f"MANIFEST_{key.upper()}_MISMATCH: {manifest.get(key)!r} != {value!r}")
    if len(manifest.get("payload_hashes", {})) != 6:
        problems.append("MANIFEST_PAYLOAD_HASHES_NOT_6")
    for kind in kinds:
        path = root / f"M2_{kind.upper()}_REFERENCE_{YEAR}-H1.json"
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            recorded = manifest.get("payload_hashes", {}).get(kind)
            if sha256_json(payload) != recorded:
                problems.append(f"PAYLOAD_HASH_MISMATCH:{kind}")
    if not isinstance(manifest.get("non_physical_rotation_flights_excluded"), int):
        problems.append("MANIFEST_ROTATION_EXCLUSION_MISSING")
    summary["bundle_manifest"] = manifest

# ---- 4) scales --------------------------------------------------------------
scales_path = root / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json"
if scales_path.is_file():
    scales_payload = json.loads(scales_path.read_text(encoding="utf-8"))
    if scales_payload.get("schema_version") != "M2_DATA2_TRAIN_SCALES_B_V1":
        problems.append("SCALES_SCHEMA_MISMATCH")
    if scales_payload.get("continuity_contract") != "JATM_F_CONTINUITY_B_V1":
        problems.append("SCALES_CONTRACT_MISMATCH")
    if scales_payload.get("experiment_year") != YEAR:
        problems.append("SCALES_YEAR_MISMATCH")
    scales = scales_payload.get("scales", {})
    if len(scales) != 7:
        problems.append(f"SCALES_COUNT {len(scales)} != 7")
    fcont = scales.get("F_continuity", {})
    if fcont.get("definition") != "max(0, T_IB + turnaround_reference - SOBT)":
        problems.append("F_CONTINUITY_DEFINITION_MISMATCH")
    if fcont.get("continuity_contract") != "JATM_F_CONTINUITY_B_V1":
        problems.append("F_CONTINUITY_CONTRACT_MISMATCH")
    if fcont.get("driver") != "planned_connection_time_gap":
        problems.append("F_CONTINUITY_DRIVER_MISMATCH")
    if not (isinstance(fcont.get("positive_n"), int) and fcont["positive_n"] > 0):
        problems.append("F_CONTINUITY_POSITIVE_SUPPORT_MISSING")
    recomputed = sha256_json({k: v for k, v in scales_payload.items()
                              if k != "bundle_hash"})
    if recomputed != scales_payload.get("bundle_hash"):
        problems.append("SCALES_BUNDLE_HASH_MISMATCH")
    if manifest is not None:
        for name, entry in scales.items():
            if entry.get("median") != manifest.get("scale_median_preview", {}).get(name):
                problems.append(f"SCALE_MEDIAN_PREVIEW_MISMATCH:{name}")
    summary["scales"] = {name: {"median": entry.get("median"),
                                "positive_n": entry.get("positive_n")}
                         for name, entry in scales.items()}
else:
    problems.append("scales file missing")

# ---- 5) per-payload provenance ---------------------------------------------
for kind in kinds:
    path = root / f"M2_{kind.upper()}_REFERENCE_{YEAR}-H1.json"
    if not path.is_file():
        continue
    payload = json.loads(path.read_text(encoding="utf-8"))
    exp = {"experiment_year": YEAR, "fit_start": f"{YEAR}-01-01",
           "fit_end": f"{YEAR}-06-30", "dataset_instance_id": "data2_2017_2022",
           "reference_contract_id": "YEAR_SPECIFIC_H1_M2_REFERENCES_V1",
           "reference_kind": kind}
    for key, value in exp.items():
        if payload.get(key) != value:
            problems.append(f"PROVENANCE_{kind.upper()}_{key.upper()}_MISMATCH")
    stored = payload.get("artifact_hash")
    recomputed = sha256_json({k: v for k, v in payload.items() if k != "artifact_hash"})
    if stored != recomputed:
        problems.append(f"ARTIFACT_HASH_MISMATCH:{kind}")

summary["problems"] = problems
summary["status"] = "PASS" if not problems else "FAIL"
summary["verified_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

OUTDIR.mkdir(parents=True, exist_ok=True)
tag = f"{TRACK}_{YEAR}_B_CU" if TRACK == "YEAR_LOCAL" else "D4_2017H1_B_CU"
(OUTDIR / f"{tag}_VERIFICATION.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
    encoding="utf-8")

if REGISTER:
    if problems:
        (OUTDIR / f"{tag}_REGISTRATION_BLOCKED.json").write_text(
            json.dumps({"status": "NOT_REGISTERED", "problems": problems},
                       indent=2) + "\n", encoding="utf-8")
    else:
        registration = {
            "schema_version": "AIRSLOT_B_CU_PASS_REGISTRATION_V1",
            "tag": f"{tag}_PASS",
            "track": TRACK, "year": YEAR,
            "output_root": OUTROOT,
            "bundle_manifest_sha256": sha256_file(manifest_path),
            "file_sha256": file_hashes,
            "adapter_registry_id": summary.get("adapter_registry_id"),
            "adapter_registry_hash": summary.get("adapter_registry_hash"),
            "official_acceptance": "PASS",
            "verified_at_utc": summary["verified_at_utc"],
        }
        (OUTDIR / f"{tag}_PASS.json").write_text(
            json.dumps(registration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")

print(json.dumps({"tag": tag, "status": summary["status"],
                  "n_problems": len(problems), "problems": problems},
                 indent=2, default=str))
sys.exit(0 if not problems else 1)
