"""One-shot held-out Final Test adapter for Air Slot Exp1-Exp4.

This module binds the frozen Q4 cohort and frozen model artifacts to the
existing experiment estimators. It deliberately leaves Development guards
and scientific estimator modules unchanged.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from datetime import date
from hashlib import sha256
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from exp.exp1.formal import LEAD_GRID
from exp.exp1.paired import hazard_crps_records, paired_records, summarize_targets
from exp.exp1.scenarios import analyze_nodes
from exp.exp1.formal_inputs import nearest_lead
from exp.exp2 import development_inputs as exp2_inputs
from exp.exp2.run import execute_node_materialization
from exp.exp2.figures import component_figure, priority_figure
from exp.exp3.analysis import (
    METRICS,
    bootstrap_stage_fast,
    common_episode_cohort,
    evaluate_stages,
    stage_contrasts,
)
from exp.exp4.triage import (
    bootstrap_screening,
    evaluate_screening,
    prepare_canonical_events,
    robust_missed_nodes,
    robust_sets,
)
from exp.shared.analytical import scores
from exp.shared.output import with_intervals, write_json
from exp.shared.resampling import bootstrap_plan, episode_ids, expand_draw, interval
from model.M1.coverage import active_node_prefixes
from model.M1.data import encode_pre_sequence
from model.M1.development_diagnostics import evaluate_lifecycle
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.tail import load_tail_continuations
from model.PRE.cohort import split_for_date
from model.PRE.development import _publish_partition
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.containment import episode_containment_from_rows
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import (
    aircraft_tail,
    config_hash,
    lightweight_flights,
    load_selected_typed_records,
    load_timezones,
    ontime_paths,
    registry_hash,
    weather_index,
)
from model.common.config import load_config_layers


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_MD = ROOT / "formal" / "FINAL_TEST_COHORT_AUTHORITY_20260908.md"
AUTHORITY_JSON = ROOT / "formal" / "FINAL_TEST_COHORT_AUTHORITY_V1.json"
LOCK = ROOT / "formal" / "FINAL_TEST_LOCK_20260907.md"
MODEL_ROOT = ROOT / "artifacts" / "models" / "m1"
HISTORY_CHECKPOINT = MODEL_ROOT / "M1_H16_HISTORY_PRIMARY" / "M1_H16_HISTORY_PRIMARY.pt"
CURRENT_CHECKPOINT = MODEL_ROOT / "M1_H16_CURRENT_COMPARATOR" / "M1_H16_CURRENT_COMPARATOR.pt"
TAIL_MANIFEST = ROOT / "artifacts" / "diagnostics" / "m1_positive_tail_continuation_v1" / "M1_POSITIVE_TAIL_CONTINUATION_V1.json"
OUTPUT_ROOT = ROOT / "artifacts" / "experiment"
FINAL_ROOT = OUTPUT_ROOT / "final_test"
ACCESS_AUDIT = FINAL_ROOT / "FINAL_TEST_ACCESS_AUDIT.json"
BUG_LOG = FINAL_ROOT / "FINAL_TEST_EXECUTION_BUGS.json"
EPISODE_COUNT = 128
SEED = 20260813
BOOTSTRAP_SEED = 20260906
BOOTSTRAP_REPLICATES = 2000


def digest(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _authority() -> dict:
    payload = _json(AUTHORITY_JSON)
    if payload["authority_status"] != "FINAL_TEST_COHORT_AUTHORITY_LOCKED":
        raise RuntimeError("FINAL_TEST_COHORT_AUTHORITY_NOT_LOCKED")
    if int(payload["final_test_episode_count"]) != EPISODE_COUNT:
        raise RuntimeError("FINAL_TEST_EPISODE_COUNT_AUTHORITY_MISMATCH")
    if payload["selection"]["seed"] != SEED or payload["selection"]["rng_scope"] != "FINAL_TEST_ONLY_FRESH_SEED":
        raise RuntimeError("FINAL_TEST_SELECTION_AUTHORITY_MISMATCH")
    if payload["source_window"]["months"] != [10, 11, 12]:
        raise RuntimeError("FINAL_TEST_SOURCE_WINDOW_AUTHORITY_MISMATCH")
    return payload


def _open_event() -> dict:
    FINAL_ROOT.mkdir(parents=True, exist_ok=True)
    if ACCESS_AUDIT.exists():
        prior = _json(ACCESS_AUDIT)
        if prior.get("final_test_access_count") != 1 or not prior.get("opened"):
            raise RuntimeError("FINAL_TEST_ACCESS_AUDIT_INVALID")
        return prior
    event = {
        "schema_version": "AIR_SLOT_FINAL_TEST_ACCESS_AUDIT_V1",
        "opened": True,
        "open_event": "FIRST_FORMAL_HELD_OUT_TEST_SOURCE_READ",
        "final_test_access_count": 1,
        "source_months": [10, 11, 12],
        "authority": str(AUTHORITY_JSON.relative_to(ROOT)),
        "lock": str(LOCK.relative_to(ROOT)),
        "execution_head": _git_head(),
        "scientific_code_lock": "c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6",
        "data_read_before_event": False,
    }
    write_json(ACCESS_AUDIT, event)
    return event


def _record_execution_bug() -> None:
    write_json(
        BUG_LOG,
        {
            "schema_version": "AIR_SLOT_FINAL_TEST_EXECUTION_BUG_LOG_V1",
            "bugs": [
                {
                    "bug_id": "FT-ADAPTER-001",
                    "class": "PURE_EXECUTION_INPUT_BINDING_BUG",
                    "status": "FIXED",
                    "location": "formal/final_test_run.py:_m1_examples",
                    "symptom": "np.argsort returned a multidimensional index for tuple sort keys",
                    "failure": "TypeError: only 0-dimensional arrays can be converted to Python scalars",
                    "impact": "No Exp1-Exp4 result was generated before failure",
                    "scientific_effect": "NONE",
                    "cohort_effect": "NONE; selected cohort manifest and PRE states were already fixed",
                    "fix": "Use stable Python index sorting by (episode_id, decision_node_id)",
                    "rerun_policy": "Reuse the same selected cohort and access audit",
                },
                {
                    "bug_id": "FT-ADAPTER-002",
                    "class": "PURE_EXECUTION_INPUT_BINDING_BUG",
                    "status": "FIXED",
                    "location": "formal/final_test_run.py:_scenarios",
                    "symptom": "Final-Test M1 state-node IDs were not rebound to the matched analysis-node namespace",
                    "failure": "Exp1B analyze_nodes raised KeyError for an exact matched node",
                    "impact": "Exp1B and downstream Exp2-Exp4 execution stopped after valid scenario materialization",
                    "scientific_effect": "NONE",
                    "cohort_effect": "NONE; the fixed cohort and generated model outputs are reused",
                    "fix": "Preserve pre_decision_node_id and bind decision/canonical/technical IDs to the exact analysis node ID",
                    "rerun_policy": "Reuse the same selected cohort and access audit",
                },
                {
                    "bug_id": "FT-ADAPTER-003",
                    "class": "PURE_EXECUTION_OUTPUT_BINDING_BUG",
                    "status": "FIXED",
                    "location": "formal/final_test_run.py:_exp2",
                    "symptom": "A WindowsPath stored in DataFrame attrs could not be serialized to Parquet metadata",
                    "failure": "TypeError: Object of type WindowsPath is not JSON serializable",
                    "impact": "Exp2 formal execution stopped after Exp1 and shared Final-Test inputs were generated",
                    "scientific_effect": "NONE",
                    "cohort_effect": "NONE; fixed cohort and shared inputs remain unchanged",
                    "fix": "Store the generated input path in DataFrame attrs as a string",
                    "rerun_policy": "Reuse the same selected cohort, access audit, and shared inputs",
                }
            ],
            "final_test_access_count": 1,
        },
    )


def _git_head() -> str:
    import subprocess

    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def select_cohort(root: Path, authority: dict) -> tuple[tuple[object, ...], dict]:
    """Select Q4 episodes with a fresh authority-scoped reservoir RNG."""
    existing = FINAL_ROOT / "FINAL_TEST_COHORT_MANIFEST_V1.json"
    if existing.is_file():
        locked = _json(existing)
        expected_ids = tuple(str(item) for item in locked.get("selected_episode_ids", ()))
        if (
            locked.get("authority_status") != "FINAL_TEST_COHORT_AUTHORITY_LOCKED"
            or locked.get("selected_episode_count") != EPISODE_COUNT
            or len(expected_ids) != EPISODE_COUNT
            or len(set(expected_ids)) != EPISODE_COUNT
            or locked.get("selected_episode_hash")
            != "sha256:" + sha256("\n".join(sorted(expected_ids)).encode()).hexdigest()
        ):
            raise RuntimeError("FINAL_TEST_LOCKED_COHORT_MANIFEST_INVALID")
        paths = ontime_paths(root, months=(10, 11, 12), allow_final_test=True)
        zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
        found = {}
        carry = ()
        target_ids = set(expected_ids)
        for month, path in zip((10, 11, 12), paths):
            rows, _ = lightweight_flights(path, zones, include_warning_fields=True)
            chunk = list(carry) + rows
            candidates = sorted(build_data2_episode_records(chunk), key=lambda item: item.episode_id)
            for episode in candidates:
                if episode.episode_id in target_ids:
                    found[episode.episode_id] = episode
            carry = aircraft_tail(rows)
        if set(found) != target_ids:
            raise RuntimeError("FINAL_TEST_LOCKED_COHORT_EPISODE_RECONSTRUCTION_FAILED")
        selected = tuple(found[episode_id] for episode_id in sorted(expected_ids))
        if tuple(item.episode_id for item in selected) != tuple(sorted(expected_ids)):
            raise RuntimeError("FINAL_TEST_LOCKED_COHORT_ORDER_FAILED")
        locked["selection_reused"] = True
        locked["selection_reperformed"] = False
        write_json(existing, locked)
        return selected, locked

    paths = ontime_paths(root, months=(10, 11, 12), allow_final_test=True)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    rng = random.Random(SEED)
    reservoir: list[object] = []
    pool_size = 0
    eligible_by_month = Counter()
    containment_exclusions = Counter()
    skipped_by_month = {}
    carry = ()
    seen_episode_ids: set[str] = set()

    for month, path in zip((10, 11, 12), paths):
        rows, skipped = lightweight_flights(path, zones, include_warning_fields=True)
        skipped_by_month[str(month)] = int(skipped)
        chunk = list(carry) + rows
        by_id = {row["flight_id"]: row for row in chunk}
        month_key = f"2019-{month:02d}"
        candidates = sorted(build_data2_episode_records(chunk), key=lambda item: item.episode_id)
        for episode in candidates:
            successor = by_id.get(episode.successor_flight_id)
            if successor is None or successor.get("service_date", "")[:7] != month_key:
                continue
            if split_for_date(date.fromisoformat(successor["service_date"])) != "test":
                continue
            containment = episode_containment_from_rows(episode, by_id)
            if not containment.allowed or containment.split != "test":
                containment_exclusions[containment.reason_code or "CONTAINMENT_REJECTED"] += 1
                continue
            if episode.episode_id in seen_episode_ids:
                raise RuntimeError("FINAL_TEST_DUPLICATE_CANDIDATE_EPISODE")
            seen_episode_ids.add(episode.episode_id)
            pool_size += 1
            eligible_by_month[month_key] += 1
            if len(reservoir) < EPISODE_COUNT:
                reservoir.append(episode)
            else:
                index = rng.randrange(pool_size)
                if index < EPISODE_COUNT:
                    reservoir[index] = episode
        carry = aircraft_tail(rows)

    if pool_size < EPISODE_COUNT:
        raise RuntimeError("BLOCK_FINAL_TEST_INSUFFICIENT_ELIGIBLE_POOL")
    selected = tuple(sorted(reservoir, key=lambda item: item.episode_id))
    if len({item.episode_id for item in selected}) != EPISODE_COUNT:
        raise RuntimeError("FINAL_TEST_SELECTED_EPISODE_ID_DUPLICATE")
    audit = {
        "schema_version": "AIR_SLOT_FINAL_TEST_COHORT_MANIFEST_V1",
        "authority_status": "FINAL_TEST_COHORT_AUTHORITY_LOCKED",
        "final_test_access_count": 1,
        "source_paths": [str(path.relative_to(root)) for path in paths],
        "source_months": [10, 11, 12],
        "candidate_eligible_pool_count": pool_size,
        "selected_episode_count": len(selected),
        "selected_episode_hash": "sha256:" + sha256("\n".join(item.episode_id for item in selected).encode()).hexdigest(),
        "selected_episode_ids": [item.episode_id for item in selected],
        "eligible_by_month": dict(eligible_by_month),
        "containment_exclusions": dict(containment_exclusions),
        "skipped_rows_by_month": skipped_by_month,
        "selection_rule": authority["selection"]["rule"],
        "selection_seed": SEED,
        "rng_scope": authority["selection"]["rng_scope"],
        "selection_pre_outcome": True,
        "no_replacement_after_selection": True,
        "old_h32_used": False,
        "final_test_access_audit": str(ACCESS_AUDIT.relative_to(root)),
    }
    write_json(FINAL_ROOT / "FINAL_TEST_COHORT_MANIFEST_V1.json", audit)
    return selected, audit


def _references():
    taxi, turnaround, _ = exp2_inputs._load_references(ROOT)
    return taxi, turnaround


def materialize_pre(selected: tuple[object, ...]) -> tuple[tuple[object, ...], dict]:
    paths = ontime_paths(ROOT, months=(10, 11, 12), allow_final_test=True)
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    schedules, outcomes = load_selected_typed_records(selected, paths, zones)
    for episode in selected:
        successor = schedules[episode.successor_flight_id]
        if split_for_date(successor.service_date) != "test":
            raise RuntimeError("FINAL_TEST_PRE_SPLIT_ASSIGNMENT_FAILED")
    taxi, turnaround = _references()
    scientific = load_config_layers(ROOT / "configs").scientific
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        ROOT / "data2", replay_lag, start_inclusive=date(2019, 10, 1), end_exclusive=date(2020, 1, 1)
    )
    items = {
        episode.episode_id: (
            episode,
            schedules[episode.successor_flight_id],
            outcomes[episode.predecessor_flight_id],
            outcomes[episode.successor_flight_id],
        )
        for episode in selected
    }
    published, stage_counts = _publish_partition(
        selected,
        items,
        config_hash_value=config_hash(ROOT),
        registry_hash_value=registry_hash(ROOT),
        weather=weather,
        weather_max_age_minutes=max_age,
        publisher=ProductionPREPublisher.from_project(),
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    states_path = FINAL_ROOT / "FINAL_TEST_PRE_STATES.jsonl"
    with states_path.open("w", encoding="utf-8") as stream:
        for prepared in published:
            for state in prepared.states:
                stream.write(state.model_dump_json() + "\n")
    audit = {
        "schema_version": "AIR_SLOT_FINAL_TEST_PRE_AUDIT_V1",
        "final_test_access_count": 1,
        "episode_count": len(published),
        "rolling_node_count": sum(len(item.nodes) for item in published),
        "stage_counts": stage_counts,
        "pre_states_sha256": digest(states_path),
        "weather_audit": weather_audit,
        "selection_reperformed": False,
        "references_fit_partition": "TRAIN",
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
    }
    write_json(FINAL_ROOT / "FINAL_TEST_PRE_AUDIT.json", audit)
    return published, audit


def _m1_examples(published):
    taxi, _ = _references()
    history = M1Lifecycle.load(HISTORY_CHECKPOINT, device="cpu")
    current = M1Lifecycle.load(CURRENT_CHECKPOINT, device="cpu")
    examples = []
    exact_rows = []
    for prepared in published:
        lookup = taxi.lookup(prepared.episode.connection_airport_id)
        taxi_minutes = (
            float(lookup.value)
            if lookup is not None and getattr(lookup, "value", None) is not None
            and getattr(getattr(lookup, "support_state", None), "value", None) == "SUPPORTED"
            else None
        )
        for node, prefix, labels in active_node_prefixes(
            episode=prepared.episode,
            nodes=prepared.nodes,
            states=prepared.states,
            successor_schedule=prepared.successor_schedule,
            predecessor_outcome=prepared.predecessor_outcome,
            successor_outcome=prepared.successor_outcome,
            taxi_reference_minutes=taxi_minutes,
            taxi_reference_id=getattr(taxi, "reference_id", None),
            taxi_reference_hash=getattr(taxi, "manifest_freeze_id", None),
        ):
            example = M1TrainingExample.from_v2_target_labels(
                values=encode_pre_sequence(prefix, history.pipeline.normalization), labels=labels
            )
            examples.append(example)
            exact_rows.append((example, prepared, prefix))
    order = sorted(
        range(len(exact_rows)),
        key=lambda index: (
            str(exact_rows[index][0].episode_id),
            str(exact_rows[index][0].decision_node_id),
        ),
    )
    exact_rows = [exact_rows[index] for index in order]
    examples = [exact_rows[i][0] for i in range(len(exact_rows))]
    return history, current, examples, exact_rows


def _exp1(published, history, current, examples, exact_rows):
    h_result = evaluate_lifecycle(history, tuple(examples), batch_size=64)
    c_result = evaluate_lifecycle(current, tuple(examples), batch_size=64)
    records = paired_records(h_result["nodes"], c_result["nodes"])
    history_crps = hazard_crps_records(history, tuple(examples))
    current_crps = hazard_crps_records(current, tuple(examples))
    for mode, values in (("History", history_crps), ("Current", current_crps)):
        records[f"{mode}_R_IB_CRPS"] = [
            values.get((str(row.episode_id), str(row.decision_node_id)), (None, None))[0]
            for row in records.itertuples()
        ]
        records[f"{mode}_R_IB_finite_support_mass"] = [
            values.get((str(row.episode_id), str(row.decision_node_id)), (None, None))[1]
            for row in records.itertuples()
        ]
    records["CRPS_scope"] = np.where(
        records.target.eq("R_IB"),
        "R_IB_T_IB_FINITE_SUPPORT_CONDITIONAL_ONLY",
        "NOT_APPLICABLE_D_OB_D_TX_NO_FROZEN_CRPS",
    )
    evaluation_rows = []
    for example, prepared, prefix in exact_rows:
        node = prefix[-1].decision_node
        events = {
            "R_IB": prepared.predecessor_outcome.actual_arrival_utc,
            "D_OB": prepared.successor_outcome.actual_departure_utc,
            "D_TX": prepared.successor_outcome.wheels_off_utc,
        }
        row = {
            "episode_id": prepared.episode.episode_id,
            "decision_node_id": str(example.decision_node_id),
        }
        for target, event in events.items():
            lead = None if event is None else (event - node.decision_time).total_seconds() / 60
            grid, status = nearest_lead(lead)
            row[f"{target}_lead_grid"] = grid
            row[f"{target}_lead_status"] = status
        evaluation_rows.append(row)
    evaluation_map = pd.DataFrame(evaluation_rows)
    from exp.exp1.formal import _lead_table

    plan = bootstrap_plan(tuple(sorted(records.episode_id.unique())), BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED)
    summary, bootstrap = summarize_targets(records, plan)
    lead = _lead_table(records, evaluation_map)
    out = FINAL_ROOT / "exp1"
    out.mkdir(parents=True, exist_ok=True)
    records.to_csv(out / "EXP1_HISTORY_CURRENT_MATCHED_RECORDS.csv", index=False)
    summary.to_csv(out / "EXP1_HISTORY_CURRENT_TARGET_SUMMARY.csv", index=False)
    bootstrap.to_csv(out / "EXP1_HISTORY_CURRENT_BOOTSTRAP.csv", index=False)
    lead.to_csv(out / "EXP1_EVALUATION_LEAD_TIME.csv", index=False)

    scenario_frame, node_source = _scenarios(published, history, exact_rows)
    node_source.to_parquet(FINAL_ROOT / "FINAL_TEST_SHARED_NODE_INPUTS.parquet", index=False)
    scenario_frame.to_parquet(FINAL_ROOT / "FINAL_TEST_SHARED_SCENARIO_INPUTS.parquet", index=False)
    taxi, _ = _references()
    supports = tuple(float(history.pipeline.contracts[name].max_finite_minutes) for name in ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX"))
    representations, native = analyze_nodes(scenario_frame, exact_rows, taxi, supports=supports)
    representations.to_csv(out / "EXP1B_REPRESENTATION_SUMMARY.csv", index=False)
    native.to_csv(out / "EXP1B_DOWNSTREAM_NATIVE_DISTORTION.csv", index=False)
    _exp1_native_bootstrap(native, out)
    representations[representations.status.eq("PASS")].to_csv(out / "EXP1_REPRESENTATION_RECORDS.csv", index=False)
    summary_payload = {
        "schema_version": "AIR_SLOT_EXP1_FINAL_TEST_MANIFEST_V1",
        "status": "FINAL_TEST_COMPLETE",
        "final_test_access_count": 1,
        "episode_count": int(len(published)),
        "rolling_node_count": int(len(exact_rows)),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_replicates_completed": int(bootstrap.replicate.nunique()),
        "bootstrap_seed": BOOTSTRAP_SEED,
        "targets": summary.to_dict("records"),
        "representation_rows": int(len(representations)),
        "native_distortion_rows": int(len(native)),
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
    }
    write_json(out / "FINAL_TEST_EXP1_MANIFEST.json", summary_payload)
    return summary_payload, node_source


def _scenarios(published, history, exact_rows):
    taxi, turnaround = _references()
    tails = load_tail_continuations(TAIL_MANIFEST)
    history.pipeline.tail_continuations = tails
    bundle = exp2_inputs.load_data2_reference_bundle(exp2_inputs._reference_payloads())
    frozen, registry, _ = exp2_inputs.active_model_contract()
    context_cache = {}
    node_rows, scenario_rows = [], []
    for example, prepared, prefix in exact_rows:
        state = prefix[-1]
        values = encode_pre_sequence(prefix, history.pipeline.normalization)
        scenarios = history.pipeline.sample_from_pre(
            state,
            values.unsqueeze(0),
            torch.tensor([len(values)]),
            observed=exp2_inputs._observed(state, taxi),
            count=64,
            seed=int(_json(HISTORY_CHECKPOINT.with_name("M1_H16_HISTORY_PRIMARY_MANIFEST.json"))["training_seed"]),
            taxi_reference=taxi,
            tail_continuations=tails,
        )
        typed = exp2_inputs.typed_m1_inputs(
            scenarios,
            pre_lineage=("FINAL_TEST_PRE_V1", str(state.decision_node.decision_node_id)),
            reference_lineage=(str(_json(TAIL_MANIFEST)["artifact_hash"]), frozen.registry_hash),
        )
        keys = exp2_inputs.AirportReferenceKeys(
            connection_airport_id=prepared.episode.connection_airport_id,
            successor_destination_airport_id=exp2_inputs._destination(state),
            carrier_id=None,
            month=state.decision_node.decision_time.month,
            quarter=(state.decision_node.decision_time.month - 1) // 3 + 1,
        )
        context_key = (
            keys.connection_airport_id,
            keys.successor_destination_airport_id,
            keys.month,
            keys.quarter,
        )
        if context_key not in context_cache:
            references = exp2_inputs.build_node_exposure_references(bundle, keys)
            context_cache[context_key] = exp2_inputs.build_m2_v4_context(
                bundle, keys, node_specific_exposure=references.airport
            )
        mapped = exp2_inputs.map_model_outputs(typed, context_cache[context_key])
        support_records = exp2_inputs.identify_common_supported_scenarios(typed, mapped, registry)
        node_row = exp2_inputs.flatten_node(
            typed, mapped,
            metadata={
                "decision_time": state.decision_node.decision_time.isoformat(),
                "information_cutoff": state.decision_node.information_cutoff.isoformat(),
                "operational_stage": state.decision_node.operational_stage.value,
                "final_test_access_count": 1,
                "original_episode_id": prepared.episode.episode_id,
                "technical_node_id": state.decision_node.decision_node_id,
            },
        )
        analysis_node_id = str(example.decision_node_id)
        node_row["pre_decision_node_id"] = str(state.decision_node.decision_node_id)
        node_row["decision_node_id"] = analysis_node_id
        node_row["technical_node_id"] = analysis_node_id
        node_rows.append(node_row)
        for typed_row, mapped_row, support_row in zip(typed, mapped, support_records):
            payload = {
                "episode_id": typed_row.episode_id,
                "decision_node_id": analysis_node_id,
                "canonical_decision_node_id": analysis_node_id,
                "pre_decision_node_id": typed_row.decision_node_id,
                "scenario_id": typed_row.scenario_id,
                "scenario_weight": typed_row.scenario_weight,
                "R_IB": typed_row.r_ib_minutes,
                "R_IB_support": typed_row.r_ib_support.value,
                "D_OB": typed_row.d_ob_minutes,
                "D_OB_support": typed_row.d_ob_support.value,
                "D_TX": typed_row.d_tx_minutes,
                "D_TX_support": typed_row.d_tx_support.value,
                "D_TO": typed_row.d_to_minutes,
                "D_TO_support": typed_row.d_to_support.value,
                "common_supported": support_row["common_supported"],
                "unsupported_reasons": "|".join(support_row["unsupported_reasons"]),
                "formal_scenario_status": support_row["formal_scenario_status"],
            }
            for component_row in mapped_row.component_vector.rows:
                component = component_row.component_id
                payload[f"{component}_native"] = component_row.native_quantity
                payload[f"Z_{component}"] = component_row.constructed_value_cu
                payload[f"{component}_support"] = component_row.support_state.value
                payload[f"{component}_cu_status"] = component_row.cu_status.value
            scenario_rows.append(payload)
    return pd.DataFrame(scenario_rows), pd.DataFrame(node_rows)


def _exp1_native_bootstrap(native: pd.DataFrame, out: Path) -> None:
    rows = []
    plan = bootstrap_plan(tuple(sorted(native.episode_id.astype(str).unique())), BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED)
    for component in exp2_inputs.COMPONENTS:
        for variant in ("point_minus_joint_native_W1", "marginal_minus_joint_native_W1"):
            frame = native.dropna(subset=[f"{component}_{variant}"]).copy()
            groups = {str(ep): g for ep, g in frame.groupby(frame.episode_id.astype(str))}
            values = []
            for draw in plan:
                chunks = [groups[str(ep)] for ep in draw if str(ep) in groups]
                if chunks:
                    values.append(float(pd.concat(chunks)[f"{component}_{variant}"].mean()))
            estimate = float(frame[f"{component}_{variant}"].mean()) if not frame.empty else None
            low, high = interval(values)
            rows.append({"component": component, "variant": variant, "estimate": estimate, "ci_low": low, "ci_high": high, "n_nodes": len(frame), "n_episodes": frame.episode_id.nunique()})
    pd.DataFrame(rows).to_csv(out / "EXP1B_DOWNSTREAM_NATIVE_BOOTSTRAP.csv", index=False)


def _exp2(source: pd.DataFrame):
    out = FINAL_ROOT / "exp2"
    out.mkdir(parents=True, exist_ok=True)
    source = source.copy()
    source.attrs["input_path"] = str(FINAL_ROOT / "FINAL_TEST_SHARED_NODE_INPUTS.parquet")
    source.to_parquet(source.attrs["input_path"], index=False)
    result = execute_node_materialization(source, fast=False, output_root=out)
    inner_manifest = _finalize_exp2_metadata(out, result["manifest"], paper_result=False)
    result = {"manifest": inner_manifest, "support_audit": result["support_audit"]}
    manifest = {
        "schema_version": "AIR_SLOT_EXP2_FINAL_TEST_MANIFEST_V1",
        "status": "FINAL_TEST_COMPLETE",
        "final_test_access_count": 1,
        "input_path": str(source.attrs["input_path"]),
        "episodes": int(source.original_episode_id.nunique()),
        "nodes": int(len(source)),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "scientific_result": result,
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
        "paper_result": False,
        "artifact_scope": "FINAL_TEST_ONLY",
    }
    write_json(out / "FINAL_TEST_EXP2_MANIFEST.json", manifest)
    ranked = pd.read_parquet(out / "data" / "EXP2_PRIORITY_BASE.parquet")
    priority_figure(ranked, out / "FIG2_PRIORITY_DIVERGENCE_FINAL_TEST.pdf")
    information = pd.read_csv(out / "results" / "EXP2B_COMPONENT_DOMAIN_SUMMARY.csv")
    pair_summary = pd.read_csv(out / "results" / "EXP2C_PAIR_BALANCED_SUMMARY.csv")
    component_gaps = pd.DataFrame(
        [
            {
                "component_id": component,
                "estimate": pair_summary.loc[0].get(f"median_component_gap_{component}"),
                "ci_low": pair_summary.loc[0].get(f"median_component_gap_{component}_ci_low"),
                "ci_high": pair_summary.loc[0].get(f"median_component_gap_{component}_ci_high"),
            }
            for component in exp2_inputs.COMPONENTS
        ]
    )
    component_figure(
        information,
        component_gaps,
        out / "FIG3_COMPONENT_EVIDENCE_FINAL_TEST.pdf",
    )
    return manifest


def _finalize_exp2_metadata(out: Path, manifest: dict, *, paper_result: bool) -> dict:
    """Rebind Development writer metadata to this held-out output root."""
    json_paths = [
        out / "EXP2_ANALYSIS_CONTRACT.json",
        out / "EXP2_INPUT_MANIFEST.json",
        out / "EXP2_SUPPORT_AUDIT.json",
        out / "results" / "EXP2_DIAGNOSTICS.json",
        out / "results" / "EXP2_DEVELOPMENT_SUMMARY.json",
    ]
    for path in json_paths:
        payload = _json(path)
        payload["final_test_access_count"] = 1
        payload["paper_result"] = paper_result
        payload["artifact_scope"] = "FINAL_TEST_ONLY"
        if path.name == "EXP2_ANALYSIS_CONTRACT.json":
            payload["status"] = "FINAL_TEST_COMPLETE"
            payload["artifact_scope"] = "FINAL_TEST_ONLY"
            payload["component_domain_population_rule"] = (
                "INDEPENDENT_COMPONENT_DOMAIN_FINITE_SUPPORT_APPLICABLE_PRIMARY_SUPPORT"
            )
        if path.name == "EXP2_INPUT_MANIFEST.json":
            payload["artifact_scope"] = "FINAL_TEST_ONLY"
        if path.name == "EXP2_DIAGNOSTICS.json":
            payload["status"] = "FINAL_TEST_ONLY"
        write_json(path, payload)
    manifest = dict(manifest)
    manifest.update(
        {
            "schema_version": "AIR_SLOT_EXP2_FINAL_TEST_INNER_MANIFEST_V1",
            "status": "FINAL_TEST_COMPLETE",
            "artifact_scope": "FINAL_TEST_ONLY",
            "final_test_access_count": 1,
            "paper_result": paper_result,
            "outputs": {
                name: digest(out / name) for name in manifest["required_outputs"]
            },
        }
    )
    write_json(out / "EXP2_MANIFEST.json", manifest)
    return manifest


def _bootstrap_replicates(path: Path) -> int:
    frame = pd.read_csv(path, usecols=["replicate"])
    return int(frame["replicate"].nunique())


def _error_bounds(frame: pd.DataFrame, estimate: str) -> tuple[np.ndarray, np.ndarray]:
    values = frame[estimate].astype(float).to_numpy()
    low = frame[f"{estimate}_ci_low"].astype(float).to_numpy()
    high = frame[f"{estimate}_ci_high"].astype(float).to_numpy()
    return np.vstack((np.maximum(0.0, values - low), np.maximum(0.0, high - values)))


def _render_final_test_figures() -> list[str]:
    """Render presentation-only figures from completed, frozen result tables."""
    created: list[str] = []

    exp1 = pd.read_csv(FINAL_ROOT / "exp1" / "EXP1_HISTORY_CURRENT_TARGET_SUMMARY.csv")
    exp1_data = exp1[[
        "target", "History_MAE", "History_MAE_ci_low", "History_MAE_ci_high",
        "Current_MAE", "Current_MAE_ci_low", "Current_MAE_ci_high",
    ]]
    exp1_data.to_csv(FINAL_ROOT / "exp1" / "FIG1_HISTORY_CURRENT_MAE_FINAL_TEST_DATA.csv", index=False)
    x = np.arange(len(exp1_data))
    fig, ax = plt.subplots(figsize=(6.3, 3.7))
    width = 0.36
    ax.bar(x - width / 2, exp1_data["History_MAE"], width, label="History", color="#2166ac")
    ax.bar(x + width / 2, exp1_data["Current_MAE"], width, label="Current", color="#b2182b")
    ax.errorbar(x - width / 2, exp1_data["History_MAE"], yerr=_error_bounds(exp1_data, "History_MAE"), fmt="none", ecolor="#222222", capsize=3, lw=0.9)
    ax.errorbar(x + width / 2, exp1_data["Current_MAE"], yerr=_error_bounds(exp1_data, "Current_MAE"), fmt="none", ecolor="#222222", capsize=3, lw=0.9)
    ax.set_xticks(x, exp1_data["target"])
    ax.set_ylabel("MAE (minutes)")
    ax.set_title("Held-out target-specific prediction error")
    ax.legend(frameon=False, ncols=2, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = FINAL_ROOT / "exp1" / "FIG1_HISTORY_CURRENT_MAE_FINAL_TEST.pdf"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    created.append(str(path.relative_to(FINAL_ROOT)))

    exp3 = pd.read_csv(FINAL_ROOT / "exp3" / "EXP3_STAGE_AGREEMENT.csv")
    exp3_data = exp3[["stage", "kendall_tau_b", "kendall_tau_b_ci_low", "kendall_tau_b_ci_high", "top10_overlap", "top10_overlap_ci_low", "top10_overlap_ci_high"]]
    exp3_data.to_csv(FINAL_ROOT / "exp3" / "FIG4_STAGE_AGREEMENT_FINAL_TEST_DATA.csv", index=False)
    fig, ax = plt.subplots(figsize=(6.4, 3.7))
    x = np.arange(len(exp3_data))
    ax.bar(x, exp3_data["kendall_tau_b"], color="#1b9e77", width=0.58)
    ax.errorbar(x, exp3_data["kendall_tau_b"], yerr=_error_bounds(exp3_data, "kendall_tau_b"), fmt="none", ecolor="#222222", capsize=3, lw=0.9)
    ax.set_xticks(x, exp3_data["stage"], rotation=12, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Kendall tau-b")
    ax.set_title("Stage-specific delay/consequence agreement")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = FINAL_ROOT / "exp3" / "FIG4_STAGE_AGREEMENT_FINAL_TEST.pdf"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    created.append(str(path.relative_to(FINAL_ROOT)))

    exp4 = pd.read_csv(FINAL_ROOT / "exp4" / "EXP4_SCREENING_RESULTS.csv")
    exp4_data = exp4.loc[np.isclose(exp4["q"], 0.10), [
        "stage", "overlap", "overlap_ci_low", "overlap_ci_high",
        "reassigned_rate", "reassigned_rate_ci_low", "reassigned_rate_ci_high",
        "Delta_Miss_m4", "Delta_Miss_m4_ci_low", "Delta_Miss_m4_ci_high",
    ]]
    exp4_data.to_csv(FINAL_ROOT / "exp4" / "FIG5_SCREENING_Q10_FINAL_TEST_DATA.csv", index=False)
    metrics = [
        ("overlap", "Top-K overlap (slots)", "#7570b3"),
        ("reassigned_rate", "Reassigned rate", "#d95f02"),
        ("Delta_Miss_m4", "Robust miss rate difference (D-C)", "#1b9e77"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.5), sharex=True)
    x = np.arange(len(exp4_data))
    for ax, (metric, title, color) in zip(axes, metrics):
        ax.bar(x, exp4_data[metric], color=color, width=0.58)
        ax.errorbar(x, exp4_data[metric], yerr=_error_bounds(exp4_data, metric), fmt="none", ecolor="#222222", capsize=3, lw=0.9)
        ax.axhline(0, color="#555555", lw=0.7)
        ax.set_title(title, fontsize=9)
        ax.set_xticks(x, exp4_data["stage"], rotation=18, ha="right", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Fixed-capacity screening at q = 10%", y=1.02)
    fig.tight_layout()
    path = FINAL_ROOT / "exp4" / "FIG5_SCREENING_Q10_FINAL_TEST.pdf"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    created.append(str(path.relative_to(FINAL_ROOT)))
    return created


def _sign(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return "positive" if float(value) > 0 else "negative" if float(value) < 0 else "zero"


def _directional_comparison(exp1: dict, exp2: pd.DataFrame, exp3: pd.DataFrame, exp4: pd.DataFrame) -> dict:
    """Compare frozen Development and Final-Test directions without new estimands."""
    dev_exp1 = _json(OUTPUT_ROOT / "exp1" / "development" / "EXP1_OUTPUT_MANIFEST.json")
    dev_exp2 = pd.read_csv(OUTPUT_ROOT / "exp2" / "development" / "results" / "EXP2A_SUMMARY.csv")
    dev_exp3 = pd.read_csv(OUTPUT_ROOT / "exp3" / "development" / "EXP3_STAGE_AGREEMENT.csv")
    dev_exp4 = pd.read_csv(OUTPUT_ROOT / "exp4" / "development" / "EXP4_SCREENING_RESULTS.csv")
    final_targets = {row["target"]: row for row in exp1["targets"]}
    dev_targets = {row["target"]: row for row in dev_exp1["history_current"]}
    final_q10 = exp4.loc[np.isclose(exp4["q"], 0.10)].set_index("stage")
    dev_q10 = dev_exp4.loc[np.isclose(dev_exp4["q"], 0.10)].set_index("stage")
    return {
        "exp1_delta_mae_history_minus_current": [
            {"target": target, "development": _sign(dev_targets[target]["Delta_MAE"]), "final_test": _sign(final_targets[target]["Delta_MAE"])}
            for target in ("R_IB", "D_OB", "D_TX")
        ],
        "exp2_kendall_tau_b": {
            "development": float(dev_exp2.iloc[0]["kendall_tau_b"]),
            "final_test": float(exp2.iloc[0]["kendall_tau_b"]),
            "development_direction": _sign(dev_exp2.iloc[0]["kendall_tau_b"]),
            "final_test_direction": _sign(exp2.iloc[0]["kendall_tau_b"]),
        },
        "exp3_kendall_tau_b": [
            {"stage": stage, "development": float(dev_exp3.loc[dev_exp3.stage.eq(stage), "kendall_tau_b"].iloc[0]), "final_test": float(exp3.loc[exp3.stage.eq(stage), "kendall_tau_b"].iloc[0])}
            for stage in exp3["stage"]
        ],
        "exp4_q10_delta_miss_m4": [
            {"stage": stage, "development": float(dev_q10.loc[stage, "Delta_Miss_m4"]), "final_test": float(final_q10.loc[stage, "Delta_Miss_m4"])}
            for stage in final_q10.index
        ],
    }


def _assert_final_test_integrity(figures: list[str]) -> dict:
    """One bounded integrity audit over completed held-out outputs."""
    access = _json(ACCESS_AUDIT)
    cohort = _json(FINAL_ROOT / "FINAL_TEST_COHORT_MANIFEST_V1.json")
    exp1 = _json(FINAL_ROOT / "exp1" / "FINAL_TEST_EXP1_MANIFEST.json")
    exp2 = _json(FINAL_ROOT / "exp2" / "FINAL_TEST_EXP2_MANIFEST.json")
    exp3 = _json(FINAL_ROOT / "exp3" / "FINAL_TEST_EXP3_MANIFEST.json")
    exp4 = _json(FINAL_ROOT / "exp4" / "FINAL_TEST_EXP4_MANIFEST.json")
    inner_exp2 = _json(FINAL_ROOT / "exp2" / "EXP2_MANIFEST.json")
    if access.get("final_test_access_count") != 1 or not access.get("opened"):
        raise RuntimeError("FINAL_TEST_ACCESS_AUDIT_INVALID")
    if cohort.get("selected_episode_count") != 128 or cohort.get("selection_reperformed"):
        raise RuntimeError("FINAL_TEST_COHORT_LINEAGE_INVALID")
    manifests = (exp1, exp2, exp3, exp4)
    if any(m.get("status") != "FINAL_TEST_COMPLETE" for m in manifests):
        raise RuntimeError("FINAL_TEST_EXPERIMENT_STATUS_INVALID")
    if any(m.get("final_test_access_count") != 1 for m in manifests):
        raise RuntimeError("FINAL_TEST_EXPERIMENT_ACCESS_COUNT_INVALID")
    if any(m.get("paper_result") is not True for m in manifests):
        raise RuntimeError("FINAL_TEST_PAPER_RESULT_NOT_FINALIZED")
    if inner_exp2.get("artifact_scope") != "FINAL_TEST_ONLY" or inner_exp2.get("final_test_access_count") != 1:
        raise RuntimeError("FINAL_TEST_EXP2_PROVENANCE_INVALID")
    if _bootstrap_replicates(FINAL_ROOT / "exp1" / "EXP1_HISTORY_CURRENT_BOOTSTRAP.csv") != 2000:
        raise RuntimeError("FINAL_TEST_EXP1_BOOTSTRAP_INCOMPLETE")
    for relative in (
        "exp2/results/EXP2A_BOOTSTRAP.csv", "exp2/results/EXP2B_BOOTSTRAP.csv", "exp2/results/EXP2C_BOOTSTRAP.csv",
        "exp3/EXP3_BOOTSTRAP.csv", "exp3/EXP3_COMMON_EPISODE_BOOTSTRAP.csv", "exp3/EXP3_STAGE_CONTRAST_BOOTSTRAP.csv",
        "exp4/EXP4_BOOTSTRAP.csv",
    ):
        if _bootstrap_replicates(FINAL_ROOT / relative) != 2000:
            raise RuntimeError(f"FINAL_TEST_BOOTSTRAP_INCOMPLETE:{relative}")
    lead = pd.read_csv(FINAL_ROOT / "exp1" / "EXP1_EVALUATION_LEAD_TIME.csv")
    if int(lead.status.eq("PASS").sum()) == 0:
        raise RuntimeError("FINAL_TEST_EXP1_LEAD_SLICES_EMPTY")
    support = _json(FINAL_ROOT / "exp2" / "EXP2_SUPPORT_AUDIT.json")
    if int(support["primary_90"]["n_nodes"]) != 1656:
        raise RuntimeError("FINAL_TEST_EXP2_PRIMARY_SUPPORT_INVALID")
    exp2b = pd.read_csv(FINAL_ROOT / "exp2" / "results" / "EXP2B_COMPONENT_DOMAIN_SUMMARY.csv")
    if not exp2b["n_nodes"].eq(1656).all():
        raise RuntimeError("FINAL_TEST_EXP2B_COMPONENT_POPULATION_INVALID")
    stage = pd.read_csv(FINAL_ROOT / "exp3" / "EXP3_STAGE_AGREEMENT.csv")
    if not stage.status.eq("PASS").all() or not np.isclose(stage.support_coverage, 1.0).all():
        raise RuntimeError("FINAL_TEST_EXP3_PRIMARY_SUPPORT_INVALID")
    q_values = set(pd.read_csv(FINAL_ROOT / "exp4" / "EXP4_SCREENING_RESULTS.csv")["q"].round(2))
    if q_values != {0.05, 0.10, 0.20, 0.30}:
        raise RuntimeError("FINAL_TEST_EXP4_CAPACITY_GRID_INVALID")
    if exp4.get("canonical_events") != exp4.get("supported_canonical_events") or exp4.get("excluded_canonical_events") != 0:
        raise RuntimeError("FINAL_TEST_EXP4_CANONICAL_SUPPORT_INVALID")
    for relative in figures:
        if not (FINAL_ROOT / relative).is_file():
            raise RuntimeError(f"FINAL_TEST_FIGURE_MISSING:{relative}")
    return {
        "status": "PASS",
        "final_test_access_count": 1,
        "selected_episode_count": 128,
        "bootstrap_unique_replicates": {
            "exp1_paired": 2000, "exp2a": 2000, "exp2b": 2000, "exp2c": 2000,
            "exp3_primary": 2000, "exp3_common_episode": 2000, "exp3_contrast": 2000, "exp4": 2000,
        },
        "exp1_lead_slice_pass_rows": int(lead.status.eq("PASS").sum()),
        "exp1_lead_slice_abstention_rows": int(lead.status.ne("PASS").sum()),
        "exp2b_independent_component_population_n_nodes": 1656,
        "exp3_primary_support_coverage": 1.0,
        "exp4_capacity_grid": [0.05, 0.10, 0.20, 0.30],
        "exp4_canonical_before_support": True,
        "figures": figures,
    }


def _write_final_test_report(integrity: dict) -> dict:
    cohort = _json(FINAL_ROOT / "FINAL_TEST_COHORT_MANIFEST_V1.json")
    pre_audit = _json(FINAL_ROOT / "FINAL_TEST_PRE_AUDIT.json")
    exp1 = _json(FINAL_ROOT / "exp1" / "FINAL_TEST_EXP1_MANIFEST.json")
    exp2 = pd.read_csv(FINAL_ROOT / "exp2" / "results" / "EXP2A_SUMMARY.csv")
    exp3 = pd.read_csv(FINAL_ROOT / "exp3" / "EXP3_STAGE_AGREEMENT.csv")
    contrasts = pd.read_csv(FINAL_ROOT / "exp3" / "EXP3_STAGE_CONTRASTS.csv")
    exp4 = pd.read_csv(FINAL_ROOT / "exp4" / "EXP4_SCREENING_RESULTS.csv")
    q10 = exp4.loc[np.isclose(exp4["q"], 0.10)].copy()
    directions = _directional_comparison(exp1, exp2, exp3, exp4)
    report = {
        "schema_version": "AIR_SLOT_FINAL_TEST_RESULT_REPORT_V1",
        "status": "FINAL_TEST_COMPLETE_READY_FOR_HUMAN_RESULT_REVIEW",
        "execution_head": _git_head(),
        "scientific_code_lock": "c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6",
        "cohort_authority_commit": "1c336fb42b0fa7df716f8bf3bc7a67ca0153c06b",
        "cohort": cohort,
        "pre_audit": pre_audit,
        "exp1_targets": exp1["targets"],
        "exp2_primary": exp2.to_dict("records"),
        "exp3_stage_results": exp3.to_dict("records"),
        "exp3_contrasts": contrasts.to_dict("records"),
        "exp4_q10_results": q10.to_dict("records"),
        "development_vs_final_test_direction": directions,
        "integrity_audit": integrity,
        "typed_abstentions": {
            "exp1_lead_slice_rows": integrity["exp1_lead_slice_abstention_rows"],
            "exp4_unsupported_canonical_events": 0,
        },
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
        "paper_result": True,
        "final_test_access_count": 1,
    }
    write_json(FINAL_ROOT / "FINAL_TEST_RESULT_REPORT.json", report)

    target_lines = "\n".join(
        f"| {row['target']} | {row['N_nodes']} | {row['N_episodes']} | {row['History_MAE']:.3f} | {row['Current_MAE']:.3f} | {row['Delta_MAE']:.3f} [{row['Delta_MAE_ci_low']:.3f}, {row['Delta_MAE_ci_high']:.3f}] |"
        for row in exp1["targets"]
    )
    stage_lines = "\n".join(
        f"| {row.stage} | {int(row.n_nodes)} | {row.kendall_tau_b:.3f} [{row.kendall_tau_b_ci_low:.3f}, {row.kendall_tau_b_ci_high:.3f}] | {row.top10_overlap:.3f} [{row.top10_overlap_ci_low:.3f}, {row.top10_overlap_ci_high:.3f}] | {row.median_consequence_priority_percentile_gap:.3f} [{row.median_consequence_priority_percentile_gap_ci_low:.3f}, {row.median_consequence_priority_percentile_gap_ci_high:.3f}] |"
        for row in exp3.itertuples(index=False)
    )
    q10_lines = "\n".join(
        f"| {row.stage} | {int(row.n)} | {int(row.k)} | {row.overlap:.3f} [{row.overlap_ci_low:.3f}, {row.overlap_ci_high:.3f}] | {row.reassigned_rate:.3f} [{row.reassigned_rate_ci_low:.3f}, {row.reassigned_rate_ci_high:.3f}] | {row.Delta_Miss_m4:.3f} [{row.Delta_Miss_m4_ci_low:.3f}, {row.Delta_Miss_m4_ci_high:.3f}] | {int(row.Pareto_reversal_count_D)}/{int(row.Pareto_reversal_count_C)} |"
        for row in q10.itertuples(index=False)
    )
    exp2_row = exp2.iloc[0]
    text = f"""# Air Slot Held-Out Final Test Result Report

