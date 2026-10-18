#!/usr/bin/env python3
"""Bounded REAL-DATA smoke for the fixed F_continuity expression (READ-ONLY).

Runs ``compute_train_scales_continuity_b`` over real Y-H1-month on-time rows
(month=01 of the given year) with the five delegated scales stubbed and a
placeholder turnaround reference (global 41.0 min, cells=()).  This proves the
repaired field access computes over real episodes without KeyError; it is a
smoke check, NOT a scientific artifact, and writes nothing.

Usage: python R2_FIX_SMOKE.py <repo_root> [year] [path_mode]
"""
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/airslot/worktree")
YEAR = int(sys.argv[2]) if len(sys.argv) > 2 else 2017
sys.path.insert(0, str(REPO))

from model.PRE.streaming.data2 import load_timezones  # noqa: E402
from model.PRE.reference import data2_m2_train_fit as fit  # noqa: E402

zones = load_timezones(REPO / "data2" / "refs" / "us_airport_timezones.csv")
paths = fit.ontime_paths(REPO, (1,), year=YEAR)
rows = list(fit.iter_train_rows(paths, zones,
                                dataset_instance_id="data2_2017_2022"))
print(f"real rows {YEAR}-01: {len(rows)}")
if not rows:
    print("SMOKE_RESULT: FAIL (no rows)")
    raise SystemExit(1)

fit.compute_train_scales = lambda *a, **k: {}  # delegate stub (smoke only)


class _TurnRef:
    cells = ()
    global_value_minutes = 41.0


out = fit.compute_train_scales_continuity_b(rows, {}, turnaround_ref=_TurnRef())
entry = out["F_continuity"]
print("F_continuity:", {k: entry[k] for k in
                        ("median", "population_rows", "positive_n", "unit",
                         "definition", "continuity_contract")})
nested = sum(1 for row in rows if "scheduled_departure_utc" in row)
print(f"rows carrying the flat scheduled_departure_utc key: {nested}")
ok = entry["positive_n"] > 0 and nested == 0
print("SMOKE_RESULT:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
