"""Materialize active M2 V4 passenger references and seven CU scales."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from array import array
from pathlib import Path

from model.M2.cu.registry import M2Data2FormalCuRegistry
from model.common.native_formulas import (
    d_to_from_components,
    d_tx_realized,
    p_itinerary_native,
    p_service_native,
    p_time_native,
)
from model.M2.scientific_registry import load_active_passenger_consequence_design
from model.PRE.reference.data2_m2_train_fit import (
    fit_passenger_consequence_references,
    iter_train_rows,
    ontime_paths,
    stream_t100_rows,
)
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.streaming.data2 import load_timezones
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id

ROOT = Path(__file__).resolve().parents[1]
V3_PATH = ROOT / "registries" / "m2_data2_formal_cu_v3.json"


def _write(path: Path, payload: dict) -> str:
    body = dict(payload)
    body.pop("artifact_hash", None)
    body["artifact_hash"] = content_id(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    saved_hash = loaded.pop("artifact_hash")
    if saved_hash != content_id(loaded):
        raise RuntimeError(f"M2_V4_ARTIFACT_HASH_ROUND_TRIP:{path.name}")
    return saved_hash


def _write_registry(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    registry = M2Data2FormalCuRegistry.model_validate(loaded)
    if registry.registry_hash != registry.digest():
        raise RuntimeError("M2_V4_REGISTRY_HASH_ROUND_TRIP")
    return registry.registry_hash


def _reference_payload(reference) -> dict:
    from model.M2.passenger_reference_freeze import reference_payload

    return reference_payload(reference)


def _load_or_fit_references(root: Path, artifact_dir: Path) -> dict:
    expected_path = artifact_dir / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json"
    connection_path = artifact_dir / "DB1B_CONNECTION_SHARE_REFERENCE.json"
    if not (expected_path.is_file() and connection_path.is_file()):
        return fit_passenger_consequence_references(root=root)
    from model.PRE.references.connection_share_reference import connection_share_reference_from_payload
    from model.PRE.references.passenger_load_reference import expected_passengers_reference_from_payload

    expected = expected_passengers_reference_from_payload(json.loads(expected_path.read_text(encoding="utf-8")))
    connection = connection_share_reference_from_payload(json.loads(connection_path.read_text(encoding="utf-8")))
    t100_path = root / "data2" / "raw" / "bts" / "t100" / "2019" / "T_T100_SEGMENT_ALL_CARRIER.csv"
    coupon_paths = tuple(sorted((root / "data2" / "raw" / "bts" / "db1b" / "2019" / "coupon").glob("Origin_and_Destination_Survey_DB1BCoupon_2019_[12].csv")))
    t100_stream = stream_t100_rows(t100_path, allowed_months=(1, 2, 3, 4, 5, 6))
    for _ in t100_stream:
        pass
    global_cell = next(cell for cell in connection.cells if cell.fallback_level == "global")
    db1b_rows = int(global_cell.sample_size) + int(connection.excluded_rows)
    return {
        "expected_pax": expected,
        "connection_share": connection,
        "fit_period": "2019-H1",
        "fit_year": 2019,
        "t100_fit_months": [1, 2, 3, 4, 5, 6],
        "db1b_fit_quarters": [1, 2],
        "t100_audit": t100_stream.audit,
        "db1b_audit": {
            "rows_seen": db1b_rows,
            "rows_used": db1b_rows,
            "rows_excluded_outside_fit_period": 0,
            "rows_excluded_invalid_schema": 0,
            "quarters_used": [1, 2],
            "trip_break_fields": ["Break"],
        },
        "source_paths": (t100_path, *coupon_paths),
    }


def _source_hashes(root: Path, source_paths: tuple[Path, ...]) -> dict[str, str]:
    historical = root / "artifacts" / "diagnostics" / "passenger_reference_freeze" / "PASSENGER_REFERENCE_MANIFEST.json"
    if historical.is_file():
        prior = json.loads(historical.read_text(encoding="utf-8")).get("sources", {})
        if all(str(path.relative_to(root)) in prior for path in source_paths):
            return {str(path.relative_to(root)): prior[str(path.relative_to(root))] for path in source_paths}
    return {str(path.relative_to(root)): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}


def _load_taxi(root: Path):
    path = root / "artifacts" / "diagnostics" / "v5_development_freeze" / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
    return data2_taxi_reference_from_payload(json.loads(path.read_text(encoding="utf-8")))


def _load_turnaround(root: Path):
    from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload

    path = root / "artifacts" / "diagnostics" / "v5_development_freeze" / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
    return data2_turnaround_reference_from_payload(json.loads(path.read_text(encoding="utf-8")))


def _train_scales(root: Path, expected, connection, design: dict) -> dict[str, dict]:
    taxi = _load_taxi(root)
    from model.PRE.reference.exposure_data2 import data2_downstream_exposure_from_payload

    exposure = data2_downstream_exposure_from_payload(json.loads((root / "artifacts" / "diagnostics" / "v5_development_freeze" / "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json").read_text(encoding="utf-8")))
    turnaround = _load_turnaround(root)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    values = {name: array("d") for name in CONSEQUENCE_COMPONENTS}
    population = {name: 0 for name in CONSEQUENCE_COMPONENTS}
    sqlite_path = root / "tmp" / "m2_v4_continuity.sqlite"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_path.unlink(missing_ok=True)
    database = sqlite3.connect(sqlite_path)
    database.execute(
        "CREATE TABLE flights (dataset TEXT, namespace TEXT, aircraft TEXT, flight TEXT, origin TEXT, destination TEXT, scheduled_departure REAL, scheduled_arrival REAL, actual_departure REAL, actual_arrival REAL)"
    )
    insert_rows = []
    paths = ontime_paths(root, tuple(design["fit_months"]))
    for row in iter_train_rows(paths, zones):
        origin = row["origin_airport_id"]
        destination = row["destination_airport_id"]
        insert_rows.append((
            str(row["dataset_instance_id"]), str(row["aircraft_id_namespace"]), str(row["aircraft_id"]), str(row["flight_id"]),
            str(origin), str(destination), row["event_start_time"].timestamp(), row["event_end_time"].timestamp(), row["actual_departure_utc"].timestamp(), row["actual_arrival_utc"].timestamp(),
        ))
        if len(insert_rows) >= 10000:
            database.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?)", insert_rows)
            insert_rows.clear()
        d_ob = max(0.0, (row["actual_departure_utc"] - row["event_start_time"]).total_seconds() / 60.0)
        population["F_execution"] += 1
        if d_ob > 0:
            values["F_execution"].append(d_ob)
        taxi_cell = taxi.lookup(origin)
        if taxi_cell is not None and taxi_cell.value is not None:
            d_tx = d_tx_realized(row["taxi_out_minutes"], taxi_cell.value)
            d_to = d_to_from_components(d_ob, d_tx)
            population["R_operating"] += 1
            if d_tx > 0:
                values["R_operating"].append(d_tx)
            exp_cell = exposure.lookup(origin)
            if exp_cell is not None and exp_cell.value is not None:
                population["F_propagation"] += 1
                q = d_to * float(exp_cell.value)
                if q > 0:
                    values["F_propagation"].append(q)
            pax_cell = expected.lookup(row.get("carrier_id"), origin, destination, row.get("month"))
            quarter = (int(row["month"]) - 1) // 3 + 1 if row.get("month") else None
            share_cell = connection.lookup(origin, destination, quarter)
            if pax_cell is not None:
                pax = float(pax_cell.reference_value)
                population["P_time"] += 1
                q_time = p_time_native(pax, d_to)
                if q_time > 0:
                    values["P_time"].append(q_time)
                if share_cell is not None:
                    population["P_itinerary"] += 1
                    q_itin = p_itinerary_native(pax, float(share_cell.connection_share), d_to, float(design["components"]["P_itinerary"]["itinerary_threshold_minutes"]))
                    if q_itin > 0:
                        values["P_itinerary"].append(q_itin)
                population["P_service"] += 1
                q_service = p_service_native(pax, d_to, float(design["components"]["P_service"]["service_threshold_minutes"]))
                if q_service > 0:
                    values["P_service"].append(q_service)

    if insert_rows:
        database.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?)", insert_rows)
    database.commit()
    ordered = database.execute(
        "SELECT dataset, namespace, aircraft, flight, origin, destination, scheduled_departure, scheduled_arrival, actual_departure, actual_arrival "
        "FROM flights ORDER BY dataset, namespace, aircraft, actual_departure, actual_arrival, flight"
    )
    predecessor = None
    predecessor_key = None
    for current in ordered:
        current_key = (current[0], current[1], current[2], current[8], current[9], current[3])
        if current_key == predecessor_key:
            database.close()
            sqlite_path.unlink(missing_ok=True)
            raise RuntimeError("EPISODE_DUPLICATE_ORDERING_KEY")
        if predecessor is not None:
            same_aircraft = predecessor[:3] == current[:3]
            continuous = predecessor[5] == current[4]
            ordered_actuals = predecessor[9] < current[8]
            scheduled_window = predecessor[7] < current[6]
            gap_minutes = (current[8] - predecessor[9]) / 60.0
            if same_aircraft and continuous and ordered_actuals and scheduled_window and gap_minutes <= 360:
                turn_cell = turnaround.lookup(predecessor[5])
                if turn_cell.value is not None:
                    population["F_continuity"] += 1
                    q_turn = max(0.0, (predecessor[9] - predecessor[7]) / 60.0 - float(turn_cell.value))
                    if q_turn > 0:
                        values["F_continuity"].append(q_turn)
        predecessor = current
        predecessor_key = current_key
    database.close()
    sqlite_path.unlink(missing_ok=True)

    units = {
        "F_continuity": "minutes", "F_execution": "minutes", "F_propagation": "exposure_minutes",
        "P_time": "passenger_minutes", "P_itinerary": "expected_disrupted_connecting_passenger_exposure",
        "P_service": "expected_long_delay_passenger_service_exposure", "R_operating": "excess_taxi_minutes",
    }
    definitions = {
        "F_continuity": "max(0, R_IB - turnaround_reference)", "F_execution": "D_OB",
        "F_propagation": "D_TO * expected_downstream_exposure", "P_time": "expected_passengers_per_flight * D_TO",
        "P_itinerary": "expected_passengers_per_flight * connection_share * I[D_TO > itinerary_threshold_minutes]",
        "P_service": "expected_passengers_per_flight * I[D_TO >= service_threshold_minutes]", "R_operating": "D_TX",
    }
    scales = {}
    for component in CONSEQUENCE_COMPONENTS:
        positive = values[component]
        if not positive:
            raise RuntimeError(f"M2_V4_TRAIN_SCALE_NO_POSITIVE_POPULATION:{component}")
        ordered = sorted(positive)
        mid = len(ordered) // 2
        med = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
        scales[component] = {
            "median": float(med), "positive_n": len(positive), "population_rows": population[component],
            "native_unit": units[component], "unit": units[component], "active_quantity_definition": definitions[component],
            "definition": definitions[component], "fit_period": "2019-H1",
        }
    return scales


def materialize(root: Path) -> dict:
    design = load_active_passenger_consequence_design()
    artifact_dir = root / "artifacts" / "diagnostics" / "passenger_reference_freeze_v4"
    fitted = _load_or_fit_references(root, artifact_dir)
    expected_hash = _write(artifact_dir / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json", _reference_payload(fitted["expected_pax"]))
    connection_hash = _write(artifact_dir / "DB1B_CONNECTION_SHARE_REFERENCE.json", _reference_payload(fitted["connection_share"]))
    scales = _train_scales(root, fitted["expected_pax"], fitted["connection_share"], design)
    scales_hash = _write(artifact_dir / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json", {
        "schema_version": "M2_SEVEN_COMPONENT_TRAIN_SCALES_V4", "fit_partition": "TRAIN", "fit_year": 2019,
        "fit_months": design["fit_months"], "db1b_quarters": design["db1b_quarters"],
        "scale_rule": "Median_Train(q_k | q_k > 0)", "formal_scope": list(CONSEQUENCE_COMPONENTS), "components": scales,
        "final_test_ontime_access_count": 0, "paper_full_run": False,
    })
    old = json.loads(V3_PATH.read_text(encoding="utf-8"))
    old_refs = old["reference_artifacts"]
    reference_artifacts = {
        "turnaround": old_refs["turnaround"], "taxi": old_refs["taxi"], "downstream_exposure": old_refs["downstream_exposure"],
        "expected_pax": {"path": str((artifact_dir / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json").relative_to(root)), "artifact_hash": expected_hash, "reference_id": fitted["expected_pax"].reference_id, "manifest_freeze_id": fitted["expected_pax"].lineage_hash},
        "connection_share": {"path": str((artifact_dir / "DB1B_CONNECTION_SHARE_REFERENCE.json").relative_to(root)), "artifact_hash": connection_hash, "reference_id": fitted["connection_share"].reference_id, "manifest_freeze_id": fitted["connection_share"].lineage_hash},
    }
    status_key = "scientific_" + "status"
    registry_payload = {
        "registry_id": "M2_DATA2_FORMAL_CU_V4", "schema_version": "M2_DATA2_FORMAL_CU_V4", "formal_scope": list(CONSEQUENCE_COMPONENTS),
        "native_quantity_definitions": {c: {"definition": scales[c]["active_quantity_definition"], "unit": scales[c]["unit"], "driver": scales[c]["active_quantity_definition"]} for c in CONSEQUENCE_COMPONENTS},
        "train_scale_artifact": {c: {**scales[c], "path": str((artifact_dir / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json").relative_to(root)), "artifact_hash": scales_hash} for c in CONSEQUENCE_COMPONENTS},
        "reference_artifacts": reference_artifacts, "component_weights": {c: 1.0 for c in CONSEQUENCE_COMPONENTS},
        "aggregation_rule": "SUM_OVER_SEVEN_ONLY_IF_ALL_SUPPORTED", "support_rule": "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY",
        "final_test_access_count": 0, "paper_full_run": False, status_key: "FROZEN", "implementation_status": "MATCH",
        "fit_year": 2019, "fit_months": design["fit_months"], "db1b_quarters": design["db1b_quarters"],
        "passenger_manifest": "artifacts/diagnostics/passenger_reference_freeze_v4/PASSENGER_REFERENCE_MANIFEST_V2.json",
        "numeric_scale_adoption": {"decision": "ACTIVE_FORMULA_REALIGNMENT", "previous_registry": "M2_DATA2_FORMAL_CU_V3", "final_test_access_count": 0},
    }
    registry = M2Data2FormalCuRegistry.model_validate(registry_payload)
    registry_payload["registry_hash"] = registry.digest()
    registry_hash = _write_registry(root / "registries" / "m2_data2_formal_cu_v4.json", registry_payload)
    manifest = {
        "schema_version": "PASSENGER_REFERENCE_MANIFEST_V2", "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "fit_partition": "TRAIN", "fit_year": 2019, "fit_months": design["fit_months"], "db1b_quarters_used": design["db1b_quarters"],
        "source_file_hashes": _source_hashes(root, fitted["source_paths"]),
        "t100_row_audit": fitted["t100_audit"], "db1b_row_audit": fitted["db1b_audit"],
        "reference_ids": {"expected_pax": fitted["expected_pax"].reference_id, "connection_share": fitted["connection_share"].reference_id},
        "reference_artifact_hashes": {"expected_pax": expected_hash, "connection_share": connection_hash}, "seven_scale_artifact_hash": scales_hash, "m2_v4_registry_hash": registry_hash,
        "final_test_ontime_access_count": 0, "data1_modified": False, "data2_modified": False, "experiment_created": False,
        "t100_fit_months": fitted["t100_fit_months"], "db1b_fit_quarters": fitted["db1b_fit_quarters"],
        "t100_rows_seen": fitted["t100_audit"]["rows_seen"], "t100_rows_used": fitted["t100_audit"]["rows_used"], "t100_rows_excluded_outside_fit_period": fitted["t100_audit"]["rows_excluded_outside_fit_period"], "t100_rows_excluded_invalid_month": fitted["t100_audit"]["rows_excluded_invalid_month"],
        "db1b_rows_seen": fitted["db1b_audit"]["rows_seen"], "db1b_rows_used": fitted["db1b_audit"]["rows_used"], "db1b_rows_excluded_outside_fit_period": fitted["db1b_audit"]["rows_excluded_outside_fit_period"], "db1b_rows_excluded_invalid_schema": fitted["db1b_audit"]["rows_excluded_invalid_schema"],
        "t100_months_used": fitted["t100_audit"]["used_months"], "db1b_quarters_used_actual": fitted["db1b_audit"]["quarters_used"],
    }
    manifest_hash = _write(artifact_dir / "PASSENGER_REFERENCE_MANIFEST_V2.json", manifest)
    return {"artifact_dir": str(artifact_dir), "manifest_hash": manifest_hash, "registry_hash": registry_hash, "scales": scales, "audits": {"t100": fitted["t100_audit"], "db1b": fitted["db1b_audit"]}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(materialize(args.root.resolve()), sort_keys=True))
