from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
COUPON = ROOT / "raw" / "bts" / "db1b" / "2019" / "coupon" / "Origin_and_Destination_Survey_DB1BCoupon_2019_1.csv"
MARKET = ROOT / "raw" / "bts" / "db1b" / "2019" / "market" / "Origin_and_Destination_Survey_DB1BMarket_2019_1.csv"


def _scan(path, numeric_fares=False):
    rows = 0
    pax = 0
    itins = set()
    origins = set()
    dests = set()
    carriers = {"OpCarrier": {}, "TkCarrier": {}, "RPCarrier": {}}
    fares = []
    with path.open(encoding="utf-8-sig", newline="", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows += 1
            try:
                pax += int(float(row.get("Passengers") or 0))
            except ValueError:
                pass
            itins.add(row.get("ItinID"))
            origins.add(row.get("Origin"))
            dests.add(row.get("Dest"))
            for col in carriers:
                code = (row.get(col) or "").strip()
                carriers[col][code] = carriers[col].get(code, 0) + 1
            if numeric_fares:
                try:
                    fares.append(float(row.get("MktFare") or 0))
                except ValueError:
                    pass
    return rows, pax, len(itins), len(origins), len(dests), carriers, fares


def _placeholder_stats(carriers):
    out = {}
    for col, counts in carriers.items():
        total = sum(counts.values())
        for code, label in (("--", "PLACEHOLDER_DASHDASH"), ("99", "PLACEHOLDER_99"), ("", "EMPTY")):
            n = counts.get(code, 0)
            out[f"{col}_{label}"] = f"{n} ({n / total:.4%})"
    return out


def _fares_stats(fares):
    if not fares:
        return {"count": 0}
    fares.sort()
    n = len(fares)
    def pct(p):
        return fares[min(n - 1, int(p * n))]
    return {"count": n, "mean": sum(fares) / n, "p25": pct(0.25), "p50": pct(0.50), "p75": pct(0.75)}


print("=== DB1B COUPON Q1 (10% ticket sample) ===")
rows, pax, itins, origins, dests, carriers, _ = _scan(COUPON)
print("rows=", rows)
print("passengers_sample_sum=", pax)
print("unique_itin_id=", itins)
print("unique_origins=", origins, "unique_dests=", dests)
for k, v in _placeholder_stats(carriers).items():
    print(k, "=", v)

print()
print("=== DB1B MARKET Q1 ===")
rows, pax, itins, origins, dests, carriers, fares = _scan(MARKET, numeric_fares=True)
print("rows=", rows)
print("passengers_sample_sum=", pax)
print("unique_itin_id=", itins)
print("unique_origins=", origins, "unique_dests=", dests)
for k, v in _placeholder_stats(carriers).items():
    print(k, "=", v)
print("mkt_fare_stats=", _fares_stats(fares))
print()
print("PROFILE_DB1B_Q1=DONE")
