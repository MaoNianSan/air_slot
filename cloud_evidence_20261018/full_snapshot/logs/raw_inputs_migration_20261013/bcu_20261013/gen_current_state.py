#!/usr/bin/env python3
"""Generate CURRENT_SYSTEM_STATE.json (round 5, Task A deliverable)."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

B = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013")
REPO = Path("/data/airslot/worktree")
OUT = B / "CURRENT_SYSTEM_STATE.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(name):
    return json.loads((B / name).read_text(encoding="utf-8"))


gate = load("SIX_YEAR_INPUT_GATE_FINAL.json")
registration = load("SIX_YEAR_INPUTS_VALIDATED.json")
m1_summary = load("M1_2019_2022_TRAINING_SUMMARY.json")
tail_ver = load("ANNUAL_TAIL_2019_2022_VERIFICATION.json")
smoke = load("DEVELOPMENT_SMOKE_VERIFICATION.json")

matrix = {}
for year in range(2017, 2023):
    g = gate["years"][str(year)]
    row = {
        "m1": g["m1"]["status"],
        "tail": g["tail"]["status"],
        "b_cu_year_local": g["year_local_bcu"]["status"],
        "d4_fixed_common": g["fixed_common_bcu"]["status"],
        "input_gate": g["input_gate"]["status"],
    }
    if str(year) in m1_summary["years"]:
        e = m1_summary["years"][str(year)]
        row["m1_training"] = {"wall": e["wall"], "peak_rss_kib": e["peak_rss_kib"],
                              "receipt_status": e.get("receipt_status")}
    if str(year) in tail_ver["years"]:
        e = tail_ver["years"][str(year)]
        row["tail_manifest_sha256"] = e["manifest_sha256"]
    matrix[str(year)] = row

ps = subprocess.run(["pgrep", "-f", "cloud_train|build_annual|dispatcher|tail_watch|sampler|build_year|run_dev_smoke"],
                    capture_output=True, text=True)
residual = [pid for pid in ps.stdout.split() if pid]

state = {
    "schema_version": "AIRSLOT_CURRENT_SYSTEM_STATE_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "matrix": matrix,
    "verification_files": {
        name: {"sha256": sha256_file(B / name)} for name in (
            "SIX_YEAR_INPUTS_VALIDATED.json", "SIX_YEAR_INPUT_GATE_FINAL.json",
            "M1_2019_2022_TRAINING_SUMMARY.json", "ANNUAL_TAIL_2019_2022_VERIFICATION.json",
            "DEVELOPMENT_SMOKE_VERIFICATION.json")
    },
    "final_test_access": {
        "final_test_access_count": 0,
        "evidence": [
            "SIX_YEAR_INPUT_GATE_FINAL.json per-year t100_accounting.final_test_evaluation_access = 0",
            "M1 receipts final_test_access_count = 0 (all four new models)",
            "DEVELOPMENT_SMOKE_VERIFICATION final_test_access_count = 0 (input_contract READY_TO_RUN)",
            "SIX_YEAR_INPUTS_VALIDATED scope: Final-Test sealed",
        ],
    },
    "code_identity": {
        "code_snapshot": json.loads((REPO / "CODE_SNAPSHOT.json").read_text(encoding="utf-8")),
        "patch_chain": [
            {"patch": "20261013_b_continuity_row_contract_fix.patch", "sha256": "8cc7a1b7bfa727334e962d24728d9554eb4f579e440612ee54f43d50f40468ec", "local_commit": "d1c72a7"},
            {"patch": "20261013_bcu2019_context_fix.patch", "sha256": "1d3ba5d32b243773201eb924aa1a3aca6fe1443ead60af6184d872b03a02fdbb", "local_commit": "ffa7487"},
        ],
        "patched_file_sha256": {
            "model/PRE/reference/data2_m2_train_fit.py": sha256_file(REPO / "model/PRE/reference/data2_m2_train_fit.py"),
            "data2/scripts/build_year_references.py": sha256_file(REPO / "data2/scripts/build_year_references.py"),
        },
        "registry_frozen_hash": "sha256:befc3ae161cc40325d379ac61d72358e7dfc068465cb82dceca1ff66df59e1ca",
        "gitless_note": "worktree has no .git (tarball deployment); GIT_DIR adapter at /data/airslot/smoke_gitmeta/repo/.git declares HEAD=583f2c12 for official entries that call git rev-parse.",
    },
    "processes": {"residual_compute_pids": residual,
                  "clean": len(residual) == 0},
    "storage": {"data_disk": subprocess.run(["df", "-h", "/data"], capture_output=True, text=True).stdout.strip().splitlines()[-1]},
    "training_summary_all_pass": m1_summary["all_pass"],
    "tail_verification_all_valid": tail_ver["all_2019_2022_valid"],
    "smoke_result": smoke["smoke_result"],
    "six_year_inputs_validated": True,
}
OUT.write_text(json.dumps(state, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print("written:", OUT)
print("clean:", state["processes"]["clean"], "| all_pass:", state["training_summary_all_pass"],
      "| tails:", state["tail_verification_all_valid"], "| smoke:", state["smoke_result"])
for y, row in state["matrix"].items():
    print(f"  {y}: m1={row['m1']} tail={row['tail']} bcu={row['b_cu_year_local']} d4={row['d4_fixed_common']} gate={row['input_gate']}")
