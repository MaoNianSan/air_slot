import pandas as pd
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2


ROOT = Path(__file__).resolve().parents[1]


top_file = ROOT / "refs" / "top_airports_2019.csv"
airport_file = ROOT / "refs" / "airport_registry.csv"
station_file = ROOT / "raw" / "weather" / "isd-history.csv"


out_file = ROOT / "refs" / "weather_station_map.csv"


# -------------------------
# load top airports
# -------------------------

top = pd.read_csv(top_file)

top_codes = set(
    top["airport"]
    .head(100)
)


# -------------------------
# load airport registry
# -------------------------

airports = pd.read_csv(
    airport_file
)

airports = airports[
    airports["iata_code"].isin(top_codes)
].copy()


print("TOP AIRPORTS FOUND =", len(airports))


# -------------------------
# load NOAA stations
# -------------------------

stations = pd.read_csv(
    station_file,
    encoding="latin1"
)


stations = stations[
    stations["LAT"].notna()
    &
    stations["LON"].notna()
].copy()


print("NOAA STATIONS =", len(stations))


# -------------------------
# distance
# -------------------------

def haversine(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371

    p1 = radians(lat1)
    p2 = radians(lat2)

    dlat = radians(lat2-lat1)
    dlon = radians(lon2-lon1)

    a = (
        sin(dlat/2)**2
        +
        cos(p1)
        *
        cos(p2)
        *
        sin(dlon/2)**2
    )

    return (
        2
        *
        R
        *
        atan2(
            sqrt(a),
            sqrt(1-a)
        )
    )


# -------------------------
# mapping
# -------------------------

rows=[]


for _, a in airports.iterrows():

    lat = a["latitude_deg"]
    lon = a["longitude_deg"]


    s = stations.copy()


    s["distance_km"] = s.apply(
        lambda x:
        haversine(
            lat,
            lon,
            x["LAT"],
            x["LON"]
        ),
        axis=1
    )


    best = s.sort_values(
        "distance_km"
    ).iloc[0]


    rows.append({

        "airport":
            a["iata_code"],

        "station":
            str(best["USAF"])
            +
            str(best["WBAN"]),

        "distance_km":
            round(
                best["distance_km"],
                3
            ),

        "weather_source_type":
            (
                "DIRECT_STATION"
                if best["distance_km"] <= 10
                else
                "NEAREST_STATION_PROXY"
            ),

        "station_lat":
            best["LAT"],

        "station_lon":
            best["LON"]

    })


result = pd.DataFrame(rows)


result.to_csv(
    out_file,
    index=False
)


print()
print(result.head(10).to_string())

print()
print("OUTPUT:")
print(out_file)

print()
print("WEATHER_STATION_MAPPING=PASS")
