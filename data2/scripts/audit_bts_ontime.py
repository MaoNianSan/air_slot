from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]

MONTH_DIR = (
    ROOT
    / "raw"
    / "bts"
    / "ontime"
    / "2019"
    / "month=01"
)

print("ROOT =", ROOT)
print("MONTH_DIR =", MONTH_DIR)

if not MONTH_DIR.exists():
    print()
    print("MONTH_DIRECTORY_NOT_FOUND")
    print(MONTH_DIR)
    sys.exit(1)

files = list(MONTH_DIR.glob("*.csv"))

if not files:
    print()
    print("NO_CSV_FOUND")
    print("Files currently in month directory:")

    for p in MONTH_DIR.iterdir():
        print(" ", p.name)

    sys.exit(2)

print()
print("CSV files:")

for f in files:
    print(
        " ",
        f.name,
        f"{f.stat().st_size / 1024 / 1024:.2f} MB"
    )

path = files[0]

with path.open(
    "r",
    encoding="utf-8-sig",
    newline="",
    errors="replace",
) as fh:
    reader = csv.reader(fh)
    header = next(reader)

header = [x.strip() for x in header]

print()
print("COLUMN COUNT:", len(header))

print()
print("COLUMNS:")

for i, col in enumerate(header):
    print(f"{i:03d}: {col}")

required = [
    "FlightDate",
    "Reporting_Airline",
    "Tail_Number",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "DepTime",
    "TaxiOut",
    "WheelsOff",
    "WheelsOn",
    "TaxiIn",
    "CRSArrTime",
    "ArrTime",
    "Cancelled",
    "Diverted",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
]

present = set(header)

print()
print("=== REQUIRED FIELD CHECK ===")

missing = []

for c in required:
    status = "OK" if c in present else "MISSING"
    print(f"{c:40s} {status}")

    if c not in present:
        missing.append(c)

print()

if missing:
    print("SCHEMA_STATUS=FAIL")
    print("Missing:", missing)
    sys.exit(3)

print("SCHEMA_STATUS=PASS")
