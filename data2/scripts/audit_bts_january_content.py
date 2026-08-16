from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parents[1]

month_dir = (
    root
    / "raw"
    / "bts"
    / "ontime"
    / "2019"
    / "month=01"
)

files = list(month_dir.glob("*.csv"))

if not files:
    raise SystemExit(f"NO_CSV_FOUND: {month_dir}")

f = files[0]

print("FILE =", f)
print("SIZE_MB =", round(f.stat().st_size / 1024 / 1024, 2))

cols = [
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
    "LateAircraftDelay",
]

df = pd.read_csv(
    f,
    usecols=cols,
    low_memory=False
)

print()
print("ROWS =", len(df))
print("CARRIERS =", df["Reporting_Airline"].nunique())
print("TAIL_NUMBERS =", df["Tail_Number"].nunique())
print("ORIGINS =", df["Origin"].nunique())
print("DESTINATIONS =", df["Dest"].nunique())

print()
print("=== ALL-FLIGHT MISSING RATE ===")

for c in cols:
    print(
        f"{c:40s}"
        f"{df[c].isna().mean():10.4%}"
    )

completed = df[
    (df["Cancelled"].fillna(0) == 0)
    &
    (df["Diverted"].fillna(0) == 0)
].copy()

print()
print("=== COMPLETED FLIGHTS ===")
print("ROWS =", len(completed))

core = [
    "Tail_Number",
    "CRSDepTime",
    "DepTime",
    "TaxiOut",
    "WheelsOff",
    "WheelsOn",
    "TaxiIn",
    "CRSArrTime",
    "ArrTime",
]

for c in core:
    print(
        f"{c:40s}"
        f"coverage={completed[c].notna().mean():10.4%}"
    )

print()
print("=== TOP CARRIERS ===")
print(
    completed["Reporting_Airline"]
    .value_counts()
    .head(20)
    .to_string()
)

print()
print("JANUARY_CONTENT_AUDIT=PASS")
