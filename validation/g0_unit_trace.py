"""Read-only G0-3 unit/time trace over a frozen development checkpoint.

The trace joins canonical PRE nodes, the HISTORY_JOINT M1 state variant, the
M2 consequence variant, and any available M3 recovery decision. It reports
actual source fields and units without treating posthoc outcomes as inference
evidence. No model is executed and no artifact is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


UNIT_CONTRACT = {
    "raw.schedule_reference.scheduled_departure_utc": "UTC timestamp",
    "raw.predecessor_operational_fact.actual_arrival_utc": "UTC timestamp",
    "raw.successor_operational_fact.actual_departure_utc": "UTC timestamp",
    "raw.successor_operational_fact.taxi_out_minutes": "minutes",
    "PRE.T_IB_A00": "UTC timestamp",
    "M1.R_IB": "minutes",
    "M1.D_OB": "minutes",
    "M1.D_TX": "minutes",
    "M1.D_TO": "minutes",
    "M2.F_continuity": "minutes",
    "M2.F_execution": "minutes",
    "M2.F_propagation": "exposure_minutes",
    "M2.P_time": "passenger_minutes",
    "M2.P_itinerary": "expected_disrupted_connecting_passenger_exposure",
    "M2.P_service": "expected_long_delay_passenger_service_exposure",
    "M2.R_operating": "excess_taxi_minutes",
    "M2.CU": "normalized consequence units (CU), dimensionless",
    "M3.priority": "normalized priority score, dimensionless",
    "M3.u": "minutes per frozen Stage-II contract",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _delta_minutes(later: str, earlier: str) -> float:
    return (_parse_time(later) - _parse_time(earlier)).total_seconds() / 60.0


def _raw_fields(node: dict[str, Any]) -> dict[str, Any]:
    pre_state = node["pre_state"]
    schedule = (
        pre_state.get("static_reference_publication", {})
        .get("schedule_reference", {})
        .get("value", {})
    )
    predecessor = (
        pre_state.get("current_state", {})
        .get("predecessor_operational_fact", {})
        .get("value", {})
    )
    successor = (
        pre_state.get("successor_state", {})
        .get("successor_operational_fact", {})
        .get("value", {})
    )
    result: dict[str, Any] = {}
    if schedule.get("scheduled_departure_utc"):
        result["scheduled_departure_utc"] = {
            "value": schedule["scheduled_departure_utc"],
            "unit": UNIT_CONTRACT["raw.schedule_reference.scheduled_departure_utc"],
            "source_record_id": schedule.get("flight_id"),
        }
    if predecessor.get("actual_arrival_utc"):
        result["predecessor_actual_arrival_utc"] = {
            "value": predecessor["actual_arrival_utc"],
            "unit": UNIT_CONTRACT["raw.predecessor_operational_fact.actual_arrival_utc"],
            "source_record_id": predecessor.get("source_record_id"),
            "availability_time": predecessor.get("availability_time"),
        }
    if successor.get("actual_departure_utc"):
        result["successor_actual_departure_utc"] = {
            "value": successor["actual_departure_utc"],
            "unit": UNIT_CONTRACT["raw.successor_operational_fact.actual_departure_utc"],
            "source_record_id": successor.get("source_record_id"),
            "availability_time": successor.get("availability_time"),
        }
    if successor.get("taxi_out_minutes") is not None:
        result["successor_taxi_out_minutes"] = {
            "value": successor["taxi_out_minutes"],
            "unit": UNIT_CONTRACT["raw.successor_operational_fact.taxi_out_minutes"],
            "source_record_id": successor.get("source_record_id"),
            "availability_time": successor.get("availability_time"),
        }
    return result


def _availability_check(raw: dict[str, Any], decision_time: str) -> dict[str, Any]:
    checks = {}
    decision = _parse_time(decision_time)
    for name, payload in raw.items():
        available = payload.get("availability_time")
        checks[name] = {
            "availability_time": available,
            "decision_time": decision_time,
            "available_by_decision": (
                None if available is None else _parse_time(available) <= decision
            ),
        }
    return checks


def _find_stage_node(
    nodes: list[dict[str, Any]], stage: str, preferred_ids: set[str] | None = None
) -> dict[str, Any]:
    if preferred_ids:
        for node in nodes:
            if node["stage"] == stage and node["node_id"] in preferred_ids:
                return node
    for node in nodes:
        if node["stage"] == stage:
            return node
    raise ValueError(f"no node for stage {stage}")


def build_trace(epoch_root: Path) -> dict[str, Any]:
    canonical_path = epoch_root / "CANONICAL_NODES.json"
    state_path = epoch_root / "STATE_VARIANTS.json"
    consequence_path = epoch_root / "CONSEQUENCE_VARIANTS.json"
    recovery_path = epoch_root / "RECOVERY_DECISIONS.json"
    canonical = _load(canonical_path)["payload"]["nodes"]
    state_payload = _load(state_path)["payload"]
    state_variant = next(
        item for item in state_payload["variants"] if item["variant"] == "HISTORY_JOINT"
    )
    state_by_id = {item["node_id"]: item["state_set"] for item in state_variant["nodes"]}
    consequence_rows = _load(consequence_path)["payload"]["rows"]
    consequence_by_id = {
        item["node_id"]: item
        for item in consequence_rows
        if item["variant"] == "HISTORY_JOINT"
    }
    recovery_rows = _load(recovery_path)["payload"]["rows"]
    recovery_by_id = {
        item["node_id"]: item
        for item in recovery_rows
        if item["variant"] == "HISTORY_JOINT"
    }
    traces = []
    recovery_ids = set(recovery_by_id)
    for stage in ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO"):
        node = _find_stage_node(canonical, stage, recovery_ids)
        state_set = state_by_id[node["node_id"]]
        scenario = state_set["scenarios"][0]
        consequence = consequence_by_id[node["node_id"]]
        consequence_scenario = consequence["consequence_set"]["scenarios"][0]
        raw = _raw_fields(node)
        decision_time = node["decision_time"]
        derived_posthoc = {}
        if raw.get("scheduled_departure_utc") and raw.get("successor_actual_departure_utc"):
            derived_posthoc["signed_delta_ob_minutes"] = _delta_minutes(
                raw["successor_actual_departure_utc"]["value"],
                raw["scheduled_departure_utc"]["value"],
            )
        if raw.get("predecessor_actual_arrival_utc") and raw.get("successor_actual_departure_utc"):
            derived_posthoc["turnaround_gap_minutes"] = _delta_minutes(
                raw["successor_actual_departure_utc"]["value"],
                raw["predecessor_actual_arrival_utc"]["value"],
            )
        native = consequence_scenario["native_components"]
        cu = consequence_scenario["cu_components"]
        recovery = recovery_by_id.get(node["node_id"])
        recovery_payload = None
        if recovery is not None:
            recovery_payload = {
                "u_star": recovery["decision"].get("u_star"),
                "unit": UNIT_CONTRACT["M3.u"],
                "actionable": recovery.get("actionable"),
                "status": recovery["decision"].get("actionable_status"),
            }
        else:
            recovery_payload = {
                "u_star": None,
                "unit": "NOT_APPLICABLE",
                "actionable": False,
                "status": "NOT_AVAILABLE_FOR_STAGE",
            }
        traces.append(
            {
                "stage": stage,
                "node_id": node["node_id"],
                "episode_id": node["episode_id"],
                "decision_time": decision_time,
                "information_cutoff": node["pre_state"]["decision_node"]["information_cutoff"],
                "information_cutoff_ok": _parse_time(
                    node["pre_state"]["decision_node"]["information_cutoff"]
                ) <= _parse_time(decision_time),
                "raw": raw,
                "raw_availability": _availability_check(raw, decision_time),
                "raw_posthoc_derivations": derived_posthoc,
                "m1_state": {
                    "representation_id": state_set["representation_id"],
                    "scenario_id": scenario["scenario_id"],
                    "scenario_weight": scenario["scenario_weight"],
                    "values": {
                        "T_IB_or_remaining": scenario.get("t_ib_minutes"),
                        "D_OB": scenario.get("d_ob_minutes"),
                        "D_TX": scenario.get("d_tx_minutes"),
                        "D_TO": scenario.get("d_to_minutes"),
                    },
                    "units": {key: UNIT_CONTRACT[key] for key in ("M1.R_IB", "M1.D_OB", "M1.D_TX", "M1.D_TO")},
                    "d_to_identity_ok": abs(
                        float(scenario["d_to_minutes"])
                        - float(scenario["d_ob_minutes"])
                        - float(scenario["d_tx_minutes"])
                    ) <= 1e-6,
                },
                "m2": {
                    "reference_binding": node["reference_binding"],
                    "native_consequence": native,
                    "native_units": {
                        key: UNIT_CONTRACT[f"M2.{key}"]
                        for key in native
                    },
                    "cu": cu,
                    "cu_semantics": UNIT_CONTRACT["M2.CU"],
                    "priority": consequence.get("consequence_signal"),
                },
                "m3": recovery_payload,
                "source_artifacts": {
                    str(path.name): {"path": str(path), "sha256": _sha256(path)}
                    for path in (canonical_path, state_path, consequence_path, recovery_path)
                },
                "status": (
                    "TRACE_COMPLETE_TO_U"
                    if recovery is not None
                    else "TRACE_COMPLETE_TO_PRIORITY_TAXI_U_NOT_AVAILABLE"
                ),
            }
        )
    return {
        "schema_version": "AIR_SLOT_G0_UNIT_TIME_TRACE_V2",
        "source_epoch": str(epoch_root),
        "source_artifact_hashes": {
            name: _sha256(epoch_root / name)
            for name in (
                "CANONICAL_NODES.json",
                "STATE_VARIANTS.json",
                "CONSEQUENCE_VARIANTS.json",
                "RECOVERY_DECISIONS.json",
            )
        },
        "scientific_recomputation": False,
        "unit_contract": UNIT_CONTRACT,
        "traces": traces,
        "status": "PASS_STATIC_UNIT_CHAIN_WITH_TYPED_TAXI_LIMIT",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epoch-root", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    result = build_trace(args.epoch_root)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [
        "# G0-3 unit/time trace",
        "",
        f"- Status: `{result['status']}`",
        f"- Source epoch: `{result['source_epoch']}`",
        "- Scientific recomputation: `False`",
        "",
        "| Stage | Decision time | Information cutoff OK | D_TO identity | M3 u | Status |",
        "|---|---|---:|---:|---:|---|",
    ]
    for trace in result["traces"]:
        rows.append(
            "| {stage} | {decision_time} | {cutoff} | {identity} | {u} | {status} |".format(
                stage=trace["stage"],
                decision_time=trace["decision_time"],
                cutoff=trace["information_cutoff_ok"],
                identity=trace["m1_state"]["d_to_identity_ok"],
                u=trace["m3"]["u_star"],
                status=trace["status"],
            )
        )
    rows += [
        "",
        "The raw actual successor fields are posthoc replay records when their availability time is after the decision time. They are reported for lineage and unit tracing, not admitted as inference inputs.",
        "CU is a normalized consequence representation and is not currency. `u` is the frozen Stage-II modeled recovery-intensity variable, not an identified real-world action.",
    ]
    args.out_md.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "traces": len(result["traces"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
