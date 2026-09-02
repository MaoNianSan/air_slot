"""Materialize the Passenger Consequence Reference refactor artifacts.

Reads only Data2 T-100, DB1B Coupon, the six Train On-Time months, and the
already frozen taxi reference. Outputs are additive diagnostics and a new M2
V3 registry. It never reads Final Test months or writes under ``data2``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from array import array
from pathlib import Path

import numpy as np

from model.M2.freeze import M2Data2FormalCuRegistry
from model.M2.passenger_reference_freeze import reference_payload
from model.PRE.reference.data2_m2_train_fit import (
    iter_train_rows,
    ontime_paths,
    fit_passenger_consequence_references,
)
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.streaming.data2 import load_timezones
from model.common.identity import content_id


def _write(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(values: list[float]) -> dict[str, float | int]:
    data = np.asarray(values, dtype=np.float64)
    return {"count": int(data.size), "min": float(data.min()), "median": float(np.median(data)), "max": float(data.max())}


def _passenger_scales(root: Path, expected, connection) -> dict[str, dict]:
    taxi_payload = json.loads((root / "artifacts" / "diagnostics" / "v5_development_freeze" / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json").read_text(encoding="utf-8"))
    taxi = data2_taxi_reference_from_payload(taxi_payload)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    arrays = {name: array("d") for name in ("P_time", "P_itinerary", "P_service")}
    population = {name: 0 for name in arrays}
    for row in iter_train_rows(ontime_paths(root, tuple(range(1, 7))), zones):
        taxi_value = taxi.lookup(row["origin_airport_id"])
        if taxi_value.value is None:
            continue
        departure_delay = max(0.0, (row["actual_departure_utc"] - row["event_start_time"]).total_seconds() / 60.0)
        excess_taxi = max(0.0, float(row["taxi_out_minutes"]) - float(taxi_value.value))
        d_to = departure_delay + excess_taxi
        month = row.get("month")
        quarter = None if month is None else (int(month) - 1) // 3 + 1
        pax = expected.lookup(row.get("carrier_id"), row["origin_airport_id"], row["destination_airport_id"], month)
        share = connection.lookup(row["origin_airport_id"], row["destination_airport_id"], quarter)
        if pax is None or share is None:
            continue
        expected_pax = float(pax.reference_value)
        expected_connecting = expected_pax * float(share.connection_share)
        for name in arrays:
            population[name] += 1
        if d_to > 0:
            arrays["P_time"].append(expected_pax * d_to)
        if d_to > 45.0 and expected_connecting > 0:
            arrays["P_itinerary"].append(expected_connecting)
        if d_to >= 180.0 and expected_pax > 0:
            arrays["P_service"].append(expected_pax)
    units = {
        "P_time": "passenger_minutes",
        "P_itinerary": "expected_disrupted_connecting_passenger_exposure",
        "P_service": "expected_long_delay_passenger_service_exposure",
    }
    definitions = {
        "P_time": "expected_passengers_per_flight * D_TO",
        "P_itinerary": "expected_passengers_per_flight * connection_share * I[D_TO > 45 minutes]",
        "P_service": "expected_passengers_per_flight * I[D_TO >= 180 minutes]",
    }
    scales = {}
    for name, values in arrays.items():
        if not values:
            raise RuntimeError(f"NO_POSITIVE_TRAIN_POPULATION:{name}")
        stats = _summary(values)
        scales[name] = {
            "median": stats["median"],
            "positive_n": stats["count"],
            "population_rows": population[name],
            "unit": units[name],
            "definition": definitions[name],
            "active_quantity_definition": definitions[name],
        }
    return scales


def materialize(root: Path) -> dict:
    artifact_dir = root / "artifacts" / "diagnostics" / "passenger_reference_freeze"
    fitted = fit_passenger_consequence_references(root=root)
    expected_payload = reference_payload(fitted["expected_pax"])
    expected_hash = _write(artifact_dir / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json", expected_payload)
    connection_payload = reference_payload(fitted["connection_share"])
    connection_hash = _write(artifact_dir / "DB1B_CONNECTION_SHARE_REFERENCE.json", connection_payload)
    scales = _passenger_scales(root, fitted["expected_pax"], fitted["connection_share"])
    scales_payload = {
        "schema_version": "PASSENGER_CONSEQUENCE_TRAIN_SCALES_V1",
        "fit_partition": "TRAIN",
        "scale_rule": "Median_Train(q_k | q_k > 0)",
        "components": scales,
        "final_test_access_count": 0,
        "paper_full_run": False,
    }
    scales_hash = _write(artifact_dir / "PASSENGER_CONSEQUENCE_TRAIN_SCALES.json", scales_payload)

    old_registry_path = root / "registries" / "m2_data2_formal_cu_v2.json"
    old = json.loads(old_registry_path.read_text(encoding="utf-8"))
    train_scales = {name: item for name, item in old["train_scale_artifact"].items() if name not in {"P_time"}}
    train_scales.update({
        name: {**item, "path": str((artifact_dir / "PASSENGER_CONSEQUENCE_TRAIN_SCALES.json").relative_to(root)), "artifact_hash": scales_hash}
        for name, item in scales.items()
    })
    registry_payload = {
        "registry_id": "M2_DATA2_FORMAL_CU_V3",
        "schema_version": "M2_DATA2_FORMAL_CU_V3",
        "formal_scope": ["F_continuity", "F_execution", "F_propagation", "P_time", "P_itinerary", "P_service", "R_operating"],
        "native_quantity_definitions": {
            **old["native_quantity_definitions"],
            **{name: {"definition": item["definition"], "unit": item["unit"], "driver": item["definition"]} for name, item in scales.items()},
        },
        "train_scale_artifact": train_scales,
        "reference_artifacts": {
            "turnaround": old["reference_artifacts"]["turnaround"],
            "taxi": old["reference_artifacts"]["taxi"],
            "downstream_exposure": old["reference_artifacts"]["downstream_exposure"],
            "expected_pax": {"path": str((artifact_dir / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json").relative_to(root)), "artifact_hash": expected_hash, "reference_id": fitted["expected_pax"].reference_id, "manifest_freeze_id": fitted["expected_pax"].lineage_hash},
            "connection_share": {"path": str((artifact_dir / "DB1B_CONNECTION_SHARE_REFERENCE.json").relative_to(root)), "artifact_hash": connection_hash, "reference_id": fitted["connection_share"].reference_id, "manifest_freeze_id": fitted["connection_share"].lineage_hash},
        },
        "component_weights": {name: 1.0 for name in ("F_continuity", "F_execution", "F_propagation", "P_time", "P_itinerary", "P_service", "R_operating")},
        "aggregation_rule": "SUM_OVER_SEVEN_ONLY_IF_ALL_SUPPORTED",
        "support_rule": "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY",
        "final_test_access_count": 0,
        "paper_full_run": False,
        "scientific_status": "FROZEN",
        "implementation_status": "MATCH",
        "numeric_scale_adoption": {"decision": "PASSENGER_CONSEQUENCE_REFERENCE_REFACTOR_20260902", "rule": "THREE_PASSENGER_COMPONENTS_USE_POSITIVE_TRAIN_MEDIANS", "final_test_access_count": 0},
    }
    registry = M2Data2FormalCuRegistry.model_validate(registry_payload)
    registry_payload["registry_hash"] = registry.digest()
    registry_hash = _write(root / "registries" / "m2_data2_formal_cu_v3.json", registry_payload)
    manifest = {
        "schema_version": "PASSENGER_REFERENCE_MANIFEST_V1",
        "passenger_reference_schema_version": "PASSENGER_REFERENCE_SCHEMA_V1",
        "fit_partition": "TRAIN",
        "sources": {str(path.relative_to(root)): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() for path in fitted["source_paths"]},
        "filter_rules": {"T100": "finite PASSENGERS; finite DEPARTURES_PERFORMED; DEPARTURES_PERFORMED > 0; PASSENGERS >= 0", "DB1B": "finite Passengers; Passengers >= 0; blank TripBreak is historical continuation reference only"},
        "row_counts": {"expected_pax_cells": len(fitted["expected_pax"].cells), "connection_share_cells": len(fitted["connection_share"].cells)},
        "excluded_rows": {"T100": fitted["expected_pax"].excluded_rows, "DB1B": fitted["connection_share"].excluded_rows},
        "support_counts": {"T100": sum(cell.support_state.value != "ABSTAIN" for cell in fitted["expected_pax"].cells), "DB1B": sum(cell.support_state.value != "ABSTAIN" for cell in fitted["connection_share"].cells)},
        "reference_summaries": {"T100": _summary([cell.reference_value for cell in fitted["expected_pax"].cells]), "DB1B": _summary([cell.connection_share for cell in fitted["connection_share"].cells])},
        "artifacts": {"expected_pax": expected_hash, "connection_share": connection_hash, "passenger_scales": scales_hash, "m2_registry_v3": registry_hash},
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "m4_rmb_mapping_registry": "M4_RMB_BASE_MAPPING_V2",
        "data1_modified": False,
        "data2_modified": False,
        "final_test_access_count": 0,
        "experiment_created": False,
    }
    manifest_hash = _write(artifact_dir / "PASSENGER_REFERENCE_MANIFEST.json", manifest)
    return {"artifact_dir": str(artifact_dir), "manifest_hash": manifest_hash, "scales": scales, "registry_hash": registry_hash}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(materialize(args.root.resolve()), sort_keys=True))
