import hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
B = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013")
REPO = Path("/data/airslot/worktree")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
gate = json.loads((B / "SIX_YEAR_INPUT_GATE_FINAL.json").read_text(encoding="utf-8"))
reg = json.loads((B / "SIX_YEAR_INPUTS_VALIDATED.json").read_text(encoding="utf-8"))
per_year = {}
ok = True
for y in map(str, range(2017, 2023)):
    g = gate["years"][y]
    row = {"m1": g["m1"]["status"], "tail": g["tail"]["status"], "bcu": g["year_local_bcu"]["status"],
           "d4": g["fixed_common_bcu"]["status"], "gate": g["input_gate"]["status"]}
    per_year[y] = row
    if not (row == {"m1": "VALID", "tail": "VALID", "bcu": "VALID", "d4": "VALID", "gate": "INPUTS_VALIDATED"}):
        ok = False
ps = subprocess.run(["pgrep", "-af", "full_e4|full_e2e3|full_e1|pilot_|sampler|consequence"], capture_output=True, text=True)
payload = {
    "schema_version": "AIRSLOT_FULL_EXECUTION_PRECHECK_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "inputs_validated": bool(gate["all_inputs_validated"]) and reg["years"] == [2017, 2018, 2019, 2020, 2021, 2022],
    "per_year": per_year,
    "all_valid": ok,
    "final_test_access_count": 0,
    "code_snapshot": json.loads((REPO / "CODE_SNAPSHOT.json").read_text(encoding="utf-8")),
    "patched_file_sha256": {
        "model/PRE/reference/data2_m2_train_fit.py": sha(REPO / "model/PRE/reference/data2_m2_train_fit.py"),
        "data2/scripts/build_year_references.py": sha(REPO / "data2/scripts/build_year_references.py"),
    },
    "patch_chain": ["8cc7a1b7bfa727334e962d24728d9554eb4f579e440612ee54f43d50f40468ec",
                    "1d3ba5d32b243773201eb924aa1a3aca6fe1443ead60af6184d872b03a02fdbb"],
    "registry_frozen_sha256": "sha256:befc3ae161cc40325d379ac61d72358e7dfc068465cb82dceca1ff66df59e1ca",
    "authorization": "FULL_EXPERIMENT_EXECUTION_AUTHORIZATION_USER_APPROVED_V1.json",
    "residual_processes_precheck": ps.stdout.strip(),
}
(B / "FULL_EXECUTION_PRECHECK.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("written FULL_EXECUTION_PRECHECK.json | inputs_validated:", payload["inputs_validated"],
      "| all_valid:", payload["all_valid"], "| fta:", payload["final_test_access_count"],
      "| residual:", payload["residual_processes_precheck"] or "NONE")
