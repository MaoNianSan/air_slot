# -*- coding: utf-8 -*-
"""Fetch Data2 raw extensions (2017/2018 and 2020-2022): BTS On-Time / DB1B /
T-100 / NOAA ISD.

One dataset-year per invocation:

    python fetch_data2_year.py --dataset ontime --year 2017
    python fetch_data2_year.py --dataset db1b   --year 2017
    python fetch_data2_year.py --dataset noaa   --year 2017
    python fetch_data2_year.py --dataset t100   --year 2017

T-100 acquisition order: (1) any zip already present in
data2/_download/bts/t100/<year>/ (validated by CRC + schema + YEAR column),
(2) programmatic replay of the official TranStats WebForms download page for
T-100 Segment (All Carriers) - no browser automation, no guessed static URLs,
(3) BLOCKED_MANUAL_DOWNLOAD_REQUIRED.

Fail-soft: per-month / per-quarter / per-station failures are logged and the
run continues. Hard stops (exit 2): wrong repo/branch, any operation that
would touch frozen 2019 raw, free disk < 80 GB, 2019 baseline integrity
failure, or downloaded content that is clearly not the registered official
product. Never overwrites existing raw files; reruns skip completed work.

Log: data2/logs/download_{dataset}_{year}.log  (FAILURE_JSON / SUMMARY_JSON lines)
Manifest: data2/manifests/data2_bts_{year}_sha256.csv (Path,Hash,Type,SourceZip,
data2-relative paths, uppercase SHA256, CRLF - same contract as
data2_bts_2019_sha256.csv).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib import request as url_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin

REPO = Path(__file__).resolve().parents[3]
DATA2 = REPO / "data2"
BRANCH_REQUIRED = "v2/paper-primary"
MIN_FREE_GB = 80.0
ALLOWED_YEARS = (2017, 2018, 2020, 2021, 2022)   # 2019 raw is frozen
MANIFEST_HEADER = ["Path", "Hash", "Type", "SourceZip"]

REQUIRED_ONTIME = ["FlightDate", "Reporting_Airline", "Tail_Number",
                   "Flight_Number_Reporting_Airline", "Origin", "Dest",
                   "CRSDepTime", "CRSArrTime"]
REQUIRED_DB1B = ["ItinID", "MktID", "Passengers", "Origin", "Dest"]
REQUIRED_T100 = ["PASSENGERS", "SEATS", "AIRCRAFT_TYPE", "ORIGIN", "DEST",
                 "YEAR", "MONTH"]
REQUIRED_NOAA = ["STATION", "DATE", "WND", "CIG", "VIS", "TMP", "DEW"]

PREZIP = "https://transtats.bts.gov/PREZIP/"
NOAA_URL = "https://www.ncei.noaa.gov/data/global-hourly/access/{year}/{station}.csv"
T100_WEBFORM_URL = ("https://www.transtats.bts.gov/DL_SelectFields.aspx"
                    "?QO_fu146_anzr=Nv4+Pn44vr45&gnoyr_VQ=FMG")
T100_TABLE_NAME = "T_T100_SEGMENT_ALL_CARRIER.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (AirSlot data2 raw sync; research use)"}


class Critical(Exception):
    """Hard-stop condition (see module docstring)."""


LOG = logging.getLogger("fetch")
FAILURES: list[dict] = []


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 10 ** 9


def guard_disk(path: Path) -> None:
    free = free_gb(path)
    if free < MIN_FREE_GB:
        raise Critical(f"DISK_LOW: {free:.1f} GB free < {MIN_FREE_GB:.0f} GB at {path}")


def guard_branch() -> None:
    out = subprocess.run(["git", "-C", str(REPO), "branch", "--show-current"],
                         capture_output=True, text=True)
    branch = out.stdout.strip()
    if branch != BRANCH_REQUIRED:
        raise Critical(f"WRONG_BRANCH: {branch!r} != {BRANCH_REQUIRED!r}")


def guard_2019_target(path: Path) -> None:
    if "2019" in path.parts:
        raise Critical(f"WOULD_TOUCH_2019: {path}")


def guard_2019_baseline() -> None:
    baseline = DATA2 / "reports" / "data2_raw_2019_baseline_sha256.csv"
    if not baseline.is_file():
        LOG.warning("2019 baseline report missing; skipping pre-fetch integrity check")
        return
    checked = changed = 0
    with baseline.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            checked += 1
            path = REPO / row["Path"]
            if not path.is_file() or sha256_file(path) != row["SHA256"]:
                changed += 1
                LOG.error("2019 baseline mismatch: %s", row["Path"])
    if changed:
        raise Critical(
            f"CRITICAL_2019_INTEGRITY_FAILURE: {changed}/{checked} baseline files changed")
    LOG.info("2019 baseline verified: %d files unchanged", checked)


class Manifest:
    """Per-year sha256 manifest, 2019 contract: Path,Hash,Type,SourceZip / CRLF."""

    def __init__(self, year: int):
        self.year = year
        self.path = DATA2 / "manifests" / f"data2_bts_{year}_sha256.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.existing: dict[str, str] = {}
        append_mode = self.path.is_file()
        if append_mode:
            with self.path.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.reader(stream)
                header = next(reader, None)
                if header != MANIFEST_HEADER:
                    raise Critical(
                        f"unexpected manifest header in {self.path}: {header}")
                for row in reader:
                    if row:
                        self.existing[row[0]] = row[1] if len(row) > 1 else ""
        else:
            with self.path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream, lineterminator="\r\n").writerow(MANIFEST_HEADER)

    def add(self, rel: str, sha: str, type_: str, source: str) -> None:
        if rel in self.existing:
            return
        with self.path.open("a", newline="", encoding="utf-8") as stream:
            csv.writer(stream, lineterminator="\r\n").writerow([rel, sha, type_, source])
        self.existing[rel] = sha


def record_failure(dataset: str, year: int, partition: str, source: str,
                   error: str, retries: int, status: str = "FAIL") -> None:
    entry = {"dataset": dataset, "year": year, "partition": partition,
             "source": source, "error": error, "retries": retries, "status": status}
    FAILURES.append(entry)
    LOG.error("FAILURE_JSON %s", json.dumps(entry, ensure_ascii=False))


def download(url: str, dest: Path, *, expect_zip: bool, retries: int = 5,
             backoffs=(10, 30, 60, 120, 240)) -> tuple[str, int] | None:
    """Stream url -> dest atomically via .part. Returns (sha256, size) or None."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            guard_disk(dest.parent)
            if tmp.exists():
                tmp.unlink()
            request = url_request.Request(url, headers=HEADERS)
            with url_request.urlopen(request, timeout=120) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                expected = response.headers.get("Content-Length")
                digest = hashlib.sha256()
                size = 0
                with tmp.open("wb") as out:
                    while True:
                        block = response.read(1 << 20)
                        if not block:
                            break
                        out.write(block)
                        digest.update(block)
                        size += len(block)
            if expected and size != int(expected):
                raise RuntimeError(f"truncated: got {size} of {expected} bytes")
            if expect_zip:
                with tmp.open("rb") as probe:
                    if probe.read(4) != b"PK\x03\x04":
                        raise RuntimeError("not a zip archive")
            os.replace(tmp, dest)
            return digest.hexdigest().upper(), size
        except HTTPError as error:
            last_err = f"HTTP {error.code} {error.reason}"
            if error.code in (403, 404):
                LOG.error("DOWNLOAD_GONE url=%s attempt=%d/%d status=%s",
                          url, attempt, retries, last_err)
                break  # deterministic failure, no retry
        except (URLError, socket.timeout, ConnectionError, OSError) as error:
            last_err = f"{type(error).__name__}: {error}"
        except RuntimeError as error:
            last_err = str(error)
        if attempt < retries:
            sleep_s = backoffs[min(attempt - 1, len(backoffs) - 1)]
            LOG.warning("RETRY url=%s attempt=%d/%d err=%s sleep=%ds",
                        url, attempt, retries, last_err, sleep_s)
            time.sleep(sleep_s)
    if tmp.exists():
        tmp.unlink()
    LOG.error("DOWNLOAD_FAIL url=%s attempts=%d err=%s", url, retries, last_err)
    return None


