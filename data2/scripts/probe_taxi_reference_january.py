from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
CSV = next((ROOT / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv"))
ZONES = ROOT / "refs" / "us_airport_timezones.csv"

import sys
sys.path.insert(0, str(ROOT.parent))

from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.reference.taxi_data2 import build_data2_taxi_reference

with ZONES.open(encoding="utf-8-sig", newline="") as fh:
    timezones = {row["iata"]: row["timezone"] for row in csv.DictReader(fh)}

PROJECTED = ["FlightDate", "Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline",
             "Origin", "Dest", "CRSDepTime", "CRSArrTime", "DepTime", "ArrTime",
             "WheelsOff", "WheelsOn", "TaxiOut", "TaxiIn", "DepDelayMinutes",
             "ArrDelayMinutes", "Cancelled", "Diverted"]

rows = []
skipped = 0
no_taxi = 0
with CSV.open(encoding="utf-8-sig", newline="", errors="replace") as fh:
    reader = csv.DictReader(fh)
    for raw in reader:
        try:
            schedule, outcome = canonicalize_ontime_row({k: raw.get(k, "") for k in PROJECTED}, timezones)
        except Exception:
            skipped += 1
            continue
        if schedule.aircraft_id is None or outcome.cancelled or outcome.diverted:
            skipped += 1
            continue
        if outcome.taxi_out_minutes is None:
            no_taxi += 1
            continue
        rows.append({
            "dataset_instance_id": schedule.dataset_instance_id,
            "aircraft_id": schedule.aircraft_id,
            "flight_id": schedule.flight_id,
            "origin_airport_id": schedule.origin_airport_id,
            "taxi_out_minutes": outcome.taxi_out_minutes,
            "split": "train",
        })

ref = build_data2_taxi_reference(rows, fit_period="2019-01")
cells_local = [c for c in ref.cells if c.fallback_level == "AIRPORT_CELL"]
cells_global = [c for c in ref.cells if c.fallback_level == "GLOBAL"]
top = sorted(cells_local, key=lambda c: -c.sample_count)[:10]
print("flights_eligible=", len(rows))
print("skipped_canonical=", skipped)
print("missing_taxi_out=", no_taxi)
print("reference_id=", ref.reference_id)
print("global_value_minutes=", ref.global_value_minutes)
print("global_sample_count=", ref.global_sample_count)
print("airports_total_cells=", len(ref.cells))
print("airports_cell_median=", len(cells_local))
print("airports_global_fallback=", len(cells_global))
print("top_airports=", ", ".join(f"{c.airport_id}:{c.value_minutes:.0f}min(n={c.sample_count})" for c in top))
print("rule=", ref.rule_id, ref.rule_version)
print("support=", ref.support_state.value)
print("PROBE_D2_4_JANUARY=DONE")