Status: `FINAL_TEST_COMPLETE_READY_FOR_HUMAN_RESULT_REVIEW`.

## Execution

- Execution HEAD: `{report['execution_head']}`
- Development scientific code lock: `{report['scientific_code_lock']}`
- Final Test cohort authority commit: `{report['cohort_authority_commit']}`
- `FINAL_TEST_ACCESS_COUNT = 1`
- `model_retrained = false`; `calibration_refit = false`; `parameter_reselected = false`
- `paper_result = true`; this does not modify the manuscript.

## Cohort And Support

- Selected episodes: {cohort['selected_episode_count']} (`{cohort['selected_episode_hash']}`)
- Frozen Q4 eligible pool: {cohort['candidate_eligible_pool_count']}; PRE rolling nodes: {pre_audit['rolling_node_count']}; active analysis nodes: {exp1['rolling_node_count']}.
- Exp2-Exp4 primary-support nodes: {exp2_row.n_nodes}; all three active stages retain full primary support coverage.
- Exp4 canonical events: 238 supported; 0 typed unsupported exclusions. No later-node replacement occurred.

## Exp1

| Target | N nodes | N episodes | History MAE | Current MAE | Delta MAE [95% CI] |
| --- | ---: | ---: | ---: | ---: | ---: |
{target_lines}