def zip_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return [info.filename for info in archive.infolist() if not info.is_dir()]


def zip_test(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
    if bad is not None:
        raise RuntimeError(f"zip CRC failure at member {bad}")


def extract_member(zip_path: Path, member: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    guard_disk(target.parent)
    tmp = target.with_name(target.name + ".tmp")
    with zipfile.ZipFile(zip_path) as archive, archive.open(member) as src, \
            tmp.open("wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    os.replace(tmp, target)


def csv_header_and_first_row(path: Path) -> tuple[list[str], list[str]]:
    with path.open("rt", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None) or []
        first = next(reader, None) or []
    return header, first


def header_missing(path: Path, required: list[str]) -> list[str]:
    header, _ = csv_header_and_first_row(path)
    return [col for col in required if col not in header]


def first_row_value(path: Path, column: str) -> str | None:
    header, first = csv_header_and_first_row(path)
    if column in header and first and header.index(column) < len(first):
        return first[header.index(column)]
    return None


def last_row_value(path: Path, column: str) -> str | None:
    header, _ = csv_header_and_first_row(path)
    if column not in header:
        return None
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - 65536))
        tail = f.read()
    lines = [line for line in tail.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        row = next(csv.reader([lines[-1].decode("utf-8", "replace")]))
        index = header.index(column)
        return row[index] if len(row) > index else None
    except Exception:
        return None


def ensure_manifest_row(manifest: Manifest, path: Path, type_: str, source: str) -> None:
    rel = path.relative_to(DATA2).as_posix()
    if rel not in manifest.existing:
        manifest.add(rel, sha256_file(path), type_, source)


# ---------------------------------------------------------------- datasets --

def process_ontime(year: int, manifest: Manifest) -> tuple[int, int]:
    ok = fail = 0
    for month in range(1, 13):
        partition = f"month={month:02d}"
        zip_name = (f"On_Time_Reporting_Carrier_On_Time_Performance_"
                    f"1987_present_{year}_{month}.zip")
        url = PREZIP + zip_name
        stage = DATA2 / "_download" / "bts" / "ontime" / str(year) / zip_name
        guard_2019_target(stage)
        try:
            if stage.is_file():
                LOG.info("STAGE_EXISTS %s (%d bytes)", stage.name, stage.stat().st_size)
            else:
                if download(url, stage, expect_zip=True) is None:
                    record_failure("ontime", year, partition, url,
                                   "download failed after retries", 5)
                    fail += 1
                    continue
            ensure_manifest_row(manifest, stage, "archive_zip",
                                stage.relative_to(DATA2).as_posix())
            zip_test(stage)
            members = zip_members(stage)
            csv_members = [m for m in members if m.lower().endswith(".csv")]
            if not csv_members:
                raise Critical(f"NOT_TARGET_PRODUCT: no csv member in {stage.name}")
            member = next((m for m in csv_members if f"_{year}_{month}.csv" in m),
                          csv_members[0])
            target_dir = DATA2 / "raw" / "bts" / "ontime" / str(year) / partition
            target = target_dir / Path(member).name
            guard_2019_target(target)
            if target.exists():
                LOG.info("RAW_EXISTS %s", target)
            else:
                extract_member(stage, member, target)
                missing = header_missing(target, REQUIRED_ONTIME)
                if missing:
                    raise Critical(
                        f"NOT_TARGET_PRODUCT: {target.name} missing columns {missing}")
                flight_date = first_row_value(target, "FlightDate")
                if flight_date and f"-{month:02d}-" not in flight_date:
                    LOG.warning("MONTH_HINT_MISMATCH %s FlightDate=%s",
                                target.name, flight_date)
                LOG.info("EXTRACTED %s (%d bytes)", target, target.stat().st_size)
            ensure_manifest_row(manifest, target, "unpacked_csv",
                                stage.relative_to(DATA2).as_posix())
            if month == 1:
                readmes = [m for m in members if m.lower() == "readme.html"]
                if readmes:
                    readme_target = target_dir / "readme.html"
                    if not readme_target.exists():
                        extract_member(stage, readmes[0], readme_target)
                    ensure_manifest_row(manifest, readme_target, "readme",
                                        stage.relative_to(DATA2).as_posix())
            ok += 1
            LOG.info("PARTITION_OK ontime %d %s", year, partition)
        except Critical:
            raise
        except Exception as error:
            record_failure("ontime", year, partition, url,
                           f"{type(error).__name__}: {error}", 0)
            fail += 1
    return ok, fail


def process_db1b(year: int, manifest: Manifest) -> tuple[int, int]:
    ok = fail = 0
    jobs = [("coupon", "Coupon", q) for q in (1, 2, 3, 4)] + [("market", "Market", 1)]
    for product, product_label, quarter in jobs:
        partition = f"{product}/Q{quarter}"
        zip_name = (f"Origin_and_Destination_Survey_DB1B{product_label}"
                    f"_{year}_{quarter}.zip")
        url = PREZIP + zip_name
        stage = DATA2 / "_download" / "bts" / "db1b" / str(year) / product / zip_name
        guard_2019_target(stage)
        try:
            if stage.is_file():
                LOG.info("STAGE_EXISTS %s (%d bytes)", stage.name, stage.stat().st_size)
            else:
                if download(url, stage, expect_zip=True) is None:
                    record_failure("db1b", year, partition, url,
                                   "download failed after retries", 5)
                    fail += 1
                    continue
            ensure_manifest_row(manifest, stage, "archive_zip",
                                stage.relative_to(DATA2).as_posix())
            zip_test(stage)
            members = zip_members(stage)
            csv_members = [m for m in members if m.lower().endswith(".csv")]
            if not csv_members:
                raise Critical(f"NOT_TARGET_PRODUCT: no csv member in {stage.name}")
            member = next((m for m in csv_members if f"_{year}_{quarter}.csv" in m),
                          csv_members[0])
            target_dir = DATA2 / "raw" / "bts" / "db1b" / str(year) / product
            target = target_dir / Path(member).name
            guard_2019_target(target)
            if target.exists():
                LOG.info("RAW_EXISTS %s", target)
            else:
                extract_member(stage, member, target)
                missing = header_missing(target, REQUIRED_DB1B)
                if missing:
                    raise Critical(
                        f"NOT_TARGET_PRODUCT: {target.name} missing columns {missing}")
                row_year = first_row_value(target, "Year")
                row_quarter = first_row_value(target, "Quarter")
                if row_year and row_year.strip() != str(year):
                    LOG.warning("YEAR_HINT_MISMATCH %s Year=%s", target.name, row_year)
                if row_quarter and row_quarter.strip() != str(quarter):
                    LOG.warning("QUARTER_HINT_MISMATCH %s Quarter=%s",
                                target.name, row_quarter)
                LOG.info("EXTRACTED %s (%d bytes)", target, target.stat().st_size)
            ensure_manifest_row(manifest, target, "unpacked_csv",
                                stage.relative_to(DATA2).as_posix())
            if quarter == 1:
                readmes = [m for m in members if m.lower() == "readme.html"]
                if readmes:
                    readme_target = target_dir / "readme.html"
                    if not readme_target.exists():
                        extract_member(stage, readmes[0], readme_target)
                    ensure_manifest_row(manifest, readme_target, "readme",
                                        stage.relative_to(DATA2).as_posix())
            ok += 1
            LOG.info("PARTITION_OK db1b %d %s", year, partition)
        except Critical:
            raise
        except Exception as error:
            record_failure("db1b", year, partition, url,
                           f"{type(error).__name__}: {error}", 0)
            fail += 1
    return ok, fail


def noaa_station_list() -> list[str]:
    """Frozen station universe = the station files present in 2019 raw (48)."""
    root = DATA2 / "raw" / "weather" / "noaa" / "2019"
    stations = sorted(p.stem for p in root.glob("*.csv"))
    LOG.info("NOAA_TEMPLATE_STATIONS %d from %s", len(stations), root)
    return stations


def _noaa_download_one(station: str, year: int) -> dict:
    """Worker: download + validate one station-year file into staging.
    Promotion and manifest writes happen in the main thread."""
    url = NOAA_URL.format(year=year, station=station)
    stage = DATA2 / "_download" / "weather" / "noaa" / str(year) / f"{station}.csv"
    guard_2019_target(stage)
    if stage.is_file():
        return {"station": station, "status": "STAGED"}
    result = download(url, stage, expect_zip=False, retries=4, backoffs=(5, 15, 45, 90))
    if result is None:
        return {"station": station, "status": "FAIL",
                "error": "download failed after retries"}
    missing = header_missing(stage, REQUIRED_NOAA)
    if missing:
        raise Critical(f"NOT_TARGET_PRODUCT: {stage.name} missing columns {missing}")
    first = first_row_value(stage, "DATE") or ""
    last = last_row_value(stage, "DATE") or ""
    if not first.startswith(str(year)) or not last.startswith(str(year)):
        stage.unlink()
        return {"station": station, "status": "FAIL",
                "error": f"DATE coverage mismatch first={first} last={last}"}
    return {"station": station, "status": "STAGED"}


def process_noaa(year: int, manifest: Manifest) -> tuple[int, int]:
    stations = noaa_station_list()
    ok = fail = 0
    (DATA2 / "raw" / "weather" / "noaa" / str(year)).mkdir(parents=True,
                                                           exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_noaa_download_one, station, year): station
                   for station in stations}
        for future in futures:
            station = futures[future]
            try:
                outcome = future.result()
            except Critical:
                raise
            except Exception as error:
                outcome = {"station": station, "status": "FAIL",
                           "error": f"{type(error).__name__}: {error}"}
            if outcome["status"] != "STAGED":
                record_failure("noaa", year, f"station={outcome['station']}",
                               NOAA_URL.format(year=year, station=outcome["station"]),
                               outcome.get("error", "unknown"), 4)
                fail += 1
                continue
            stage = DATA2 / "_download" / "weather" / "noaa" / str(year) / \
                f"{outcome['station']}.csv"
            target = DATA2 / "raw" / "weather" / "noaa" / str(year) / \
                f"{outcome['station']}.csv"
            guard_2019_target(target)
            if not target.exists():
                tmp = target.with_name(target.name + ".tmp")
                shutil.copyfile(stage, tmp)
                os.replace(tmp, target)
                LOG.info("PROMOTED %s (%d bytes)", target, target.stat().st_size)
            ensure_manifest_row(manifest, target, "weather_csv",
                                "noaa_global_hourly_direct")
            ok += 1
    LOG.info("PARTITION_OK noaa %d %d/%d stations", year, ok, len(stations))
    return ok, fail


# ------------------------------------------------------------------- t100 --

def distinct_column_values(path: Path, column: str) -> set[str]:
    """Every distinct value of one CSV column (used for the YEAR gate)."""
    values: set[str] = set()
    with path.open("rt", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None) or []
        if column not in header:
            return values
        index = header.index(column)
        for row in reader:
            if len(row) > index:
                values.add(row[index].strip())
    return values


def _hidden_inputs(page: str) -> dict[str, str]:
    """ASP.NET hidden state (__VIEWSTATE / __EVENTVALIDATION / ...), never hardcoded."""
    import html as html_mod
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input[^>]*type=[\"']?hidden[\"']?[^>]*>", page, re.I):
        name = re.search(r"name=[\"']?([^\"'\s>/]+)", tag, re.I)
        value = re.search(r"value=[\"']([^\"']*)", tag, re.I)
        if name:
            fields[name.group(1)] = html_mod.unescape(value.group(1)) if value else ""
    return fields


def _field_checkboxes(page: str) -> list[str]:
    """Data-field checkbox names (the page's own field list, minus chk* controls)."""
    names: list[str] = []
    for tag in re.findall(r"<input[^>]*type=[\"']?checkbox[\"']?[^>]*>", page, re.I):
        name = re.search(r"name=[\"']?([^\"'\s>/]+)", tag, re.I)
        if name and not name.group(1).lower().startswith("chk"):
            names.append(name.group(1))
    return names


def _zip_link(page: str) -> str | None:
    """Generated-zip link inside a POST response HTML page, if any."""
    for attr in re.findall(r"(?:href|src)=[\"']([^\"']+)[\"']", page, re.I):
        cleaned = attr.strip()
        low = cleaned.lower()
        if low.endswith(".zip") or "download_table" in low or "/temp/" in low:
            return cleaned
    return None


def t100_webform_fetch(year: int, dest: Path, *, retries: int = 3,
                       backoffs=(30, 90, 180)) -> tuple[str, int] | None:
    """Programmatic TranStats WebForms acquisition of T-100 Segment (All Carriers).

    One cookie jar per attempt: GET the download page, replay the ASP.NET form
    (all 50 field checkboxes + Geography=All + Year=<year> + Period=All +
    zip output), then accept either a zip response body or an HTML page that
    carries the generated-zip link. Files are streamed to a .part file and
    atomically renamed; the YEAR gate runs later on the extracted CSV.
    """
    from http.cookiejar import CookieJar

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            guard_disk(dest.parent)
            opener = url_request.build_opener(
                url_request.HTTPCookieProcessor(CookieJar()))
            opener.addheaders = list(HEADERS.items())
            with opener.open(T100_WEBFORM_URL, timeout=120) as response:
                page = response.read().decode("utf-8", "replace")
            if not ("T-100" in page and "Segment" in page and "All Carriers" in page):
                raise Critical("NOT_TARGET_PRODUCT: page is not T-100 Segment "
                               "(All Carriers)")
            hidden = _hidden_inputs(page)
            fields = _field_checkboxes(page)
            if "__VIEWSTATE" not in hidden or "__EVENTVALIDATION" not in hidden:
                raise RuntimeError(f"ASP.NET state inputs missing: {sorted(hidden)}")
            if not fields:
                raise RuntimeError("no data-field checkboxes found on the page")
            form = dict(hidden)
            form.update({name: "on" for name in fields})
            form["cboGeography"] = "All"
            form["cboYear"] = str(year)
            form["cboPeriod"] = "All"
            form["chkDownloadZip"] = "on"
            form["btnDownload"] = "Download"
            LOG.info("T100_WEBFORM_POST year=%d fields=%d hidden=%d",
                     year, len(fields), len(hidden))
            request = url_request.Request(
                T100_WEBFORM_URL,
                data=urlencode(form).encode(),
                method="POST",
                headers={**HEADERS,
                         "Content-Type": "application/x-www-form-urlencoded",
                         "Referer": T100_WEBFORM_URL})
            with opener.open(request, timeout=1800) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                payload = response.read()
            if payload[:2] != b"PK":
                link = _zip_link(payload.decode("utf-8", "replace"))
                if link is None:
                    raise RuntimeError(
                        f"POST returned neither a zip body nor a zip link "
                        f"(content-type={content_type}, {len(payload)} bytes)")
                link_url = urljoin(T100_WEBFORM_URL, link)
                LOG.info("T100_WEBFORM_LINK %s", link_url)
                with opener.open(url_request.Request(
                        link_url,
                        headers={**HEADERS, "Referer": T100_WEBFORM_URL}),
                        timeout=900) as response:
                    payload = response.read()
                if payload[:2] != b"PK":
                    raise RuntimeError("generated download is not a zip")
            with tmp.open("wb") as out:
                out.write(payload)
            os.replace(tmp, dest)
            return sha256_file(dest), len(payload)
        except Critical:
            raise
        except Exception as error:
            last_err = f"{type(error).__name__}: {error}"
            LOG.warning("T100_WEBFORM_RETRY year=%d attempt=%d/%d err=%s",
                        year, attempt, retries, last_err)
            if attempt < retries:
                time.sleep(backoffs[min(attempt - 1, len(backoffs) - 1)])
    if tmp.exists():
        tmp.unlink()
    LOG.error("T100_WEBFORM_FAIL year=%d attempts=%d err=%s", year, retries, last_err)
    return None


def process_t100(year: int, manifest: Manifest) -> tuple[int, int]:
    ok = fail = 0
    stage_dir = DATA2 / "_download" / "bts" / "t100" / str(year)
    guard_2019_target(stage_dir)
    source_note = ""
    try:
        local_zips = sorted(stage_dir.glob("*.zip")) if stage_dir.is_dir() else []
        if local_zips:
            stage = local_zips[0]
            source_note = "local staging zip"
            LOG.info("T100_LOCAL_STAGE_ZIP %s (%d bytes)",
                     stage.name, stage.stat().st_size)
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stage = stage_dir / f"T_T100_SEGMENT_ALL_CARRIER_{stamp}.zip"
            source_note = "TranStats WebForms (programmatic)"
            if t100_webform_fetch(year, stage) is None:
                raise RuntimeError("official WebForms acquisition failed")
        ensure_manifest_row(manifest, stage, "archive_zip",
                            stage.relative_to(DATA2).as_posix())
        zip_test(stage)
        members = zip_members(stage)
        named = [m for m in members if Path(m).name == T100_TABLE_NAME]
        if not named:
            raise Critical(f"NOT_TARGET_PRODUCT: no {T100_TABLE_NAME} member in "
                           f"{stage.name}; members={members}")
        member = named[0]
        companions = [m for m in members if m != member]
        if companions:
            # WebForms-generated zips may carry a Documentation.csv companion
            LOG.info("T100_ZIP_COMPANIONS %s (not extracted)", companions)
        target = DATA2 / "raw" / "bts" / "t100" / str(year) / T100_TABLE_NAME
        guard_2019_target(target)
        if not target.exists():
            extract_member(stage, member, target)
            missing = header_missing(target, REQUIRED_T100)
            if missing:
                raise Critical(
                    f"NOT_TARGET_PRODUCT: {target.name} missing columns {missing}")
            years_seen = distinct_column_values(target, "YEAR")
            if years_seen != {str(year)}:
                target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"T-100 YEAR values {sorted(years_seen)} != [{year}]; rejected")
            LOG.info("EXTRACTED %s (%d bytes)", target, target.stat().st_size)
        ensure_manifest_row(manifest, target, "unpacked_csv",
                            stage.relative_to(DATA2).as_posix())
        ok += 1
        LOG.info("PARTITION_OK t100 %d (%s)", year, source_note)
    except Critical:
        raise
    except Exception as error:
        record_failure("t100", year, "full_year", "TranStats T-100 Segment "
                       "(All Carriers)", f"{type(error).__name__}: {error}", 0,
                       status="BLOCKED_MANUAL_DOWNLOAD_REQUIRED")
        LOG.error("T100_%d=BLOCKED_MANUAL_DOWNLOAD_REQUIRED", year)
        fail += 1
    return ok, fail


