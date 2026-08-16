from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from model.common.identity import content_id
from model.PRE.reference.passenger_data2 import build_data2_passenger_reference

COUPON_CSV = ROOT / "raw" / "bts" / "db1b" / "2019" / "coupon" / "Origin_and_Destination_Survey_DB1BCoupon_2019_1.csv"
ONTIME_CSV = next((ROOT / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv"))


def stream_coupon_routes():
    """Official DB1B Coupon Q1: stream and aggregate Passengers by route.

    Reads only the coupon file (the adapter glob would also match the
    market file, so the probe reads the coupon path directly and keeps the
    same canonical column semantics: Passengers/Origin/Dest).
    """
    sums: dict[tuple[str, str], float] = {}
    counts: dict[tuple[str, str], int] = {}
    rows = 0
    missing_passengers = 0
    with COUPON_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        idx_pax = header.index("Passengers")
        idx_origin = header.index("Origin")
        idx_dest = header.index("Dest")
        for raw in reader:
            if not raw or len(raw) <= max(idx_pax, idx_origin, idx_dest):
                continue
            rows += 1
            origin = raw[idx_origin].strip()
            dest = raw[idx_dest].strip()
            if not origin or not dest:
                continue
            try:
                pax = float(raw[idx_pax])
            except ValueError:
                missing_passengers += 1
                continue
            key = (origin, dest)
            sums[key] = sums.get(key, 0.0) + pax
            counts[key] = counts.get(key, 0) + 1
    return sums, counts, rows, missing_passengers


def main():
    sums, counts, raw_rows, missing_pax = stream_coupon_routes()
    print("coupon_raw_rows=", raw_rows)
    print("coupon_rows_with_missing_passengers=", missing_pax)
    print("routes_in_coupon=", len(sums))

    rows = [
        {
            "dataset_instance_id": "data2_2019",
            "canonical_record_id": content_id({"source": "bts_db1b", "origin": o, "destination": d}),
            "join_key": {"origin": o, "destination": d},
            "reference_period": "2019",
            "value": total,
            "record_count": counts[(o, d)],
            "split": "train",
        }
        for (o, d), total in sums.items()
    ]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    print("reference_id=", ref.reference_id)
    print("fit_period=", ref.fit_period)
    print("route_count=", ref.route_count)
    print("total_sample_count=", ref.total_sample_count)
    print("total_passengers_scaled=", round(ref.total_passengers))
    print("scale_factor=", ref.scale_factor)
    print("manifest_freeze_id=", ref.manifest_freeze_id)

    top = sorted(ref.cells, key=lambda c: -c.value_passengers)[:10]
    print("top10_routes_by_passengers=", [(c.origin_airport_id + "->" + c.destination_airport_id,
                                            round(c.value_passengers), c.sample_count) for c in top])

    # January flight-route join hit rate (completed flights only)
    flight_routes = set()
    flight_rows = 0
    skipped = 0
    with ONTIME_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            if float(row.get("Cancelled", "0.00") or "0.00") != 0.0 or \
                    float(row.get("Diverted", "0.00") or "0.00") != 0.0:
                skipped += 1
                continue
            flight_rows += 1
            flight_routes.add((row["Origin"].strip(), row["Dest"].strip()))
    covered = {r for r in flight_routes if ref.lookup(*r).support_state.value == "SUPPORTED"}
    print("january_completed_flights=", flight_rows)
    print("january_skipped_cancelled_diverted=", skipped)
    print("january_flight_routes=", len(flight_routes))
    print("january_flight_routes_covered_by_db1b_q1=", len(covered))
    print("january_route_coverage_share=", round(len(covered) / len(flight_routes), 4))
    missing_routes = sorted(flight_routes - covered)[:15]
    print("sample_uncovered_routes=", missing_routes)


if __name__ == "__main__":
    main()
