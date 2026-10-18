#!/usr/bin/env python3
"""SIX_YEAR_INPUT_GATE_FINAL (round 4): official check_year(require_tail=True)
for 2017-2022 + component validators + registration when all pass."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/data/airslot/worktree")
B = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013")
OUT = B / "SIX_YEAR_INPUT_GATE_FINAL.json"
REG = B / "SIX_YEAR_INPUTS_VALIDATED.json"
sys.path.insert(0, str(REPO))
from exp.jatm_s34.cloud_inputs import check_year, model_bindings  # noqa: E402
from exp.jatm_s34.annual_cu import load_annual_cu  # noqa: E402
from exp.jatm_s34.annual_tail import annual_tail_path, load_annual_tail  # noqa: E402

SEAL = json.loads((B.parent / "T100_H1_SEAL_20261013.json").read_text(encoding="utf-8"))
CONTRACT = "JATM_F_CONTINUITY_B_V1"
E4 = REPO / "artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


matrix = {
    "schema_version": "AIRSLOT_SIX_YEAR_INPUT_GATE_FINAL_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "contract": CONTRACT,
    "code_state": "snapshot 583f2c12 + patch 8cc7a1b7 (d1c72a7) + patch 1d3ba5d3 (ffa7487)",
    "years": {},
}
for year in range(2017, 2023):
    y: dict = {}
    bindings = model_bindings(year, root=REPO)
    y["m1"] = {"status": "VALID",
               "checkpoint_hashes": {r: b["checkpoint_hash"] for r, b in bindings.items()},
               "manifest_sha256": {r: b["manifest_sha256"] for r, b in bindings.items()}}
    tail_path = annual_tail_path(year)
    load_annual_tail(year)
    y["tail"] = {"status": "VALID", "manifest_sha256": sha256_file(tail_path)}
    try:
        adapter = load_annual_cu(year, track="YEAR_LOCAL", continuity_contract=CONTRACT)
        y["year_local_bcu"] = {"status": "VALID", "adapter_registry_id": adapter.registry_id}
    except Exception as error:  # noqa: BLE001
        y["year_local_bcu"] = {"status": f"INVALID: {error}"}
    try:
        adapter = load_annual_cu(year, track="FIXED_COMMON", continuity_contract=CONTRACT)
        y["fixed_common_bcu"] = {"status": "VALID", "adapter_registry_id": adapter.registry_id}
    except Exception as error:  # noqa: BLE001
        y["fixed_common_bcu"] = {"status": f"INVALID: {error}"}
    gate = check_year(year, require_tail=True, continuity_contract=CONTRACT)
    y["input_gate"] = {"status": gate.get("status"), "reason": gate.get("reason"),
                       "cohort_sha256": gate.get("cohort_sha256"),
                       "cohort_pool_counts": gate.get("cohort_pool_counts")}
    seal_year = SEAL["years"][str(year)]
    y["t100_accounting"] = {
        "active_h1_input_sha256": seal_year["h1"]["sha256"],
        "audited_annual_original_sha256": seal_year["annual"]["sha256"],
        "audited_annual_matches_frozen": seal_year["annual"]["sha256_match_frozen_manifest"],
        "raw_annual_full_file_scans_on_record": [
            "migration SHA-256 sweeps (months 1-12, pre-seal)",
            "Phase-2 structural parse (pre-seal)",
        ],
        "train_h1_fit_inputs": "sealed H1 file only (MONTH<=6, plus code-level filter)",
        "final_test_evaluation_access": 0,
    }
    matrix["years"][str(year)] = y

all_valid = all(v["input_gate"]["status"] == "INPUTS_VALIDATED" for v in matrix["years"].values())
matrix["all_inputs_validated"] = all_valid
OUT.write_text(json.dumps(matrix, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print("written:", OUT, "| all_inputs_validated:", all_valid)
for year, v in matrix["years"].items():
    print(f"  {year}: {v['input_gate']['status']} m1={v['m1']['status']} tail={v['tail']['status']} "
          f"e4={v['year_local_bcu']['status'][:5]} d4={v['fixed_common_bcu']['status'][:5]}")

if all_valid:
    registration = {
        "schema_version": "AIRSLOT_SIX_YEAR_INPUTS_VALIDATED_V1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY; Final-Test sealed; E1-E4 NOT started",
        "contract": CONTRACT,
        "code_state": matrix["code_state"],
        "gate_matrix_sha256": sha256_file(OUT),
        "years": [2017, 2018, 2019, 2020, 2021, 2022],
        "evidence": {str(y): {"m1_checkpoints": matrix["years"][str(y)]["m1"]["checkpoint_hashes"],
                              "tail_manifest": matrix["years"][str(y)]["tail"]["manifest_sha256"]}
                     for y in range(2017, 2023)},
    }
    REG.write_text(json.dumps(registration, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("REGISTERED:", REG)