# ------------------------------------------------------------------- main --

def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one Data2 dataset-year.")
    parser.add_argument("--dataset", required=True,
                        choices=["ontime", "db1b", "noaa", "t100"])
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    dataset, year = args.dataset, args.year
    if year not in ALLOWED_YEARS:
        print(f"refusing year {year}: allowed {sorted(ALLOWED_YEARS)} "
              f"(2019 raw is frozen)")
        return 2

    log_path = DATA2 / "logs" / f"download_{dataset}_{year}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
        force=True,
    )
    start = now()
    LOG.info("RUN_START dataset=%s year=%d repo=%s", dataset, year, REPO)
    ok = fail = 0
    critical = False
    try:
        guard_branch()
        guard_disk(DATA2)
        guard_2019_baseline()
        manifest = Manifest(year)
        if dataset == "ontime":
            ok, fail = process_ontime(year, manifest)
        elif dataset == "db1b":
            ok, fail = process_db1b(year, manifest)
        elif dataset == "noaa":
            ok, fail = process_noaa(year, manifest)
        else:
            ok, fail = process_t100(year, manifest)
    except Critical as error:
        LOG.critical("CRITICAL %s", error)
        FAILURES.append({"dataset": dataset, "year": year, "partition": "RUN",
                         "source": "local", "error": str(error), "retries": 0,
                         "status": "CRITICAL"})
        critical = True

    summary = {"dataset": dataset, "year": year, "start": start, "end": now(),
               "ok": ok, "fail": fail, "critical": critical,
               "failures": FAILURES}
    LOG.info("SUMMARY_JSON %s", json.dumps(summary, ensure_ascii=False))
    return 2 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
