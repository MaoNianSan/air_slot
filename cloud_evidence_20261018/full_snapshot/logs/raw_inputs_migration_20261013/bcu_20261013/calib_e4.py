import json, sys
from pathlib import Path
REPO = Path("/data/airslot/worktree")
sys.path.insert(0, str(REPO))
from exp.jatm_s34.e4_run import run
R1 = REPO / "artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1"
out = REPO / "artifacts/experiment/jatm_s34/calibration_20261013/e4_n256"
result = run(repo=REPO, output_root=out, bundle_root=R1, years=(2019,), n_grid=(256,))
state = json.loads((out / "YEAR_2019" / "E4_YEAR_STATE.json").read_text(encoding="utf-8"))
chain_ok = state.get("completed_phases") == ["headroom", "fit", "ladder", "eval"]
print(json.dumps({"terminal_status": result.get("status"), "completion_class": state.get("completion_class"),
                  "eval_decision": state.get("eval_decision"), "n_grid_coverage": state.get("n_grid_coverage")}, indent=2, default=str))
print("E4_CALIB_RESULT:", "CHAIN_COMPLETE" if chain_ok else "INCOMPLETE")
sys.exit(0 if chain_ok else 1)
