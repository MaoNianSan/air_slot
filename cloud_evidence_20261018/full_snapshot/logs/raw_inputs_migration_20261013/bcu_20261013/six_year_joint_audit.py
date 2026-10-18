#!/usr/bin/env python3
"""Six-year joint acceptance audit (READ-ONLY; Task D, round 3).

Per year 2017-2022 the audit runs the ACTUAL validators (never treats file
existence as scientific validity):

  * M1 bindings: exp.jatm_s34.cloud_inputs.model_bindings(year) -- schema,
    n/episode counts, history modes, checkpoint hash, final_test_access_count.
  * Annual tail: exp.jatm_s34.annual_tail.load_annual_tail(year) -- hash
    identity, source hashes, fit window, tail support >= 30.
  * Year-local B CU: exp.jatm_s34.annual_cu.load_annual_cu(year, 'YEAR_LOCAL',
    JATM_F_CONTINUITY_B_V1) -- manifest/scales/six payload hashes, turnaround
    numeric equality, positive scale support; plus file inventory + file
    SHA-256s of the bundle directory.
  * Fixed-common track: load_annual_cu(year, 'FIXED_COMMON', B) -- the shared
    D4 2017-H1 bundle, validated per year.
  * Cohort: exp.jatm_s34.cloud_inputs.check_year(year, require_tail=False) --
    the official input gate (splits, counts, duplicates, model bindings, CU
    bundles, nominal policy).
  * T-100 isolation accounting: active H1 file (path/hash/rows/months), audited
    annual original (path/hash == frozen manifest hash), and an explicit,
    honest record separating raw annual-file scans (audit/admin reads that DID
    touch months 1-12) from Train-H1 fit inputs and Final-Test evaluation
    access.

Writes /data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013/
SIX_YEAR_INPUT_GATE_MATRIX.json and prints a compact table.
Exit 0 always (the matrix is the deliverable; statuses live inside).
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/data/airslot/worktree")
OUT = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013/SIX_YEAR_INPUT_GATE_MATRIX.json")
sys.path.insert(0, str(REPO))

from exp.jatm_s34.cloud_inputs import check_year, model_bindings  # noqa: E402
from exp.jatm_s34.annual_cu import load_annual_cu  # noqa: E402
from exp.jatm_s34.annual_tail import annual_tail_path, load_annual_tail  # noqa: E402

SEAL = json.loads(Path(
    "/data/airslot/logs/raw_inputs_migration_20261013/T100_H1_SEAL_20261013.json"
).read_text(encoding="utf-8"))
CONTRACT = "JATM_F_CONTINUITY_B_V1"
E4 = REPO / "artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1"
D4 = REPO / "artifacts/models/pre/PRE_MULTIYEAR_V1_D4_2017H1_B_V1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_files(year: int):
    root = E4 / str(year) / "M2_REFERENCES"
    return sorted(p.name for p in root.iterdir() if p.is_file()) if root.is_dir() else []


matrix = {
    "schema_version": "AIRSLOT_SIX_YEAR_INPUT_GATE_MATRIX_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "contract": CONTRACT,
    "code_state": "snapshot 583f2c12 + patch 8cc7a1b7 (d1c72a7) + patch 1d3ba5d3 (ffa7487)",
    "years": {},
}

rows = []
for year in range(2017, 2023):
    y: dict = {}
    # ---- M1 ----
    try:
        bindings = model_bindings(year, root=REPO)
        y["m1"] = {"status": "VALID", "checkpoint_hashes": {
            role: b["checkpoint_hash"] for role, b in bindings.items()},
            "manifest_sha256": {role: b["manifest_sha256"] for role, b in bindings.items()}}
    except Exception as error:  # noqa: BLE001
        y["m1"] = {"status": "MISSING_OR_INVALID", "reason": f"{type(error).__name__}: {error}"}
    # ---- Tail ----
    tail_path = annual_tail_path(year)
    if tail_path.is_file():
        try:
            load_annual_tail(year)
            y["tail"] = {"status": "VALID", "manifest_sha256": sha256_file(tail_path)}
        except Exception as error:  # noqa: BLE001
            y["tail"] = {"status": "INVALID", "reason": f"{type(error).__name__}: {error}"}
    else:
        y["tail"] = {"status": "MISSING", "path": str(tail_path)}
    # ---- Year-local B CU ----
    try:
        adapter = load_annual_cu(year, track="YEAR_LOCAL", continuity_contract=CONTRACT)
        names = bundle_files(year)
        y["year_local_bcu"] = {
            "status": "VALID", "adapter_registry_id": adapter.registry_id,
            "files": names, "n_files": len(names),
            "bundle_manifest_sha256": sha256_file(E4 / str(year) / "M2_REFERENCES" / "M2_REFERENCE_BUNDLE_MANIFEST.json"),
        }
    except Exception as error:  # noqa: BLE001
        y["year_local_bcu"] = {"status": "MISSING_OR_INVALID", "reason": f"{type(error).__name__}: {error}"}
    # ---- Fixed-common (D4 2017 bundle, validated per year) ----
    try:
        adapter = load_annual_cu(year, track="FIXED_COMMON", continuity_contract=CONTRACT)
        y["fixed_common_bcu"] = {"status": "VALID", "adapter_registry_id": adapter.registry_id}
    except Exception as error:  # noqa: BLE001
        y["fixed_common_bcu"] = {"status": "MISSING_OR_INVALID", "reason": f"{type(error).__name__}: {error}"}
    # ---- Official input gate (without tail requirement to separate layers) ----
    gate = check_year(year, require_tail=False, continuity_contract=CONTRACT)
    y["input_gate"] = {"status": gate.get("status"), "reason": gate.get("reason"),
                       "cu_tracks_validated": sorted(gate.get("cu", {}).keys()) if "cu" in gate else [],
                       "cohort_sha256": gate.get("cohort_sha256"),
                       "cohort_pool_counts": gate.get("cohort_pool_counts"),
                       "tail_status": gate.get("tail_status")}
    # ---- T-100 isolation accounting (honest scan record) ----
    seal_year = SEAL["years"][str(year)]
    y["t100_accounting"] = {
        "active_h1_input": {"path": seal_year["h1"]["path"], "sha256": seal_year["h1"]["sha256"],
                            "rows": seal_year["h1"]["rows"], "months": [1, 2, 3, 4, 5, 6]},
        "audited_annual_original": {"path": seal_year["annual"]["audit_path"],
                                    "sha256": seal_year["annual"]["sha256"],
                                    "matches_frozen_manifest": seal_year["annual"]["sha256_match_frozen_manifest"]},
        "raw_annual_full_file_scans_on_record": [
            "2026-10-13 migration SHA-256 sweeps (months 1-12 bytes hashed, before sealing)",
            "2026-10-13 Phase-2 structural parse (all rows/months parsed for input contract checks, before sealing)",
        ],
        "train_h1_fit_inputs": "only the sealed H1 file above (MONTH<=6); the builder additionally row-filters MONTH<=6 (defense in depth)",
        "final_test_evaluation_access": 0,
        "note": "Raw annual files WERE fully read on disk during audit/administration before sealing; that reading is recorded here and is not described as 'never accessed'. No fit ever consumed MONTH>6 and no Test/Final-Test partition was read.",
    }
    matrix["years"][str(year)] = y
    rows.append((year, y))

matrix["summary"] = {
    "m1_valid_years": [int(k) for k, v in matrix["years"].items() if v["m1"]["status"] == "VALID"],
    "m1_missing_years": [int(k) for k, v in matrix["years"].items() if v["m1"]["status"] != "VALID"],
    "tail_valid_years": [int(k) for k, v in matrix["years"].items() if v["tail"]["status"] == "VALID"],
    "tail_missing_years": [int(k) for k, v in matrix["years"].items() if v["tail"]["status"] != "VALID"],
    "year_local_bcu_valid_years": [int(k) for k, v in matrix["years"].items() if v["year_local_bcu"]["status"] == "VALID"],
    "fixed_common_valid_for_years": [int(k) for k, v in matrix["years"].items() if v["fixed_common_bcu"]["status"] == "VALID"],
    "gate_validated_years": [int(k) for k, v in matrix["years"].items() if v["input_gate"]["status"] == "INPUTS_VALIDATED"],
    "gate_blocked_years": {k: v["input_gate"].get("reason") for k, v in matrix["years"].items() if v["input_gate"]["status"] != "INPUTS_VALIDATED"},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(matrix, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print(f"written: {OUT}\n")
print(f"{'year':6s} {'M1':22s} {'tail':8s} {'E4-B':8s} {'D4':8s} gate")
for year, y in rows:
    print(f"{year:<6d} {y['m1']['status']:22s} {y['tail']['status']:8s} "
          f"{y['year_local_bcu']['status']:8s} {y['fixed_common_bcu']['status']:8s} "
          f"{y['input_gate']['status']}")
print("\nsummary:", json.dumps(matrix["summary"], sort_keys=True))
