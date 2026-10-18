from pathlib import Path
import csv
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
T100 = ROOT / "raw" / "bts" / "t100" / "2019" / "T_T100_SEGMENT_ALL_CARRIER.csv"


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


rows = 0
class_counts = Counter()
class_pax = Counter()
class_rows = Counter()
carrier_class = Counter()
acft_missing = 0
years = set()
months = set()
origins = set()
dests = set()
with T100.open(encoding="utf-8-sig", newline="", errors="replace") as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        rows += 1
        cls = (row.get("CLASS") or "").strip() or "<EMPTY>"
        carrier = (row.get("UNIQUE_CARRIER") or row.get("CARRIER") or "").strip()
        class_counts[cls] += 1
        pax = _num(row.get("PASSENGERS"))
        if pax is not None:
            class_pax[cls] += pax
        class_rows[cls] += 1
        carrier_class[(carrier, cls)] += 1
        if not (row.get("AIRCRAFT_TYPE") or "").strip():
            acft_missing += 1
        years.add(row.get("YEAR"))
        months.add(row.get("MONTH"))
        origins.add(row.get("ORIGIN"))
        dests.add(row.get("DEST"))

print("rows=", rows)
print("class_value_counts=", dict(class_counts))
print("class_passenger_rows=", dict(class_rows))
print("class_passenger_sum=", {k: round(v) for k, v in class_pax.items()})
print("aircraft_type_missing_rate=", f"{acft_missing / rows:.4%}")
print("years=", sorted(years))
print("months=", sorted(months))
print("unique_origins=", len(origins), "unique_dests=", len(dests))
print("top_carrier_class=", carrier_class.most_common(12))
print()
print("PROFILE_T100_CLASS=DONE")
