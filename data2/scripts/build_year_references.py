# -*- coding: utf-8 -*-
"""Per-year M2 reference one-shot build (M5-b P1).

    python data2/scripts/build_year_references.py --years 2019 2020

For each year Y, fits ONCE (shared by every N in the cohort-size study):
  taxi / turnaround        - reused from PRE_MULTIYEAR_V1/{Y} (M4b, Y-H1)
  downstream exposure      - built from Y-H1 on-time train rows
  passenger (DB1B)         - Coupon Q1+Q2 of Y only
  T-100 expected pax       - annual file read, rows filtered MONTH <= 6
  connection share (DB1B)  - Coupon Q1+Q2 of Y only
  seven train scales       - Y-H1 on-time rows (cohort-size independent)

Hard correction 1: the annual file is storage granularity, not admissibility
granularity - nothing later than Y-06-30 may enter any fit.
Hard correction 8: every artifact records experiment_year / fit_start /
fit_end / dataset_instance_id / reference_contract_id.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from model.PRE.cohort import split_for_date_multiyear
from model.PRE.reference.data2_m2_train_fit import (
    compute_train_scales,
    fit_passenger_consequence_references,
    fit_train_references,
)
from model.PRE.reference.exposure_data2 import (
    data2_downstream_exposure_from_payload,
)
from model.PRE.reference.passenger_data2 import (
    data2_passenger_reference_from_payload,
)
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import (
    data2_turnaround_reference_from_payload,
)
from model.PRE.streaming.data2 import load_timezones, ontime_paths

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
RAW = DATA2 / "raw"
PRE_ROOT = REPO / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
INSTANCE_ID = "data2_2017_2022"
REFERENCE_CONTRACT_ID = "YEAR_SPECIFIC_H1_M2_REFERENCES_V1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now_iso()}] {message}", flush=True)


def sha256_json(payload) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   default=str).encode("utf-8")).hexdigest()


def normalize(payload: dict, *, year: int, kind: str) -> dict:
    """M5 metadata re-bind + correction-8 fields, applied uniformly."""
    payload["dataset_instance_id"] = INSTANCE_ID
    payload["experiment_year"] = year
    payload["fit_start"] = f"{year}-01-01"
    payload["fit_end"] = f"{year}-06-30"
    payload["reference_contract_id"] = REFERENCE_CONTRACT_ID
    payload["reference_kind"] = kind
    payload.pop("artifact_hash", None)
    payload["artifact_hash"] = sha256_json(payload)
    return payload


def _expected_pax_payload(reference) -> dict:
    """Serialize the ExpectedPassengersReference dataclass to the payload
    shape read by expected_passengers_reference_from_payload (round-trip)."""
    return {
        "reference_id": reference.reference_id,
        "reference_unit": reference.reference_unit,
        "grain": reference.grain,
        "fallback_hierarchy": list(reference.fallback_hierarchy),
        "fit_partition": reference.fit_partition,
        "source": reference.source,
        "support_state": reference.support_state.value,
        "evidence_class": reference.evidence_class.value,
        "lineage_hash": reference.lineage_hash,
        "excluded_rows": int(reference.excluded_rows),
        "cells": [
            {
                "key": list(cell.key),
                "reference_value": cell.reference_value,
                "grain": cell.grain,
                "fallback_level": cell.fallback_level,
                "numerator_passengers": cell.numerator_passengers,
                "denominator_departures_performed":
                    cell.denominator_departures_performed,
                "sample_size": cell.sample_size,
                "support_state": cell.support_state.value,
                "reference_id": cell.reference_id,
                "lineage_hash": cell.lineage_hash,
            }
            for cell in reference.cells
        ],
    }


def _connection_share_payload(reference) -> dict:
    """Serialize the ConnectionShareReference dataclass to the payload shape
    read by connection_share_reference_from_payload (round-trip)."""
    return {
        "reference_id": reference.reference_id,
        "connection_share": reference.connection_share,
        "total_passenger_weight": reference.total_passenger_weight,
        "connecting_passenger_weight": reference.connecting_passenger_weight,
        "grain": reference.grain,
        "fallback_hierarchy": list(reference.fallback_hierarchy),
        "fit_partition": reference.fit_partition,
        "source": reference.source,
        "support_state": reference.support_state.value,
        "evidence_class": reference.evidence_class.value,
        "lineage_hash": reference.lineage_hash,
        "excluded_rows": int(reference.excluded_rows),
        "cells": [
            {
                "key": list(cell.key),
                "connection_share": cell.connection_share,
                "total_passenger_weight": cell.total_passenger_weight,
                "connecting_passenger_weight": cell.connecting_passenger_weight,
                "grain": cell.grain,
                "fallback_level": cell.fallback_level,
                "sample_size": cell.sample_size,
                "support_state": cell.support_state.value,
                "reference_id": cell.reference_id,
                "lineage_hash": cell.lineage_hash,
            }
            for cell in reference.cells
        ],
    }


def build_year(year: int, output_root: Path | None = None) -> dict:
    base = Path(output_root) if output_root else PRE_ROOT
    out = base / str(year) / "M2_REFERENCES"
    out.mkdir(parents=True, exist_ok=True)
    zones = load_timezones(DATA2 / "refs" / "us_airport_timezones.csv")

    # ---- 1) Y-H1 on-time canonical rows (full train population, N-independent)
    log(f"{year}: streaming Y-H1 on-time rows (months 1-6)")
    from model.PRE.reference.data2_m2_train_fit import iter_train_rows
    paths = ontime_paths(REPO, (1, 2, 3, 4, 5, 6), year=year)
    rows = []
    for path in paths:
        rows.extend(iter_train_rows((path,), zones))
    # Reference-legality gate: the reference builders hard-require these keys
    # non-empty; a row missing one could never enter any reference, so it is
    # dropped explicitly (and counted) instead of failing mid-fit.  2019 H1
    # drops zero rows, so the 2019 bundle is unchanged by this gate.
    from model.PRE.reference.turnaround_data2 import _REQUIRED_ROW_KEYS
    before = len(rows)
    rows = [row for row in rows
            if all(row.get(key) not in (None, "") for key in _REQUIRED_ROW_KEYS)]
    log(f"{year}: Y-H1 rows = {len(rows)} (reference-legality gate dropped "
        f"{before - len(rows)})")

    # Non-physical rotations (a successor departing before -- or implausibly
    # long after -- its predecessor arrives) can never be a gate-to-gate
    # turnaround sample.  The headroom population already excludes them; the
    # reference fit would otherwise abort on the first one.  Apply the same
    # exclusion rule here by dropping the offending flights and re-chaining,
    # and record how many were removed.
    from model.PRE.episode.builder import build_data2_episode_records
    from model.PRE.reference.turnaround_data2 import MAX_GAP_MINUTES
    dropped_flights: set[str] = set()
    by_id = {row["flight_id"]: row for row in rows}
    passes = 0
    while passes < 8:
        passes += 1
        episodes = build_data2_episode_records(
            [row for row in rows if row["flight_id"] not in dropped_flights],
            max_gap_minutes=MAX_GAP_MINUTES)
        offending: set[str] = set()
        for episode in episodes:
            predecessor = by_id[episode.predecessor_flight_id]
            successor = by_id[episode.successor_flight_id]
            gap = (successor["actual_departure_utc"]
                   - predecessor["actual_arrival_utc"]).total_seconds() / 60.0
            if gap <= 0 or gap > MAX_GAP_MINUTES:
                offending |= {episode.predecessor_flight_id,
                              episode.successor_flight_id}
        if not offending:
            break
        dropped_flights |= offending
    if dropped_flights:
        rows = [row for row in rows if row["flight_id"] not in dropped_flights]
    log(f"{year}: non-physical rotation flights excluded = "
        f"{len(dropped_flights)} ({passes} chaining passes)")

    # ---- 2) fit_train_references: turnaround + exposure + passenger (Y-H1)
    log(f"{year}: fit_train_references (turnaround/exposure/passenger)")
    references = fit_train_references(rows, root=REPO,
                                      fit_period=f"{year}-H1", year=year)

    # ---- 3) fit_passenger_consequence_references: T-100 + connection share
    log(f"{year}: fit_passenger_consequence_references (T100 MONTH<=6, DB1B Q1+Q2)")
    consequence = fit_passenger_consequence_references(
        root=REPO, fit_period=f"{year}-H1", year=year)

    # ---- 4) seven train scales (Y-H1 rows, cohort-size independent)
    pax_ref = consequence["expected_pax"]
    conn_ref = consequence["connection_share"]
    scales = compute_train_scales(
        rows,
        references,
        turnaround_ref=data2_turnaround_reference_from_payload(
            references["turnaround"]),
        taxi_ref=data2_taxi_reference_from_payload(references["taxi"]),
        exposure_ref=data2_downstream_exposure_from_payload(
            references["downstream_exposure"]),
        passenger_ref=data2_passenger_reference_from_payload(
            references["passenger"]),
        expected_pax_reference=pax_ref,
        connection_share_reference=conn_ref,
    )

    # ---- 5) assemble + normalize + write
    bundle = {}
    for kind, payload in (
            ("taxi", references["taxi"]),
            ("turnaround", references["turnaround"]),
            ("downstream_exposure", references["downstream_exposure"]),
            ("passenger", references["passenger"]),
            ("expected_passengers",
             _expected_pax_payload(consequence["expected_pax"])),
            ("connection_share",
             _connection_share_payload(consequence["connection_share"]))):
        payload = dict(payload)
        payload["reference_period"] = f"{year}-H1"
        payload = normalize(payload, year=year, kind=kind)
        bundle[kind] = payload
        (out / f"M2_{kind.upper()}_REFERENCE_{year}-H1.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8")

    scale_payload = {
        "schema_version": "M2_DATA2_TRAIN_SCALES_V1",
        "experiment_year": year,
        "fit_period": f"{year}-H1",
        "dataset_instance_id": INSTANCE_ID,
        "reference_contract_id": REFERENCE_CONTRACT_ID,
        "scales": scales,
    }
    scale_payload["bundle_hash"] = sha256_json(scale_payload)
    (out / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json").write_text(
        json.dumps(scale_payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8")

    bundle_manifest = {
        "schema_version": "M2_REFERENCE_BUNDLE_V1",
        "year": year,
        "dataset_instance_id": INSTANCE_ID,
        "reference_contract_id": REFERENCE_CONTRACT_ID,
        "fit_window": {"start": f"{year}-01-01", "end": f"{year}-06-30"},
        "m2_reference_fixity": "fit once per year; shared across all N (correction 2)",
        "t100_admissibility": "YEAR == Y and MONTH <= 6",
        "db1b_admissibility": "Q1 + Q2 of Y",
        "payload_hashes": {kind: sha256_json(payload)
                           for kind, payload in bundle.items()},
        "scale_median_preview": {k: v.get("median") for k, v in scales.items()},
        "non_physical_rotation_flights_excluded": len(dropped_flights),
        "created_at_utc": now_iso(),
    }
    (out / "M2_REFERENCE_BUNDLE_MANIFEST.json").write_text(
        json.dumps(bundle_manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8")
    log(f"{year}: M2 references written -> {out}")
    return bundle_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=[2019, 2020])
    parser.add_argument("--output-root", default=None,
                        help="write the M2 reference bundle under this root "
                             "(default: PRE_MULTIYEAR_V1)")
    args = parser.parse_args()
    for year in args.years:
        manifest = build_year(year, output_root=args.output_root)
        log(f"{year} done: payloads={len(manifest['payload_hashes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
