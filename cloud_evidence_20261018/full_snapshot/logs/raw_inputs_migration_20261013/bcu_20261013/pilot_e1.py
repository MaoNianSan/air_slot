import json, sys
from pathlib import Path
REPO = Path("/data/airslot/worktree")
sys.path.insert(0, str(REPO))
from exp.jatm_s34.e1_information_gain import run_bounded_annual
out = REPO / "artifacts/experiment/jatm_s34/pilot_20261013/e1_2019"
result = run_bounded_annual(output_root=out, year=2019, n=4096, chunk_size=4, node_limit=128)
summary = json.loads((out / "E1_SUMMARY.json").read_text(encoding="utf-8"))
keys = ("schema_version", "status", "node_count", "final_test_access_count", "bounded_memory", "chunk_size")
print(json.dumps({k: summary.get(k) for k in keys if k in summary}, indent=2, default=str))
print("E1_PILOT_RESULT:", summary.get("status"))
sys.exit(0 if summary.get("status") == "DEVELOPMENT_COMPLETE" else 1)
