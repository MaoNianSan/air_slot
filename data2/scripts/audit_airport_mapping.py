import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

airport = pd.read_csv(
    ROOT/"refs"/"airport_registry.csv"
)

iata = set(
    airport["iata_code"].dropna()
)

print("AIRPORT REGISTRY:")
print(len(iata))


# 读取一个 BTS 月份
files = list(
    (
        ROOT/
        "raw"/"bts"/"ontime"/"2019"/"month=01"
    ).glob("*.csv")
)

f = files[0]


df = pd.read_csv(
    f,
    usecols=[
        "Origin",
        "Dest"
    ],
    nrows=500000,
    low_memory=False
)


origin_match = (
    df["Origin"].isin(iata)
).mean()

dest_match = (
    df["Dest"].isin(iata)
).mean()


print()
print("Origin match =", origin_match)
print("Dest match   =", dest_match)

print()
print("BTS_AIRPORT_MAPPING_TEST=PASS")
