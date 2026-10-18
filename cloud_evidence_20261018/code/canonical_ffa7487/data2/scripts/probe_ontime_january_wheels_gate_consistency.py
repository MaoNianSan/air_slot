from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
MONTH_DIR = ROOT / "raw" / "bts" / "ontime" / "2019" / "month=01"
CSV = next(MONTH_DIR.glob("*.csv"))


def _minutes(hhmm):
    if not hhmm or str(hhmm).strip() == "":
        return None
    s = str(hhmm).strip()
    if "." in s:
        try:
            return int(float(s))
        except ValueError:
            return None
    try:
        h, m = int(s[:-2]), int(s[-2:])
    except ValueError:
        return None
    return h * 60 + m


rows = 0
completed = 0
checked = 0
wheels_off_mismatch = 0
wheels_on_mismatch = 0
wheels_off_mismatch_examples = []
wheels_on_mismatch_examples = []
with CSV.open(encoding="utf-8-sig", newline="", errors="replace") as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        rows += 1
        try:
            cancelled = int(float(row.get("Cancelled") or 0))
            diverted = int(float(row.get("Diverted") or 0))
        except ValueError:
            cancelled = diverted = 0
        if cancelled or diverted:
            continue
        completed += 1
        dep = _minutes(row.get("DepTime"))
        arr = _minutes(row.get("ArrTime"))
        wo = _minutes(row.get("WheelsOff"))
        wn = _minutes(row.get("WheelsOn"))
        taxi_out = _minutes(row.get("TaxiOut"))
        taxi_in = _minutes(row.get("TaxiIn"))
        if dep is None or wo is None or taxi_out is None:
            continue
        checked += 1
        expected_wo = (dep + taxi_out) % 1440
        diff = (wo - expected_wo) % 1440
        diff = min(diff, 1440 - diff)
        if diff > 1:
            wheels_off_mismatch += 1
            if len(wheels_off_mismatch_examples) < 5:
                wheels_off_mismatch_examples.append(
                    (row.get("FlightDate"), row.get("Flight_Number_Reporting_Airline"),
                     row.get("DepTime"), row.get("TaxiOut"), row.get("WheelsOff")))
        if arr is None or wn is None or taxi_in is None:
            continue
        expected_wn = (arr - taxi_in) % 1440
        diff2 = (wn - expected_wn) % 1440
        diff2 = min(diff2, 1440 - diff2)
        if diff2 > 1:
            wheels_on_mismatch += 1
            if len(wheels_on_mismatch_examples) < 5:
                wheels_on_mismatch_examples.append(
                    (row.get("FlightDate"), row.get("Flight_Number_Reporting_Airline"),
                     row.get("ArrTime"), row.get("TaxiIn"), row.get("WheelsOn")))

print("rows=", rows)
print("completed=", completed)
print("checked_wheels_off=", checked)
print("wheels_off_mismatch_rate=", f"{wheels_off_mismatch / checked:.4%}", "(", wheels_off_mismatch, ")")
print("wheels_off_examples=", wheels_off_mismatch_examples)
print("wheels_on_mismatch_rate=", f"{wheels_on_mismatch / checked:.4%}", "(", wheels_on_mismatch, ")")
print("wheels_on_examples=", wheels_on_mismatch_examples)
print()
print("PROBE_JANUARY_WHEELS_GATE_CONSISTENCY=DONE")
