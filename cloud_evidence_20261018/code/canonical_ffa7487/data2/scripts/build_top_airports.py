import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

files = list(
    (ROOT/"raw"/"bts"/"ontime"/"2019"/"month=01").glob("*.csv")
)

f = files[0]

print("Reading:", f)

df = pd.read_csv(
    f,
    usecols=[
        "Origin",
        "Dest"
    ],
    low_memory=False
)


origin = (
    df["Origin"]
    .value_counts()
    .rename_axis("airport")
    .reset_index(name="departures")
)

dest = (
    df["Dest"]
    .value_counts()
    .rename_axis("airport")
    .reset_index(name="arrivals")
)


airport = (
    origin
    .merge(
        dest,
        on="airport",
        how="outer"
    )
    .fillna(0)
)


airport["operations"] = (
    airport["departures"]
    +
    airport["arrivals"]
)


airport = airport.sort_values(
    "operations",
    ascending=False
)


out = ROOT/"refs"/"top_airports_2019.csv"


airport.head(100).to_csv(
    out,
    index=False
)


print()
print("TOP 20 AIRPORTS")
print(
    airport.head(20).to_string(index=False)
)

print()
print("OUTPUT:")
print(out)

print()
print("TOP_AIRPORT_BUILD=PASS")
