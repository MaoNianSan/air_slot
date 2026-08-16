from pathlib import Path
import csv
import sys
from collections import defaultdict
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

ONTIME_CSV = next((ROOT / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv"))


def hhmm_to_minutes(value: str) -> int | None:
    value = value.strip()
    if not value or value == "NA" or len(value) != 4:
        return None
    try:
        return int(value[:2]) * 60 + int(value[2:])
    except ValueError:
        return None


def percentiles(values, qs=(50, 90, 95, 99)):
    ordered = sorted(values)
    n = len(ordered)
    out = {}
    for q in qs:
        out[q] = ordered[min(n - 1, int(n * q / 100.0))]
    return out, n, ordered[-1]


def main():
    taxi_out = []
    r_ob = []
    # same-aircraft, same-airport consecutive pairs (local times; same tz)
    by_aircraft = defaultdict(list)
    completed = 0
    skipped = 0
    with ONTIME_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            if float(row.get("Cancelled", "0.00") or "0.00") != 0.0 or \
                    float(row.get("Diverted", "0.00") or "0.00") != 0.0:
                skipped += 1
                continue
            completed += 1
            tail = row["Tail_Number"].strip()
            dep_min = hhmm_to_minutes(row.get("DepTime", ""))
            arr_min = hhmm_to_minutes(row.get("ArrTime", ""))
            crs_dep = hhmm_to_minutes(row.get("CRSDepTime", ""))
            taxi = row.get("TaxiOut", "").strip()
            if taxi and taxi != "NA":
                try:
                    taxi_out.append(int(round(float(taxi))))
                except ValueError:
                    pass
            if dep_min is not None and crs_dep is not None:
                r_ob.append(max(0, dep_min - crs_dep))
            if tail and dep_min is not None and arr_min is not None:
                flight_date = datetime.strptime(row["FlightDate"], "%Y-%m-%d").date()
                by_aircraft[tail].append(
                    (flight_date, dep_min, arr_min, row["Origin"].strip(), row["Dest"].strip())
                )

    gaps = []
    for tail, legs in by_aircraft.items():
        legs.sort()
        for prev, curr in zip(legs, legs[1:]):
            if prev[4] != curr[3]:  # pred.Dest != succ.Origin -> not a chain
                continue
            gap = (curr[0] - prev[0]).days * 1440 + (curr[1] - prev[2])
            gaps.append(gap)

    def report(name, values):
        if not values:
            print(f"{name}: EMPTY")
            return
        p, n, maximum = percentiles(values)
        print(f"{name}_n={n}")
        print(f"{name}_median={p[50]}")
        print(f"{name}_p90={p[90]} p95={p[95]} p99={p[99]}")
        print(f"{name}_max={maximum}")

    report("taxi_out", taxi_out)
    cap = 60
    share = sum(1 for v in taxi_out if v > cap) / len(taxi_out) if taxi_out else 0
    print(f"taxi_out_share_gt_{cap}min={round(share, 5)}")

    report("r_ob", r_ob)
    cap = 180
    share = sum(1 for v in r_ob if v > cap) / len(r_ob) if r_ob else 0
    print(f"r_ob_share_gt_{cap}min={round(share, 5)}")

    report("same_aircraft_same_airport_gap", gaps)
    cap = 360
    share = sum(1 for v in gaps if v > cap) / len(gaps) if gaps else 0
    print(f"gap_share_gt_{cap}min={round(share, 5)}")
    chained = [v for v in gaps if v <= cap]
    if chained:
        p, n, maximum = percentiles(chained)
        print(f"chained_gap_n={n} median={p[50]} p90={p[90]} p95={p[95]} p99={p[99]} max={maximum}")
    print(f"completed_flights={completed} skipped_cancelled_diverted={skipped}")


if __name__ == "__main__":
    main()
