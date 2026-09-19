"""Freeze-precheck (2026-09-19): correct the F_continuity Train scale.

Why this exists
---------------
``artifacts/diagnostics/passenger_reference_freeze_v4/M2_SEVEN_COMPONENT_TRAIN_SCALES.json``
computed every principal positive-Train median of the seven consequences. The
``F_continuity`` component was computed with the superseded (uncorrected) Data
Gate turnaround reference ``sha256:7c6ac016...``. The freeze-precheck audit
showed that reference is *not* stale metadata: it resolves the M2
node-reference bundle at decision time through
``exp.exp2.development_inputs._reference_payloads`` ->
``model.M2.context.load_data2_reference_bundle`` -> ``M2ConsequenceService`` ->
``F_continuity = max(0, R_IB - turnaround_reference)``.

The V2 chain now binds the corrected Data Gate A2 reference
(``sha256:aa241b90...``, BTS signed-delay semantic correction). Because
``F_continuity`` reads that reference, its Train normalization scale has to be
recomputed from the same reference. The scale *rule* does not change
(``Median_Train(q_k | q_k > 0)``); only the reference input does.

Scope guards
------------
- Train partition only (2019-01..06). Final Test months are never opened.
- No M1 retraining and no manuscript/estimand/consequence redefinition.
- The only recomputed component is ``F_continuity``; the other four principal
  V5 components do not read the turnaround reference and stay inherited from
  the V4 scale artifact.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from array import array
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Sequence

if __package__ in (None, ""):  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.PRE.reference.data2_m2_train_fit import iter_train_rows, ontime_paths
from model.PRE.reference.turnaround_data2 import (
    data2_turnaround_reference_from_payload,
)
from model.PRE.streaming.data2 import load_timezones
from model.common.identity import content_id

from validation.v2_phase5.common import (  # noqa: E402
    PROJECT_ROOT,
    file_hash,
    read_json,
    write_json,
)

SCHEMA_VERSION = "M2_V5_F_CONTINUITY_SCALE_CORRECTION_V1"
COMPONENT = "F_continuity"
QUANTITY_DEFINITION = "max(0, R_IB - turnaround_reference)"
SCALE_RULE = "Median_Train(q_k | q_k > 0)"
FIT_PERIOD = "2019-H1"
FIT_MONTHS = (1, 2, 3, 4, 5, 6)

CORRECTED_REFERENCE_ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_v2_data_gate_a2"
    / "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
)
SUPERSEDED_REFERENCE_ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v5_development_freeze"
    / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
)
V4_SCALE_ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "passenger_reference_freeze_v4"
    / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json"
)
OUTPUT_ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_freeze_precheck"
    / "M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json"
)

#: The four V5 principal components that never read the turnaround reference.
INHERITED_FROM_V4 = ("F_execution", "F_propagation", "P_time", "R_operating")
#: V4-only medians replaced by assumption event normalization in V5.
V4_ONLY_EVENT_COMPONENTS = ("P_itinerary", "P_service")

ProgressHook = Callable[[str], None]


def _log(message: str) -> None:
    print(f"[scale-correction] {message}", flush=True)


class ContinuityDatabase:
    """SQLite staging table mirroring the frozen V4 train-scale scanner."""

    COLUMNS = (
        "dataset TEXT, namespace TEXT, aircraft TEXT, flight TEXT, origin TEXT, "
        "destination TEXT, scheduled_departure REAL, scheduled_arrival REAL, "
        "actual_departure REAL, actual_arrival REAL"
    )

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute(f"CREATE TABLE flights ({self.COLUMNS})")

    def insert(self, rows: Sequence[tuple[Any, ...]]) -> None:
        self.connection.executemany(
            "INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?)", rows
        )

    def commit(self) -> None:
        self.connection.commit()

    def ordered(self):
        return self.connection.execute(
            "SELECT dataset, namespace, aircraft, flight, origin, destination, "
            "scheduled_departure, scheduled_arrival, actual_departure, "
            "actual_arrival FROM flights ORDER BY dataset, namespace, aircraft, "
            "actual_departure, actual_arrival, flight"
        )

    def close(self) -> None:
        self.connection.close()
        self.path.unlink(missing_ok=True)


def _row_tuple(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(row["dataset_instance_id"]),
        str(row["aircraft_id_namespace"]),
        str(row["aircraft_id"]),
        str(row["flight_id"]),
        str(row["origin_airport_id"]),
        str(row["destination_airport_id"]),
        row["event_start_time"].timestamp(),
        row["event_end_time"].timestamp(),
        row["actual_departure_utc"].timestamp(),
        row["actual_arrival_utc"].timestamp(),
    )


def scan_f_continuity(
    reference,
    *,
    months: Sequence[int] = FIT_MONTHS,
    root: Path = PROJECT_ROOT,
    sqlite_path: Path | None = None,
    progress: ProgressHook | None = None,
) -> dict[str, Any]:
    """Stream the Train continuity population and collect positive F_continuity.

    Byte-for-byte the same population rule as the frozen V4 scanner: same
    aircraft, airport continuity, strictly ordered actual and scheduled times,
    actual gate gap <= 360 minutes. Only the turnaround reference differs.
    """
    if not set(months) <= set(range(1, 7)):
        raise ValueError("SCALE_CORRECTION_MONTHS_MUST_STAY_INSIDE_TRAIN")
    paths = ontime_paths(root, tuple(months))
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    staging = sqlite_path or (root / "tmp" / "v2_freeze_precheck_continuity.sqlite")
    database = ContinuityDatabase(staging)
    positives = array("d")
    population_rows = 0
    staged_rows = 0
    try:
        for path in paths:
            started = time.time()
            batch: list[tuple[Any, ...]] = []
            month_rows = 0
            for row in iter_train_rows((path,), zones):
                batch.append(_row_tuple(row))
                month_rows += 1
                if len(batch) >= 10_000:
                    database.insert(batch)
                    batch.clear()
            if batch:
                database.insert(batch)
            database.commit()
            staged_rows += month_rows
            if progress:
                progress(
                    f"staged {path.name}: {month_rows} rows in "
                    f"{time.time() - started:.1f}s (total {staged_rows})"
                )
        started = time.time()
        predecessor = None
        predecessor_key = None
        for current in database.ordered():
            current_key = (
                current[0],
                current[1],
                current[2],
                current[8],
                current[9],
                current[3],
            )
            if current_key == predecessor_key:
                raise RuntimeError("EPISODE_DUPLICATE_ORDERING_KEY")
            if predecessor is not None:
                same_aircraft = predecessor[:3] == current[:3]
                continuous = predecessor[5] == current[4]
                ordered_actuals = predecessor[9] < current[8]
                scheduled_window = predecessor[7] < current[6]
                gap_minutes = (current[8] - predecessor[9]) / 60.0
                if (
                    same_aircraft
                    and continuous
                    and ordered_actuals
                    and scheduled_window
                    and gap_minutes <= 360
                ):
                    cell = reference.lookup(predecessor[5])
                    if cell.value is not None:
                        population_rows += 1
                        q_turn = max(
                            0.0,
                            (predecessor[9] - predecessor[7]) / 60.0
                            - float(cell.value),
                        )
                        if q_turn > 0:
                            positives.append(q_turn)
            predecessor = current
            predecessor_key = current_key
        if progress:
            progress(
                f"continuity scan finished in {time.time() - started:.1f}s: "
                f"population_rows={population_rows} positive_n={len(positives)}"
            )
    finally:
        database.close()
    return {
        "population_rows": population_rows,
        "positive_n": len(positives),
        "median": float(median(positives)) if len(positives) else 0.0,
        "source_paths": [str(path) for path in paths],
        "source_hashes": [file_hash(path) for path in paths],
    }


def _reference_lineage() -> dict[str, Any]:
    corrected_payload = read_json(CORRECTED_REFERENCE_ARTIFACT)
    superseded_payload = read_json(SUPERSEDED_REFERENCE_ARTIFACT)
    return {
        "active_reference_id": corrected_payload["reference_id"],
        "active_manifest_freeze_id": corrected_payload["manifest_freeze_id"],
        "active_artifact_hash": corrected_payload["artifact_hash"],
        "active_path": str(CORRECTED_REFERENCE_ARTIFACT),
        "active_file_hash": file_hash(CORRECTED_REFERENCE_ARTIFACT),
        "active_global_value_minutes": corrected_payload["global_value_minutes"],
        "active_semantic_correction": corrected_payload.get("semantic_correction"),
        "superseded_reference_id": superseded_payload.get("reference_id"),
        "superseded_manifest_freeze_id": superseded_payload.get(
            "manifest_freeze_id"
        ),
        "superseded_artifact_hash": superseded_payload.get("artifact_hash"),
        "superseded_path": str(SUPERSEDED_REFERENCE_ARTIFACT),
        "superseded_file_hash": file_hash(SUPERSEDED_REFERENCE_ARTIFACT),
        "superseded_global_value_minutes": superseded_payload.get(
            "global_value_minutes"
        ),
    }


def recompute_f_continuity_scale(
    *,
    root: Path = PROJECT_ROOT,
    months: Sequence[int] = FIT_MONTHS,
    output: Path = OUTPUT_ARTIFACT,
    sqlite_path: Path | None = None,
    progress: ProgressHook | None = None,
) -> dict[str, Any]:
    """Recompute the F_continuity scale and materialize the V5 support artifact."""
    reference_payload = read_json(CORRECTED_REFERENCE_ARTIFACT)
    reference = data2_turnaround_reference_from_payload(reference_payload)
    scan = scan_f_continuity(
        reference, months=months, root=root, sqlite_path=sqlite_path, progress=progress
    )

    v4_payload = read_json(V4_SCALE_ARTIFACT)
    v4_component = v4_payload["components"][COMPONENT]
    if tuple(months) == tuple(FIT_MONTHS):
        # The continuity population never reads the reference, so a full
        # 2019-H1 scan has to reproduce the frozen V4 population exactly.
        if scan["population_rows"] != int(v4_component["population_rows"]):
            raise RuntimeError(
                "F_CONTINUITY_POPULATION_CHANGED:"
                f"{scan['population_rows']}!={v4_component['population_rows']}"
            )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "component": COMPONENT,
        "active_quantity_definition": QUANTITY_DEFINITION,
        "definition": QUANTITY_DEFINITION,
        "native_unit": "minutes",
        "unit": "minutes",
        "fit_partition": "TRAIN",
        "fit_period": FIT_PERIOD,
        "fit_year": 2019,
        "fit_months": list(months),
        "scale_rule": SCALE_RULE,
        "median": scan["median"],
        "positive_n": scan["positive_n"],
        "population_rows": scan["population_rows"],
        "source_paths": scan["source_paths"],
        "source_hashes": scan["source_hashes"],
        "reference_lineage": _reference_lineage(),
        "superseded_scale": {
            "path": str(V4_SCALE_ARTIFACT.relative_to(PROJECT_ROOT)),
            "artifact_hash": v4_payload["artifact_hash"],
            "median": v4_component["median"],
            "positive_n": v4_component["positive_n"],
            "population_rows": v4_component["population_rows"],
            "reason": (
                "F_continuity_CU_scale_was_computed_with_the_superseded_"
                "turnaround_reference_sha256_7c6ac016"
            ),
        },
        "v4_scale_artifact": {
            "path": str(V4_SCALE_ARTIFACT.relative_to(PROJECT_ROOT)),
            "artifact_hash": v4_payload["artifact_hash"],
            "file_hash": file_hash(V4_SCALE_ARTIFACT),
        },
        "inherited_from_v4_unchanged": {
            component: {
                "median": v4_payload["components"][component]["median"],
                "positive_n": v4_payload["components"][component]["positive_n"],
                "population_rows": v4_payload["components"][component][
                    "population_rows"
                ],
                "reason": "does_not_read_the_turnaround_reference",
            }
            for component in INHERITED_FROM_V4
        },
        "v4_only_event_components_not_used_by_v5": list(V4_ONLY_EVENT_COMPONENTS),
        "stage2_turnaround_lower_bound": {
            "note": (
                "T^{turn,lb} = Q20(Train) is a Stage-II lower-tail support "
                "quantity and is NOT the M2 node-reference median"
            )
        },
        "final_test_access_count": 0,
        "paper_full_run": False,
    }
    payload["artifact_hash"] = content_id(payload)
    write_json(output, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        type=int,
        nargs="*",
        default=list(FIT_MONTHS),
        help="Train months to scan (default: 1..6); used for timing probes.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_ARTIFACT,
        help="Destination artifact path.",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="Optional staging database path.",
    )
    arguments = parser.parse_args(argv)
    started = time.time()
    payload = recompute_f_continuity_scale(
        months=tuple(arguments.months),
        output=arguments.output,
        sqlite_path=arguments.sqlite,
        progress=_log,
    )
    _log(
        f"done in {time.time() - started:.1f}s: median={payload['median']} "
        f"positive_n={payload['positive_n']} "
        f"population_rows={payload['population_rows']} "
        f"superseded_median={payload['superseded_scale']['median']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
