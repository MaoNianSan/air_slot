import json, sys
from pathlib import Path
REPO = Path("/data/airslot/worktree"); sys.path.insert(0, str(REPO))
from exp.jatm_s34.e1_information_gain import run_bounded_annual
year = int(sys.argv[1])
out = REPO / f"artifacts/experiment/jatm_s34/full_20261013/e1/{year}"
result = run_bounded_annual(output_root=out, year=year, n=4096, chunk_size=64, node_limit=None, bootstrap_replicates=2000)
summary = json.loads((out / "E1_SUMMARY.json").read_text(encoding="utf-8"))
print(json.dumps({k: summary.get(k) for k in ("schema_version","status","chunk_count","chunk_size","node_count","final_test_access_count") if k in summary}, indent=2))
print("E1_FULL_RESULT:", summary.get("status"))
sys.exit(0 if summary.get("status") == "DEVELOPMENT_COMPLETE" else 1)