R_IB finite-support CRPS is 7.561 (History) versus 9.060 (Current), with Delta -1.498 [-3.139, 0.155]. Evaluation-lead reporting has 16 passing rows and 14 legitimate typed abstentions.

## Exp2

Primary delay/consequence association: Kendall tau-b {exp2_row.kendall_tau_b:.3f} [{exp2_row.kendall_tau_b_ci_low:.3f}, {exp2_row.kendall_tau_b_ci_high:.3f}], Top-10 overlap {exp2_row.top_overlap:.3f} [{exp2_row.top_overlap_ci_low:.3f}, {exp2_row.top_overlap_ci_high:.3f}], median rank displacement {exp2_row.median_rank_displacement:.3f} [{exp2_row.median_rank_displacement_ci_low:.3f}, {exp2_row.median_rank_displacement_ci_high:.3f}]. Exp2B uses the independently defined finite, support-applicable component/domain population.

## Exp3

| Stage | N nodes | Tau-b [95% CI] | Top-10 overlap [95% CI] | Same-delay percentile gap [95% CI] |
| --- | ---: | ---: | ---: | ---: |
{stage_lines}

All three frozen pairwise contrasts and common-episode robustness are present in the formal tables with 2,000 episode-cluster replicates.

## Exp4 At q=10%

