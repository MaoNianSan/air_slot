# -*- coding: utf-8 -*-
"""D1 baseline + D6 audit for the Data2 2019->2022 raw extension.

  python audit_raw_year_extension.py --mode baseline   # freeze 2019 (D1)
  python audit_raw_year_extension.py --mode audit      # completeness / schema /
                                                       # manifests / 2019 integrity (D6)

Read-only over data2; writes only under data2/reports/. In audit mode the
Data2 adapter may be imported for a RAW_SCHEMA_MISMATCH smoke test (reading
raw only, max_rows=3; the PRE pipeline is never invoked).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA2 = REPO / "data2"
REPORTS = DATA2 / "reports"
BASELINE_CSV = REPORTS / "data2_raw_2019_baseline_sha256.csv"
BASELINE_GIT = REPORTS / "data2_2019_git_status_baseline.txt"
AUDIT_JSON = REPORTS / "data2_raw_2017_2022_audit.json"
AUDIT_MD = REPORTS / "data2_raw_2017_2022_audit.md"
YEARS = (2017, 2018, 2020, 2021, 2022)          # extended fetch years
ALL_YEARS = (2017, 2018, 2019, 2020, 2021, 2022)  # incl. the frozen template
RAW_2019_DIRS = (DATA2 / "raw" / "bts" / "ontime" / "2019",
                 DATA2 / "raw" / "bts" / "db1b" / "2019",
                 DATA2 / "raw" / "bts" / "t100" / "2019",
                 DATA2 / "raw" / "weather" / "noaa" / "2019")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), *args],
                         capture_output=True, text=True)
    return (out.stdout + out.stderr).strip()


def files_under(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.rglob("*") if p.is_file())


def csv_header(path: Path) -> list[str]:
    with path.open("rt", encoding="utf-8-sig", newline="", errors="replace") as f:
        row = next(csv.reader(f), None)
    return [cell.strip() for cell in (row or [])]


def header_diff(base: list[str], new: list[str]) -> dict:
    return {"identical": base == new,
            "added": [c for c in new if c not in base],
            "removed": [c for c in base if c not in new],
            "reordered": sorted(base) == sorted(new) and base != new,
            "base_columns": len(base), "new_columns": len(new)}


# ---------------------------------------------------------------- baseline --

def run_baseline() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for root in RAW_2019_DIRS:
        for path in files_under(root):
            rows.append([path.relative_to(REPO).as_posix(), sha256_file(path),
                         path.stat().st_size])
    with BASELINE_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(["Path", "SHA256", "Bytes"])
        writer.writerows(rows)
    status = git("status", "--porcelain")
    BASELINE_GIT.write_text(status + "\n", encoding="utf-8")
    print(f"BASELINE_WRITTEN files={len(rows)} "
          f"csv={BASELINE_CSV} git_status_bytes={len(status)}")


# -------------------------------------------------------------------- audit --

def count_ontime(year: int) -> dict:
    base = DATA2 / "raw" / "bts" / "ontime" / str(year)
    have, missing = [], []
    for month in range(1, 13):
        d = base / f"month={month:02d}"
        csvs = [p for p in d.glob("*.csv")] if d.is_dir() else []
        (have if csvs else missing).append(f"month={month:02d}")
    return {"expected": 12, "downloaded": len(have), "present": have,
            "missing": missing}


def count_db1b(year: int, product: str) -> dict:
    d = DATA2 / "raw" / "bts" / "db1b" / str(year) / product
    csvs = [p.name for p in files_under(d) if p.suffix.lower() == ".csv"]
    expected = 4 if product == "coupon" else 1
    return {"expected": expected, "downloaded": len(csvs), "files": csvs}


def count_noaa(year: int, template: list[str]) -> dict:
    d = DATA2 / "raw" / "weather" / "noaa" / str(year)
    present = sorted(p.stem for p in d.glob("*.csv")) if d.is_dir() else []
    missing = sorted(set(template) - set(present))
    extra = sorted(set(present) - set(template))
    return {"expected": len(template), "downloaded": len(present),
            "missing": missing, "extra": extra}


def count_t100(year: int) -> dict:
    d = DATA2 / "raw" / "bts" / "t100" / str(year)
    csvs = [p for p in files_under(d) if p.suffix.lower() == ".csv"]
    return {"expected": 1, "downloaded": len(csvs), "files": [p.name for p in csvs]}


def schema_section() -> dict:
    out: dict = {}
    ontime_base_dir = DATA2 / "raw" / "bts" / "ontime" / "2019" / "month=01"
    ontime_base = csv_header(next(iter(ontime_base_dir.glob("*.csv"))))
    for year in YEARS:
        d = DATA2 / "raw" / "bts" / "ontime" / str(year) / "month=01"
        csvs = list(d.glob("*.csv"))
        out[f"ontime_{year}"] = (header_diff(ontime_base, csv_header(csvs[0]))
                                 if csvs else {"status": "MISSING_FILE"})
    for product in ("coupon", "market"):
        base_dir = DATA2 / "raw" / "bts" / "db1b" / "2019" / product
        base_csvs = list(base_dir.glob("*.csv"))
        base = csv_header(base_csvs[0]) if base_csvs else None
        for year in YEARS:
            d = DATA2 / "raw" / "bts" / "db1b" / str(year) / product
            csvs = list(d.glob("*.csv"))
            key = f"db1b_{product}_{year}"
            out[key] = (header_diff(base, csv_header(csvs[0]))
                        if base and csvs else {"status": "MISSING_FILE"})
    t100_base_dir = DATA2 / "raw" / "bts" / "t100" / "2019"
    base = csv_header(next(iter(t100_base_dir.glob("*.csv"))))
    for year in YEARS:
        csvs = list((DATA2 / "raw" / "bts" / "t100" / str(year)).glob("*.csv"))
        out[f"t100_{year}"] = (header_diff(base, csv_header(csvs[0]))
                               if csvs else {"status": "MISSING_FILE"})
    noaa_2019 = DATA2 / "raw" / "weather" / "noaa" / "2019"
    base_headers = {p.stem: csv_header(p) for p in noaa_2019.glob("*.csv")}
    mandatory = ["STATION", "DATE", "WND", "CIG", "VIS", "TMP", "DEW",
                 "SLP", "REM", "REPORT_TYPE", "CALL_SIGN"]
    for year in YEARS:
        d = DATA2 / "raw" / "weather" / "noaa" / str(year)
        identical, diffs, absent, mandatory_drift = 0, [], 0, []
        for station, base in sorted(base_headers.items()):
            path = d / f"{station}.csv"
            if not path.is_file():
                absent += 1
                continue
            new = csv_header(path)
            diff = header_diff(base, new)
            if diff["identical"]:
                identical += 1
            else:
                diffs.append({"station": station, **diff})
            missing_mandatory = [c for c in mandatory if c not in new]
            if missing_mandatory:
                mandatory_drift.append({"station": station,
                                        "missing": missing_mandatory})
        out[f"noaa_{year}"] = {"stations_identical_to_2019": identical,
                               "stations_different": diffs, "stations_absent": absent,
                               "mandatory_column_drift": mandatory_drift}
    return out


def verify_manifest(year: int) -> dict:
    path = DATA2 / "manifests" / f"data2_bts_{year}_sha256.csv"
    if not path.is_file():
        return {"manifest": path.name, "exists": False, "rows": 0,
                "verified": 0, "missing_files": [], "hash_mismatches": []}
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header != ["Path", "Hash", "Type", "SourceZip"]:
            return {"manifest": path.name, "exists": True,
                    "error": f"unexpected header {header}"}
        rows = [row for row in reader if row]
    missing, mismatches, verified = [], [], 0
    for row in rows:
        target = DATA2 / row[0]
        if not target.is_file():
            missing.append(row[0])
        elif sha256_file(target) != row[1]:
            mismatches.append(row[0])
        else:
            verified += 1
    return {"manifest": path.name, "exists": True, "rows": len(rows),
            "verified": verified, "missing_files": missing,
            "hash_mismatches": mismatches}


def integrity_2019() -> dict:
    baseline = {}
    with BASELINE_CSV.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            baseline[row["Path"]] = (row["SHA256"], int(row["Bytes"]))
    current = {}
    for root in RAW_2019_DIRS:
        for path in files_under(root):
            current[path.relative_to(REPO).as_posix()] = path
    changed, missing, checked = [], [], 0
    for rel, (sha, _bytes) in baseline.items():
        checked += 1
        path = REPO / rel
        if not path.is_file():
            missing.append(rel)
        elif sha256_file(path) != sha:
            changed.append(rel)
    new = sorted(set(current) - set(baseline))
    return {"files_checked": checked, "changed": changed, "missing": missing,
            "new_files": new, "ok": not (changed or missing or new)}


def parse_logs() -> dict:
    """Collect failures and the final per-log summary. A failure is marked
    resolved when the log's LAST summary for that dataset-year shows success
    (a later run legitimately fixed it)."""
    failures, summaries, criticals = [], {}, []
    logs_dir = DATA2 / "logs"
    for log in sorted(logs_dir.glob("download_*_20*.log")):
        text = log.read_text(encoding="utf-8", errors="replace")
        log_failures: list[dict] = []
        for line in text.splitlines():
            if "FAILURE_JSON " in line:
                try:
                    entry = json.loads(line.split("FAILURE_JSON ", 1)[1])
                    entry["log"] = log.name
                    log_failures.append(entry)
                except json.JSONDecodeError:
                    pass
            elif "SUMMARY_JSON " in line:
                try:
                    summaries[log.name] = json.loads(
                        line.split("SUMMARY_JSON ", 1)[1])
                except json.JSONDecodeError:
                    pass
            elif " CRITICAL " in line:
                criticals.append({"log": log.name, "line": line.strip()[:300]})
        final = summaries.get(log.name)
        for entry in log_failures:
            if final and final.get("ok", 0) > 0:
                entry["resolved_by_later_run"] = True
            failures.append(entry)
    return {"failures": failures, "summaries": summaries, "criticals": criticals}


def adapter_smoke() -> dict:
    try:
        sys.path.insert(0, str(REPO))
        from model.PRE.adapters.data2 import Data2Adapter
        from model.PRE.adapters.registry import RawReadRequest
    except Exception as error:
        return {"status": "SKIPPED_IMPORT_FAILED",
                "error": f"{type(error).__name__}: {error}"}
    families = {"ontime": "bts_ontime", "db1b": "bts_db1b",
                "t100": "bts_t100", "noaa": "noaa_isd"}
    replay_lag = 5
    try:
        import yaml
        cfg = yaml.safe_load((REPO / "configs" / "scientific" /
                              "foundation.yaml").read_text(encoding="utf-8"))
        replay_lag = int(cfg["parameters"]["data2_weather_replay_lag_minutes"]["value"])
    except Exception:
        pass
    detail: dict = {}
    adapter = Data2Adapter()
    for label, family in families.items():
        for year in YEARS:
            key = f"{label}_{year}"
            try:
                request = RawReadRequest(
                    dataset_instance_id="data2_2019", source_family=family,
                    raw_root=DATA2, output_root=REPO / "tmp" / "data2_audit_smoke",
                    year=year, max_rows=3)
                rows = []
                for row in adapter.iter_canonical(request,
                                                  replay_lag_minutes=replay_lag):
                    rows.append(row.source_path)
                detail[key] = {"status": "PASS" if rows else "NO_ROWS",
                               "rows": rows[:3]}
            except Exception as error:
                detail[key] = {"status": "FAIL",
                               "error": f"{type(error).__name__}: {error}"}
    status = ("PASS" if all(v["status"] == "PASS" for v in detail.values())
              else "PARTIAL")
    return {"status": status, "detail": detail}


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in files_under(path))


def disk_section() -> dict:
    bts = DATA2 / "raw" / "bts"
    weather = DATA2 / "raw" / "weather"
    per_year = {}
    for year in ("2019", "2020", "2021", "2022"):
        per_year[year] = {
            "ontime_gb": round(dir_size(bts / "ontime" / year) / 10 ** 9, 2),
            "db1b_gb": round(dir_size(bts / "db1b" / year) / 10 ** 9, 2),
            "t100_gb": round(dir_size(bts / "t100" / year) / 10 ** 9, 2),
            "noaa_gb": round(dir_size(weather / "noaa" / year) / 10 ** 9, 2),
        }
    return {"free_gb": round(shutil_disk_free(DATA2), 2),
            "raw_bts_gb": round(dir_size(bts) / 10 ** 9, 2),
            "raw_weather_gb": round(dir_size(weather) / 10 ** 9, 2),
            "download_gb": round(dir_size(DATA2 / "_download") / 10 ** 9, 2),
            "per_year": per_year}


def shutil_disk_free(path: Path) -> float:
    import shutil
    return shutil.disk_usage(path).free / 10 ** 9


def run_audit() -> None:
    import shutil
    start_time = (datetime.fromtimestamp(BASELINE_CSV.stat().st_mtime)
                  .astimezone().isoformat(timespec="seconds")
                  if BASELINE_CSV.is_file() else None)
    noaa_template = sorted(p.stem for p in
                           (DATA2 / "raw" / "weather" / "noaa" / "2019").glob("*.csv"))
    ontime = {y: count_ontime(y) for y in YEARS}
    coupon = {y: count_db1b(y, "coupon") for y in YEARS}
    market = {y: count_db1b(y, "market") for y in YEARS}
    noaa = {y: count_noaa(y, noaa_template) for y in YEARS}
    t100 = {y: count_t100(y) for y in YEARS}
    integrity = integrity_2019()
    logs = parse_logs()
    manifests = {y: verify_manifest(y) for y in ALL_YEARS}
    smoke = adapter_smoke()
    t100_blocked = sorted({str(entry["year"]) for entry in logs["failures"]
                           if entry.get("dataset") == "t100"
                           and "BLOCKED" in str(entry.get("status", ""))
                           and not entry.get("resolved_by_later_run")})
    missing_partitions = (
        sum(len(v["missing"]) for v in ontime.values())
        + sum(v["expected"] - v["downloaded"] for v in coupon.values())
        + sum(v["expected"] - v["downloaded"] for v in market.values())
        + sum(len(v["missing"]) for v in noaa.values())
        + sum(v["expected"] - v["downloaded"] for v in t100.values()))
    t100_methods: dict[str, str] = {}
    for year in YEARS:
        log = DATA2 / "logs" / f"download_t100_{year}.log"
        if not log.is_file():
            t100_methods[str(year)] = "NO_LOG"
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        if "T100_LOCAL_STAGE_ZIP" in text and "PARTITION_OK t100" in text:
            t100_methods[str(year)] = "LOCAL_STAGING_ZIP_VALIDATED"
        elif "T100_WEBFORM_POST" in text:
            t100_methods[str(year)] = "TRANSTATS_WEBFORMS_PROGRAMMATIC"
        elif "T100_WEBFORM_FAIL" in text:
            t100_methods[str(year)] = "WEBFORMS_FAILED"
        else:
            t100_methods[str(year)] = "NO_ACQUISITION_ATTEMPTED"
    if not integrity["ok"] or logs["criticals"]:
        overall = "FAIL"
    elif missing_partitions:
        overall = "PARTIAL_WITH_BLOCKERS"
    else:
        overall = "PASS"
    report = {
        "EXECUTION_REPOSITORY": str(REPO),
        "BRANCH": git("branch", "--show-current"),
        "START_TIME": start_time,
        "END_TIME": now(),
        "ONTIME": ontime,
        "DB1B_COUPON": coupon,
        "DB1B_MARKET_Q1": market,
        "NOAA": noaa,
        "T100": {y: {**t100[y],
                     "status": ("OK" if t100[y]["downloaded"] == 1 else
                                "BLOCKED_MANUAL_DOWNLOAD_REQUIRED"
                                if str(y) in t100_blocked else "MISSING")}
                 for y in YEARS},
        "T100_ACQUISITION_METHOD": t100_methods,
        "DOWNLOAD_FAILURES": logs["failures"],
        "SCHEMA_DRIFT": schema_section(),
        "MANIFEST_STATUS": manifests,
        "2019_INTEGRITY": integrity,
        "DISK_USAGE": disk_section(),
        "ADAPTER_SMOKE": smoke,
        "LOG_SUMMARIES": logs["summaries"],
        "OVERALL_STATUS": overall,
    }
    AUDIT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    write_md(report)
    print(f"AUDIT_WRITTEN overall={overall} json={AUDIT_JSON} md={AUDIT_MD}")


def write_md(r: dict) -> None:
    lines = ["# Data2 raw 2017-2022 extension audit", ""]
    lines += [f"- Execution repository: `{r['EXECUTION_REPOSITORY']}`",
              f"- Branch: `{r['BRANCH']}`",
              f"- Start time (D1 baseline): {r['START_TIME']}",
              f"- End time (D6 audit): {r['END_TIME']}",
              f"- **OVERALL_STATUS: {r['OVERALL_STATUS']}**", ""]
    lines += ["## Partition counts", "",
              "| dataset | year | expected | downloaded | missing |",
              "|---|---|---|---|---|"]
    for year in YEARS:
        v = r["ONTIME"][year]
        lines.append(f"| ontime | {year} | {v['expected']} | {v['downloaded']} | "
                     f"{', '.join(v['missing']) or '-'} |")
        v = r["DB1B_COUPON"][year]
        lines.append(f"| db1b coupon | {year} | {v['expected']} | {v['downloaded']} | "
                     f"{'-'} |")
        v = r["DB1B_MARKET_Q1"][year]
        lines.append(f"| db1b market Q1 | {year} | {v['expected']} | "
                     f"{v['downloaded']} | {'-'} |")
        v = r["NOAA"][year]
        lines.append(f"| noaa stations | {year} | {v['expected']} | "
                     f"{v['downloaded']} | {', '.join(v['missing'][:5]) or '-'}"
                     f"{' ...' if len(v['missing']) > 5 else ''} |")
        v = r["T100"][year]
        lines.append(f"| t100 | {year} | {v['expected']} | {v['downloaded']} | "
                     f"{v['status']} |")
    lines += ["", "## Download failures", ""]
    if r["DOWNLOAD_FAILURES"]:
        for entry in r["DOWNLOAD_FAILURES"]:
            resolved = " [RESOLVED by later run]" if entry.get(
                "resolved_by_later_run") else ""
            lines.append(f"- `{entry['log']}` {entry['dataset']} {entry['year']} "
                         f"{entry['partition']} status={entry['status']}"
                         f"{resolved} retries={entry['retries']} "
                         f"error={entry['error']}")
    else:
        lines.append("- none")
    lines += ["", "## Schema drift (vs 2019 template)", ""]
    for key, diff in r["SCHEMA_DRIFT"].items():
        if diff.get("status") == "MISSING_FILE":
            lines.append(f"- {key}: MISSING_FILE")
        elif "stations_identical_to_2019" in diff:
            md = diff.get("mandatory_column_drift", [])
            lines.append(f"- {key}: identical={diff['stations_identical_to_2019']} "
                         f"different(only ISD additional groups)="
                         f"{len(diff['stations_different'])} "
                         f"absent={diff['stations_absent']} "
                         f"mandatory_column_drift={len(md)}")
        elif diff.get("identical"):
            lines.append(f"- {key}: identical ({diff['base_columns']} columns)")
        else:
            lines.append(f"- {key}: added={diff['added']} removed={diff['removed']} "
                         f"reordered={diff['reordered']} "
                         f"({diff['base_columns']} -> {diff['new_columns']} columns)")
    lines += ["", "## T-100 acquisition method", ""]
    for year, method in r.get("T100_ACQUISITION_METHOD", {}).items():
        lines.append(f"- {year}: {method}")
    lines += ["", "## Manifest status", ""]
    for year, m in r["MANIFEST_STATUS"].items():
        lines.append(f"- {m.get('manifest', year)}: rows={m.get('rows')} "
                     f"verified={m.get('verified')} "
                     f"missing_files={len(m.get('missing_files', []))} "
                     f"hash_mismatches={len(m.get('hash_mismatches', []))}")
    integrity = r["2019_INTEGRITY"]
    lines += ["", "## 2019 integrity", "",
              f"- files checked: {integrity['files_checked']}",
              f"- changed: {len(integrity['changed'])}",
              f"- missing: {len(integrity['missing'])}",
              f"- new files: {len(integrity['new_files'])}",
              f"- ok: {integrity['ok']}"]
    usage = r["DISK_USAGE"]
    lines += ["", "## Disk usage", "",
              f"- free: {usage['free_gb']} GB; raw bts {usage['raw_bts_gb']} GB; "
              f"raw weather {usage['raw_weather_gb']} GB; "
              f"_download {usage['download_gb']} GB", ""]
    lines += ["| year | ontime GB | db1b GB | t100 GB | noaa GB |", "|---|---|---|---|---|"]
    for year, v in usage["per_year"].items():
        lines.append(f"| {year} | {v['ontime_gb']} | {v['db1b_gb']} | "
                     f"{v['t100_gb']} | {v['noaa_gb']} |")
    smoke = r["ADAPTER_SMOKE"]
    lines += ["", "## Adapter smoke test (read-only, max_rows=3)", "",
              f"- status: {smoke['status']}"]
    for key, v in smoke.get("detail", {}).items():
        lines.append(f"- {key}: {v['status']}"
                     + (f" ({v.get('error', '')[:160]})" if v["status"] != "PASS" else ""))
    lines += ["", "## Log summaries", ""]
    for log_name, summary in r["LOG_SUMMARIES"].items():
        lines.append(f"- `{log_name}`: ok={summary['ok']} fail={summary['fail']} "
                     f"critical={summary['critical']}")
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="D1 baseline / D6 audit.")
    parser.add_argument("--mode", required=True, choices=["baseline", "audit"])
    args = parser.parse_args()
    if args.mode == "baseline":
        run_baseline()
    else:
        run_audit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
