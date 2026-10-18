from pathlib import Path
import csv
import statistics

ROOT = Path(__file__).resolve().parents[1]
CSV = next((ROOT / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv"))
ZONES = ROOT / "refs" / "us_airport_timezones.csv"

import sys
sys.path.insert(0, str(ROOT.parent))

from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.episode.builder import build_data2_episode_records, DATA2_CHAIN_RULE_ID

with ZONES.open(encoding="utf-8-sig", newline="") as fh:
    timezones = {row["iata"]: row["timezone"] for row in csv.DictReader(fh)}

PROJECTED = ["FlightDate", "Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline",
             "Origin", "Dest", "CRSDepTime", "CRSArrTime", "DepTime", "ArrTime",
             "WheelsOff", "WheelsOn", "TaxiOut", "TaxiIn", "DepDelayMinutes",
             "ArrDelayMinutes", "Cancelled", "Diverted"]

rows = []
skipped = 0
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
        rows.append({
            "flight_id": schedule.flight_id,
            "aircraft_id": schedule.aircraft_id,
            "aircraft_id_namespace": schedule.aircraft_id_namespace,
            "origin_airport_id": schedule.origin_airport_id,
            "destination_airport_id": schedule.destination_airport_id,
            "event_start_time": schedule.event_start_time,
            "event_end_time": schedule.event_end_time,
            "actual_arrival_utc": outcome.actual_arrival_utc,
            "actual_departure_utc": outcome.actual_departure_utc,
            "dataset_instance_id": schedule.dataset_instance_id,
        })

by_id = {r["flight_id"]: r for r in rows}

# all actual-gap-linked candidate pairs (same sort order as the builder)
ordered = sorted(rows, key=lambda r: (
    r["dataset_instance_id"], r["aircraft_id_namespace"], r["aircraft_id"],
    r["actual_departure_utc"], r["actual_arrival_utc"], r["flight_id"]))
candidates = []
for pred, succ in zip(ordered, ordered[1:]):
    if (pred["aircraft_id"], pred["aircraft_id_namespace"]) != (succ["aircraft_id"], succ["aircraft_id_namespace"]):
        continue
    if pred["destination_airport_id"] != succ["origin_airport_id"]:
        continue
    if pred["actual_arrival_utc"] >= succ["actual_departure_utc"]:
        continue
    gap = (succ["actual_departure_utc"] - pred["actual_arrival_utc"]).total_seconds() / 60
    if gap <= 0 or gap > 360:
        continue
    candidates.append((pred, succ, gap))

inverted_full_interval = sum(1 for p, s, _ in candidates if p["event_start_time"] >= s["event_end_time"])
inverted_turnaround_window = sum(1 for p, s, _ in candidates if p["event_end_time"] >= s["event_start_time"])

episodes = build_data2_episode_records(rows)
gaps = []
for e in episodes:
    gaps.append((by_id[e.successor_flight_id]["actual_departure_utc"]
                 - by_id[e.predecessor_flight_id]["actual_arrival_utc"]).total_seconds() / 60)

gaps.sort()
n = len(gaps)
def pct(p):
    return gaps[min(n - 1, int(p * n))]
print("flights_eligible=", len(rows))
print("skipped_canonical=", skipped)
print("actual_gap_candidate_pairs=", len(candidates))
print("inverted_full_schedule_interval=", inverted_full_interval, f"({inverted_full_interval / len(candidates):.4%})")
print("inverted_turnaround_window=", inverted_turnaround_window, f"({inverted_turnaround_window / len(candidates):.4%})")
print("episodes_d2_1=", n)
print("rule=", DATA2_CHAIN_RULE_ID)
print("gap_minutes_p5=", round(pct(0.05), 1), "p25=", round(pct(0.25), 1),
      "p50=", round(pct(0.50), 1), "p75=", round(pct(0.75), 1), "p95=", round(pct(0.95), 1))
aircraft = {r["aircraft_id"] for r in rows}
print("unique_aircraft=", len(aircraft))
print("PROBE_D2_1_JANUARY=DONE")