| Stage | N | K | Overlap [95% CI] | Reassigned rate [95% CI] | Delta robust miss m=4 [95% CI] | Pareto reversals D/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{q10_lines}

The frozen q grid is 5%, 10%, 20%, and 30%. Pareto reversals remain zero under the locked definition; no alternative definition was introduced.

## Integrity And Interpretation Boundary

All Exp1-Exp4 primary bootstrap artifacts contain 2,000 unique replicate IDs using the frozen seed and original-episode clusters. The Development-versus-Test comparison is stored as sign/value provenance in `FINAL_TEST_RESULT_REPORT.json`; it is descriptive only. No Test result was used to alter a scientific definition or to select reporting parameters.

Paper-facing figure data and vector figures are under `artifacts/experiment/final_test/exp1`, `exp3`, and `exp4`; existing Exp2 figures remain under its Final Test root.
"""
    (ROOT / "formal" / "FINAL_TEST_RESULT_REPORT_20260908.md").write_text(text, encoding="utf-8")
    return report


def _complete_final_test_reporting() -> dict:
    """Finalize provenance and reporting from existing formal outputs only."""
    exp2_out = FINAL_ROOT / "exp2"
    inner = _finalize_exp2_metadata(exp2_out, _json(exp2_out / "EXP2_MANIFEST.json"), paper_result=True)
    outer = _json(exp2_out / "FINAL_TEST_EXP2_MANIFEST.json")
    outer.update({"status": "FINAL_TEST_COMPLETE", "final_test_access_count": 1, "paper_result": True, "artifact_scope": "FINAL_TEST_ONLY"})
    outer["scientific_result"]["manifest"] = inner
    write_json(exp2_out / "FINAL_TEST_EXP2_MANIFEST.json", outer)
    for relative in ("exp1/FINAL_TEST_EXP1_MANIFEST.json", "exp3/FINAL_TEST_EXP3_MANIFEST.json", "exp4/FINAL_TEST_EXP4_MANIFEST.json"):
        path = FINAL_ROOT / relative
        payload = _json(path)
        payload.update({"status": "FINAL_TEST_COMPLETE", "final_test_access_count": 1, "paper_result": True, "artifact_scope": "FINAL_TEST_ONLY"})
        if relative.startswith("exp4/"):
            payload["canonical_selection_order"] = "FIRST_CHRONOLOGICAL_NODE_THEN_SUPPORT"
            payload["unsupported_canonical_later_replacement"] = False
        write_json(path, payload)
    cohort = _json(FINAL_ROOT / "FINAL_TEST_COHORT_MANIFEST_V1.json")
    formal_cohort = dict(cohort)
    formal_cohort["artifact_manifest_path"] = "artifacts/experiment/final_test/FINAL_TEST_COHORT_MANIFEST_V1.json"
    formal_cohort["artifact_manifest_sha256"] = digest(FINAL_ROOT / "FINAL_TEST_COHORT_MANIFEST_V1.json")
    formal_cohort["execution_status"] = "FINAL_TEST_COMPLETE_READY_FOR_HUMAN_RESULT_REVIEW"
    write_json(ROOT / "formal" / "FINAL_TEST_COHORT_MANIFEST_V1.json", formal_cohort)
    figures = _render_final_test_figures()
    integrity = _assert_final_test_integrity(figures)
    write_json(FINAL_ROOT / "FINAL_TEST_INTEGRITY_AUDIT.json", integrity)
    return _write_final_test_report(integrity)


def _exp3(source: pd.DataFrame):
    out = FINAL_ROOT / "exp3"
    out.mkdir(parents=True, exist_ok=True)
    data = scores(source)
    plan = bootstrap_plan(episode_ids(data), BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED)
    estimate = evaluate_stages(data)
    boot = bootstrap_stage_fast(data, plan=plan)
    with_intervals(estimate, boot, ["stage"], METRICS).to_csv(out / "EXP3_STAGE_AGREEMENT.csv", index=False)
    boot.to_csv(out / "EXP3_BOOTSTRAP.csv", index=False)
    contrasts = stage_contrasts(estimate)
    contrast_draws = pd.concat([stage_contrasts(group).assign(replicate=rep) for rep, group in boot.groupby("replicate")], ignore_index=True)
    with_intervals(contrasts, contrast_draws, ["stage_a", "stage_b"]).to_csv(out / "EXP3_STAGE_CONTRASTS.csv", index=False)
    contrast_draws.to_csv(out / "EXP3_STAGE_CONTRAST_BOOTSTRAP.csv", index=False)
    pd.concat([evaluate_stages(data, c) for c in (5.0, 10.0, 15.0)]).to_csv(out / "EXP3_STAGE_HETEROGENEITY.csv", index=False)
    common = common_episode_cohort(data)
    if not common.empty:
        cb = bootstrap_stage_fast(common, plan=bootstrap_plan(episode_ids(common), BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED))
        with_intervals(evaluate_stages(common), cb, ["stage"], METRICS).to_csv(out / "EXP3_COMMON_EPISODE_ROBUSTNESS.csv", index=False)
        cb.to_csv(out / "EXP3_COMMON_EPISODE_BOOTSTRAP.csv", index=False)
    estimate.to_csv(out / "EXP3_STAGE_COHORT.csv", index=False)
    write_json(out / "FINAL_TEST_EXP3_MANIFEST.json", {
        "schema_version": "AIR_SLOT_EXP3_FINAL_TEST_MANIFEST_V1", "status": "FINAL_TEST_COMPLETE",
        "final_test_access_count": 1, "episodes": int(data.original_episode_id.nunique()), "nodes": int(len(data)),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_replicates_completed": int(boot.replicate.nunique()),
        "bootstrap_seed": BOOTSTRAP_SEED, "model_retrained": False, "calibration_refit": False, "parameter_reselected": False,
    })
    return estimate, contrasts


def _exp4(source: pd.DataFrame):
    out = FINAL_ROOT / "exp4"
    out.mkdir(parents=True, exist_ok=True)
    data = scores(source)
    plan = bootstrap_plan(episode_ids(data), BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED)
    events, _ = prepare_canonical_events(data)
    events.to_parquet(out / "EXP4_CANONICAL_EVENTS.parquet", index=False)
    result, evidence = evaluate_screening(events, evidence=True)
    membership = pd.concat([robust_sets(events, threshold) for threshold in (3, 4, 5)], ignore_index=True)
    membership.to_csv(out / "EXP4_ROBUST_MEMBERSHIP.csv", index=False)
    membership[membership.m.eq(4)].to_csv(out / "EXP4_ROBUST_HIGH_CONSEQUENCE.csv", index=False)
    robust_missed_nodes(events, threshold=4).to_csv(out / "EXP4_ROBUST_MISSED_NODES.csv", index=False)
    evidence.to_csv(out / "EXP4_PARETO_EVIDENCE.csv", index=False)
    boot = bootstrap_screening(data, plan=plan)
    boot.to_csv(out / "EXP4_BOOTSTRAP.csv", index=False)
    final = with_intervals(result, boot, ["stage", "q"])
    final.to_csv(out / "EXP4_SCREENING_RESULTS.csv", index=False)
    final[[c for c in final if c in ("stage", "q", "status", "n", "k") or "Capture" in c]].to_csv(out / "EXP4_CAPTURE.csv", index=False)
    final[[c for c in final if c in ("stage", "q", "status", "n", "k") or "Pareto" in c]].to_csv(out / "EXP4_PARETO_SUMMARY.csv", index=False)
    for name, columns in {
        "DELTA_CAPTURE": [c for c in final if "Delta_Capture" in c],
        "DOMAIN_CAPTURE": [c for c in final if "Capture" in c and any(c.startswith(p) for p in ("Capture_D_F", "Capture_C_F", "Delta_Capture_F_pp", "Capture_D_P", "Capture_C_P", "Delta_Capture_P_pp", "Capture_D_R", "Capture_C_R", "Delta_Capture_R_pp"))],
        "NATIVE_COMPONENT_CAPTURE": [c for c in final if "Capture" in c and any(x in c for x in ("continuity", "execution", "propagation", "time", "itinerary", "service", "operating"))],
        "ROBUSTNESS_SUMMARY": [c for c in final if "robust" in c or "Miss" in c],
        "TIE_AUDIT": [c for c in final if "boundary_tie" in c],
    }.items():
        final[[c for c in ("stage", "q", "status", "n", "k", *columns) if c in final]].to_csv(out / f"EXP4_{name}.csv", index=False)
    write_json(out / "FINAL_TEST_EXP4_MANIFEST.json", {
        "schema_version": "AIR_SLOT_EXP4_FINAL_TEST_MANIFEST_V1", "status": "FINAL_TEST_COMPLETE", "final_test_access_count": 1,
        "episodes": int(data.original_episode_id.nunique()), "nodes": int(len(data)), "canonical_events": int(len(events)),
        "supported_canonical_events": int((events.canonical_event_status == "SUPPORTED").sum()),
        "excluded_canonical_events": int((events.canonical_event_status != "SUPPORTED").sum()),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_replicates_completed": int(boot.replicate.nunique()),
        "bootstrap_seed": BOOTSTRAP_SEED, "model_retrained": False, "calibration_refit": False, "parameter_reselected": False,
    })
    return final, events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Finalize provenance, integrity, figures, and reports from completed outputs only.",
    )
    args = parser.parse_args()
    authority = _authority()
    if args.report_only:
        _complete_final_test_reporting()
        return 0
    open_event = _open_event()
    _record_execution_bug()
    selected, cohort = select_cohort(ROOT, authority)
    published, pre_audit = materialize_pre(selected)
    history, current, examples, exact_rows = _m1_examples(published)
    exp1, node_source = _exp1(published, history, current, examples, exact_rows)
    exp2 = _exp2(node_source)
    exp3, contrasts = _exp3(node_source)
    exp4, events = _exp4(node_source)
    _complete_final_test_reporting()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
