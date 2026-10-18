#!/usr/bin/env python3
"""R1 empirical equivalence check (READ-ONLY, no writes anywhere).

On REAL 2017 H1 on-time data (first N canonicalizable rows of month=01):
  A) canonicalize_ontime_row: FlightRecord.scheduled_departure_utc == FlightRecord.event_start_time
     (the two keys of the canonical schedule; both assigned from the same
     schedule_dep variable in normalization_flights.py).
  B) iter_train_rows row contract (the rows consumed by
     compute_train_scales_continuity_b): "event_start_time" present and is a
     datetime; "scheduled_departure_utc" absent (the flat key never exists);
     "actual_arrival_utc"/"actual_departure_utc" present; and the row's
     event_start_time equals the FlightRecord.scheduled_departure_utc of the
     same flight.

Exit 0 iff every check passes.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

REPO = Path("/data/airslot/worktree")
sys.path.insert(0, str(REPO))

from model.PRE.canonical.normalization import canonicalize_ontime_row  # noqa: E402
from model.PRE.streaming.data2 import load_timezones  # noqa: E402
from model.PRE.reference.data2_m2_train_fit import (  # noqa: E402
    ONTIME_PROJECTED_FIELDS,
    iter_train_rows,
    ontime_paths,
)

LIMIT = 5000
zones = load_timezones(REPO / "data2" / "refs" / "us_airport_timezones.csv")
paths = ontime_paths(REPO, (1,), year=2017)
path = paths[0]
print(f"file: {path}")

# ---- A) FlightRecord-level equality on real rows --------------------------
a_rows = a_eq = a_neq = 0
expected: dict[str, datetime] = {}
with path.open(encoding="utf-8-sig", newline="", errors="replace") as fh:
    for raw in csv.DictReader(fh):
        if a_rows >= LIMIT:
            break
        try:
            schedule, _outcome = canonicalize_ontime_row(
                {k: raw.get(k, "") for k in ONTIME_PROJECTED_FIELDS}, zones
            )
        except Exception:
            continue
        a_rows += 1
        if schedule.scheduled_departure_utc == schedule.event_start_time:
            a_eq += 1
        else:
            a_neq += 1
        expected[schedule.flight_id] = schedule.scheduled_departure_utc
print(f"A FlightRecord rows={a_rows} equal={a_eq} neq={a_neq}")

# ---- B) iter_train_rows contract + cross-check ----------------------------
b_rows = has_est = has_sdu = miss_other = 0
b_eq = b_neq = non_dt = 0
for row in iter_train_rows(paths, zones, dataset_instance_id="data2_2017_2022"):
    if b_rows >= LIMIT:
        break
    b_rows += 1
    has_est += 1 if "event_start_time" in row else 0
    has_sdu += 1 if "scheduled_departure_utc" in row else 0
    miss_other += 0 if (
        "actual_arrival_utc" in row and "actual_departure_utc" in row
    ) else 1
    non_dt += 0 if isinstance(row["event_start_time"], datetime) else 1
    exp = expected.get(row["flight_id"])
    if exp is None:
        continue
    if row["event_start_time"] == exp:
        b_eq += 1
    else:
        b_neq += 1
print(
    f"B row-contract rows={b_rows} with_event_start_time={has_est} "
    f"with_flat_scheduled_departure_utc={has_sdu} missing_actuals={miss_other} "
    f"matches_FlightRecord={b_eq} mismatch={b_neq} non_datetime={non_dt}"
)

ok = (
    a_neq == 0 and b_neq == 0 and has_sdu == 0
    and has_est == b_rows and miss_other == 0 and non_dt == 0
    and a_rows == LIMIT and b_eq > 0
)
print("EQUIVALENCE_RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
