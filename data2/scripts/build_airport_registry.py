import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

src = ROOT / "raw" / "airport" / "airports.csv"

out = ROOT / "refs" / "airport_registry.csv"

print("INPUT:")
print(src)

df = pd.read_csv(
    src,
    low_memory=False
)

print()
print("RAW AIRPORT ROWS =", len(df))

# Keep airports with IATA code
df = df[
    df["iata_code"].notna()
].copy()

# Keep US airports for BTS Data2
df = df[
    df["iso_country"] == "US"
].copy()


cols = [
    "ident",
    "iata_code",
    "name",
    "type",
    "latitude_deg",
    "longitude_deg",
    "elevation_ft",
    "iso_country",
    "iso_region",
    "municipality",
    "timezone"
]

available = [
    c for c in cols
    if c in df.columns
]


df = df[available]


df = df.drop_duplicates(
    subset=["iata_code"]
)


df.to_csv(
    out,
    index=False,
    encoding="utf-8"
)


print()
print("OUTPUT:")
print(out)

print()
print("US IATA AIRPORTS =", len(df))

print()
print(df.head(10).to_string())

print()
print("AIRPORT_REGISTRY_BUILD=PASS")
