import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

weather_dir = ROOT / "raw" / "weather" / "noaa" / "2019"

files = list(weather_dir.glob("*.csv"))

print("STATIONS =", len(files))

records=[]

for f in files:

    try:

        df = pd.read_csv(
            f,
            low_memory=False
        )

        print()
        print(f.name)
        print("rows =", len(df))

        records.append({

            "station":
                f.stem,

            "rows":
                len(df),

            "columns":
                len(df.columns)

        })


    except Exception as e:

        print(
            "FAILED",
            f.name,
            e
        )


out = ROOT / "reports" / "data2_weather_audit.csv"

pd.DataFrame(records).to_csv(
    out,
    index=False
)

print()
print(out)

print()
print("WEATHER_AUDIT_BASIC=PASS")
