from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.registry import RawReadRequest

WEATHER_DIR = ROOT / "raw" / "weather" / "noaa" / "2019"
STATION_MAP = ROOT / "refs" / "weather_station_map.csv"
TOP_AIRPORTS = ROOT / "refs" / "top_airports_2019.csv"

# --- raw column scan: January rows, FM-15 share, TMP missing rate ---
raw_rows = 0
jan_rows = 0
fm15_jan = 0
tmp_missing_jan = 0
for path in sorted(WEATHER_DIR.glob("*.csv")):
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            raw_rows += 1
            if not row["DATE"].startswith("2019-01"):
                continue
            jan_rows += 1
            if row["REPORT_TYPE"] == "FM-15":
                fm15_jan += 1
            if not row["TMP"].strip():
                tmp_missing_jan += 1

print("raw_rows_total=", raw_rows, flush=True)
print("raw_rows_january=", jan_rows, flush=True)
print("fm15_january_share=", round(fm15_jan / jan_rows, 4), flush=True)
print("tmp_missing_january_share=", round(tmp_missing_jan / jan_rows, 4), flush=True)

with STATION_MAP.open(encoding="utf-8-sig", newline="") as fh:
    mapped_airports = {row["airport"] for row in csv.DictReader(fh)}
with TOP_AIRPORTS.open(encoding="utf-8-sig", newline="") as fh:
    top_airports = {row["airport"] for row in csv.DictReader(fh)}

request = RawReadRequest(
    dataset_instance_id="data2_2019",
    source_family="noaa_isd",
    raw_root=ROOT,
    output_root=ROOT.parent / "outputs" / "probe_isd_weather_january",
    year=2019,
)
adapter = Data2Adapter()
jan_obs = 0
covered = set()
per_airport = {}
qnh_absent = 0
vis_missing = 0
ceil_missing = 0
ceil_unlimited = 0
tmp_missing_canon = 0
files_done = set()
errors = 0
for obs in adapter.iter_canonical(request, replay_lag_minutes=5):
    if obs.source_path not in files_done:
        files_done.add(obs.source_path)
        print("file:", obs.source_path, "rows_in_jan_so_far=", jan_obs, flush=True)
    if obs.event_time is None or not obs.event_time.strftime("%Y-%m").startswith("2019-01"):
        continue
    jan_obs += 1
    covered.add(obs.airport_id)
    per_airport[obs.airport_id] = per_airport.get(obs.airport_id, 0) + 1
    flags = obs.quality_flags
    if obs.temperature_c is None:
        tmp_missing_canon += 1
    if "QNH_ABSENT" in flags:
        qnh_absent += 1
    if obs.visibility_m is None:
        vis_missing += 1
    if "CEILING_MISSING" in flags:
        ceil_missing += 1
    if "CEILING_UNLIMITED" in flags or "CEILING_UNLIMITED_OR_METAR_ABSENT" in flags:
        ceil_unlimited += 1

print("canonical_january_obs=", jan_obs, flush=True)
print("airports_covered=", len(covered), flush=True)
print("airports_mapped_total=", len(mapped_airports), flush=True)
print("airports_covered_in_top100=", len(covered & top_airports), flush=True)
print("top100_total=", len(top_airports), flush=True)
print("tmp_missing_canonical_share=", round(tmp_missing_canon / jan_obs, 4), flush=True)
print("qnh_absent_share=", round(qnh_absent / jan_obs, 4), flush=True)
print("visibility_missing_share=", round(vis_missing / jan_obs, 4), flush=True)
print("ceiling_missing_share=", round(ceil_missing / jan_obs, 4), flush=True)
print("ceiling_unlimited_or_absent_share=", round(ceil_unlimited / jan_obs, 4), flush=True)
print("top10_airports_by_jan_obs=", sorted(per_airport.items(), key=lambda kv: -kv[1])[:10], flush=True)
print("contract_errors=", errors, flush=True)
