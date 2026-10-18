import json, sys
from pathlib import Path
REPO = Path("/data/airslot/worktree"); sys.path.insert(0, str(REPO))
from exp.jatm_s34.e4_run import run
year = int(sys.argv[1])
R1 = REPO / "artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1"
out = REPO / f"artifacts/experiment/jatm_s34/full_20261013/e4/{year}"
result = run(repo=REPO, output_root=out, bundle_root=R1, years=(year,), n_grid=(128, 256, 512, 1024, 2048, 4096))
state = json.loads((out / f"YEAR_{year}" / "E4_YEAR_STATE.json").read_text(encoding="utf-8"))
chain_ok = state.get("completed_phases") == ["headroom", "fit", "ladder", "eval"]
print(json.dumps({"year": year, "terminal_status": result.get("status"), "completion_class": state.get("completion_class"),
                  "eval_decision": state.get("eval_decision"), "n_grid_coverage": state.get("n_grid_coverage")}, indent=2, default=str))
print("E4_FULL_RESULT:", "CHAIN_COMPLETE" if chain_ok else "INCOMPLETE")
sys.exit(0 if chain_ok else 1)
