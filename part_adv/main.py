from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from downstream_common import resolve_requested_n_jobs
from src.pipeline import report, run, validate


def main() -> int:
    p=argparse.ArgumentParser(description="Air Slot part-wise advantage experiments")
    p.add_argument("command",choices=["validate","fast","diagnostic","full","adapt_full","precision","report"])
    p.add_argument("--mode",choices=["fast","diagnostic","full","adapt_full","precision"],default=None)
    p.add_argument("--progress",choices=["quiet","normal","detail"],default="normal")
    p.add_argument("--config",type=Path,default=None)
    p.add_argument("--n-jobs",type=int,default=None,help="Runtime CPU budget; default 1, -1 uses all but one logical CPU")
    p.add_argument("--resume",action="store_true",help="Resume a hash-valid incomplete mode output")
    a=p.parse_args()
    if a.command in {"validate", "report"} and a.mode is None:
        p.error("--mode is required for validate and report")
    mode=a.command if a.command in {"fast","diagnostic","full","adapt_full","precision"} else a.mode
    try:
        requested_n_jobs=resolve_requested_n_jobs(a.n_jobs,1)
        result=validate(mode,a.config) if a.command=="validate" else (report(mode) if a.command=="report" else run(mode,a.progress,a.config,requested_n_jobs=requested_n_jobs,resume=a.resume));print(json.dumps(result,indent=2,default=str));return 0
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}",file=sys.stderr)
        if a.progress=="detail":raise
        return 1
if __name__=="__main__":raise SystemExit(main())
