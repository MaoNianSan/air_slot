import json, sys
from pathlib import Path
REPO = Path("/data/airslot/worktree")
sys.path.insert(0, str(REPO))
from exp.jatm_s34.e4_run import run
R1 = REPO / "artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1"
out = REPO / "artifacts/experiment/jatm_s34/pilot_20261013/e4_2019_r2"
result = run(repo=REPO, output_root=out, bundle_root=R1, years=(2019,), n_grid=(128,))
print(json.dumps({k: result.get(k) for k in ("status", "n_grid") if k in result}, indent=2, default=str))
state = json.loads((out / "YEAR_2019" / "E4_YEAR_STATE.json").read_text(encoding="utf-8"))
print("E4_YEAR_STATE:", json.dumps({k: state.get(k) for k in ("status", "completed_phases", "resumed_from_checkpoint")}, default=str))
print("E4_PILOT_RESULT:", result.get("status"))
sys.exit(0 if result.get("status") == "DEVELOPMENT_COMPLETE" else 1)
