import json, sys
from pathlib import Path
REPO = Path("/data/airslot/worktree")
sys.path.insert(0, str(REPO))
from exp.jatm_s34.e2_e3_exact import run_bounded_annual
out = REPO / "artifacts/experiment/jatm_s34/calibration_20261013/e2e3_c64"
result = run_bounded_annual(output_root=out, year=2019, n=4096, chunk_size=64, node_limit=128, bootstrap_replicates=2000)
summary = json.loads((out / "E2_E3_SUMMARY.json").read_text(encoding="utf-8"))
print(json.dumps({k: summary.get(k) for k in ("schema_version","status","chunk_count","second_pass_chunk_count","chunk_size","node_count","final_test_access_count") if k in summary}, indent=2))
print("E2E3_CALIB_RESULT:", summary.get("status"))
sys.exit(0 if summary.get("status") == "DEVELOPMENT_COMPLETE" else 1)
