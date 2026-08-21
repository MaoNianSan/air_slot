from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from exp.exp1.development.wstar import recommend_window
from model.M1.coverage import active_node_prefixes
from model.M1.data import encode_pre_sequence, fit_train_normalization
from model.M1.history import adaptive_history, current_history, fixed_history
from model.M1.preparation import normalization_rows
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.contracts.pre_state import EpisodeRecord
from model.PRE.episode.builder import build_data2_episode_chain, build_data2_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import ProductionPREPublisher, ProductionPRERequest
from model.PRE.streaming.data2 import (
    PROJECTED_ONTIME_COLUMNS,
    iter_lightweight_flights,
    latest_weather,
    load_timezones,
    ontime_paths,
    publish_episode_states,
)
from model.PRE.streaming.development import summarize_episode_publication


ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
ZONES = {"JFK": "America/New_York", "LAX": "America/Los_Angeles"}


def _row(**updates):
    row = {
        "FlightDate": "2019-08-05",
        "Reporting_Airline": "AA",
        "Tail_Number": "N1",
        "Flight_Number_Reporting_Airline": "10",
        "Origin": "JFK",
        "Dest": "LAX",
        "CRSDepTime": "0800",
        "CRSArrTime": "1100",
        "DepTime": "0810",
        "ArrTime": "1120",
        "WheelsOff": "0825",
        "WheelsOn": "1105",
        "TaxiOut": "15",
        "TaxiIn": "15",
        "DepDelay": "10",
        "ArrDelay": "20",
        "DepDelayMinutes": "10",
        "ArrDelayMinutes": "20",
        "Cancelled": "0",
        "Diverted": "0",
    }
    row.update(updates)
    return row


def _typed_fixture():
    predecessor_schedule, predecessor_outcome = canonicalize_ontime_row(
        _row(
            FlightDate="2019-08-04",
            Flight_Number_Reporting_Airline="9",
            Origin="LAX",
            Dest="JFK",
            CRSDepTime="2200",
            CRSArrTime="0600",
            DepTime="2200",
            ArrTime="0630",
            WheelsOff="2215",
            WheelsOn="0615",
            DepDelay="0",
            ArrDelay="30",
            DepDelayMinutes="0",
            ArrDelayMinutes="30",
        ),
        ZONES,
    )
    successor_schedule, successor_outcome = canonicalize_ontime_row(_row(), ZONES)
    episode = EpisodeRecord(
        episode_id="migration-e",
        dataset_instance_id="data2_2019",
        predecessor_flight_id=predecessor_schedule.flight_id,
        successor_flight_id=successor_schedule.flight_id,
        aircraft_id="N1",
        aircraft_id_namespace="REGISTRATION",
        connection_airport_id="JFK",
        episode_start_time=predecessor_schedule.scheduled_arrival_utc,
        episode_end_time=successor_outcome.wheels_off_utc,
        chain_rule_id="D2-CHAIN-TEST",
        lineage_support="SUPPORTED",
        formal_eligible=True,
    )
    return (
        episode,
        successor_schedule,
        predecessor_outcome,
        successor_outcome,
    )


def _flight(flight_id, start_hour):
    start = datetime(2019, 8, 1, start_hour, tzinfo=UTC)
    return {
        "flight_id": flight_id,
        "aircraft_id": "N1",
        "aircraft_id_namespace": "REGISTRATION",
        "origin_airport_id": "JFK",
        "destination_airport_id": "JFK",
        "event_start_time": start,
        "event_end_time": start + timedelta(hours=1),
        "actual_departure_utc": start + timedelta(minutes=5),
        "actual_arrival_utc": start + timedelta(hours=1, minutes=5),
        "dataset_instance_id": "data2_2019",
    }


def _legacy_episode_records(flights):
    grouped = defaultdict(list)
    for row in flights:
        grouped[
            (
                row["dataset_instance_id"],
                row["aircraft_id_namespace"],
                row["aircraft_id"],
            )
        ].append(row)
    output = []
    for rows in grouped.values():
        ordered = sorted(
            rows,
            key=lambda row: (
                row["actual_departure_utc"],
                row["actual_arrival_utc"],
                row["flight_id"],
            ),
        )
        for predecessor, successor in zip(ordered, ordered[1:]):
            try:
                output.append(build_data2_episode_chain(predecessor, successor))
            except Exception:
                continue
    return output


def _legacy_publish(item):
    episode, schedule, predecessor_outcome, successor_outcome = item
    nodes = build_rolling_decision_nodes(
        episode=episode,
        predecessor_outcome=predecessor_outcome,
        successor_outcome=successor_outcome,
        config_hash="sha256:c",
        registry_hash="sha256:r",
    )
    publisher = ProductionPREPublisher.from_project()
    states = tuple(
        publisher.publish(
            ProductionPRERequest(
                episode_id=episode.episode_id,
                predecessor_id=episode.predecessor_flight_id,
                successor_id=episode.successor_flight_id,
                dataset_instance_id="data2_2019",
                decision_time=node.decision_time,
                information_cutoff=node.information_cutoff,
                records=(schedule,),
                config_hash="sha256:c",
                registry_hash="sha256:r",
                connection_airport_id=episode.connection_airport_id,
                operational_stage=node.operational_stage,
                node_index=node.node_index,
                roll_minutes=node.roll_minutes,
            )
        ).pre_state
        for node in nodes
    )
    return nodes, states


def _paths(item, nodes, states):
    episode, schedule, predecessor_outcome, successor_outcome = item
    return tuple(
        active_node_prefixes(
            episode=episode,
            nodes=nodes,
            states=states,
            successor_schedule=schedule,
            predecessor_outcome=predecessor_outcome,
            successor_outcome=successor_outcome,
        )
    )


def _new_and_old():
    item = _typed_fixture()
    old_nodes, old_states = _legacy_publish(item)
    publisher = ProductionPREPublisher.from_project()
    new_nodes, new_states = publish_episode_states(
        item,
        "sha256:c",
        "sha256:r",
        {},
        180,
        publisher=publisher,
    )
    return item, old_nodes, old_states, new_nodes, new_states


def test_pre_old_new_episode_identity():
    flights = [_flight("f1", 1), _flight("f2", 4), _flight("f3", 7)]
    old = _legacy_episode_records(flights)
    new = build_data2_episode_records(flights)
    assert [item.model_dump(mode="json") for item in new] == [
        item.model_dump(mode="json") for item in old
    ]


def test_pre_old_new_real_subset_canonical_and_episode_identity():
    paths = ontime_paths(ROOT, months=(8,))
    if not paths or not paths[0].is_file():
        pytest.skip("LOCAL_DATA2_REAL_SUBSET_NOT_AVAILABLE")
    path = paths[0]
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    generator = iter_lightweight_flights(path, zones)
    new = tuple(islice(generator, 64))
    generator.close()

    old = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        for raw in csv.DictReader(stream):
            try:
                schedule, outcome = canonicalize_ontime_row(
                    {name: raw.get(name, "") for name in PROJECTED_ONTIME_COLUMNS},
                    zones,
                )
            except Exception:
                continue
            if (
                schedule.aircraft_id is None
                or outcome.cancelled
                or outcome.diverted
                or outcome.actual_departure_utc is None
                or outcome.actual_arrival_utc is None
            ):
                continue
            old.append(
                {
                    "flight_id": schedule.flight_id,
                    "aircraft_id": schedule.aircraft_id,
                    "aircraft_id_namespace": schedule.aircraft_id_namespace,
                    "origin_airport_id": schedule.origin_airport_id,
                    "destination_airport_id": schedule.destination_airport_id,
                    "event_start_time": schedule.event_start_time,
                    "event_end_time": schedule.event_end_time,
                    "actual_arrival_utc": outcome.actual_arrival_utc,
                    "actual_departure_utc": outcome.actual_departure_utc,
                    "dataset_instance_id": schedule.dataset_instance_id,
                    "service_date": schedule.service_date.isoformat(),
                }
            )
            if len(old) == len(new):
                break

    assert len(new) == 64
    assert tuple(old) == new
    assert [item.model_dump(mode="json") for item in build_data2_episode_records(new)] == [
        item.model_dump(mode="json") for item in build_data2_episode_records(old)
    ]


def test_pre_old_new_node_identity():
    _, old_nodes, _, new_nodes, _ = _new_and_old()
    assert [item.model_dump(mode="json") for item in new_nodes] == [
        item.model_dump(mode="json") for item in old_nodes
    ]


def test_pre_old_new_weather_assignment():
    cutoff = datetime(2019, 8, 1, 12, tzinfo=UTC)
    observations = tuple(
        SimpleNamespace(
            airport_id="JFK",
            availability_time=cutoff + timedelta(minutes=offset),
            reference_id=f"wx-{offset}",
        )
        for offset in (-30, -5, 10)
    )
    index = {"JFK": (tuple(item.availability_time for item in observations), observations)}
    legacy = [item for item in observations if item.availability_time <= cutoff][-1]
    assert latest_weather(index, "JFK", cutoff, 60).reference_id == legacy.reference_id


def test_pre_old_new_support_state():
    _, _, old_states, _, new_states = _new_and_old()
    assert [item.target_support for item in new_states] == [
        item.target_support for item in old_states
    ]
    assert [item.predecessor_state for item in new_states] == [
        item.predecessor_state for item in old_states
    ]


def test_pre_old_new_evidence_state():
    _, _, old_states, _, new_states = _new_and_old()
    assert [item.evidence_ledger for item in new_states] == [
        item.evidence_ledger for item in old_states
    ]
    assert [item.variable_lineage for item in new_states] == [
        item.variable_lineage for item in old_states
    ]


def test_pre_old_new_features():
    item, old_nodes, old_states, new_nodes, new_states = _new_and_old()
    old_paths, new_paths = _paths(item, old_nodes, old_states), _paths(
        item, new_nodes, new_states
    )
    old_prefixes = [prefix for _, prefix, _ in old_paths]
    new_prefixes = [prefix for _, prefix, _ in new_paths]
    normalization = fit_train_normalization(normalization_rows(old_prefixes), split="train")
    for old, new in zip(old_prefixes, new_prefixes):
        assert torch.allclose(
            encode_pre_sequence(old, normalization),
            encode_pre_sequence(new, normalization),
            rtol=1e-6,
            atol=1e-7,
        )


def test_pre_old_new_labels():
    item, old_nodes, old_states, new_nodes, new_states = _new_and_old()
    old_paths, new_paths = _paths(item, old_nodes, old_states), _paths(
        item, new_nodes, new_states
    )
    assert [labels for _, _, labels in new_paths] == [
        labels for _, _, labels in old_paths
    ]


def test_pre_stream_aggregate_matches_full_publication():
    item, _, _, nodes, states = _new_and_old()
    publisher = ProductionPREPublisher.from_project()
    summary = summarize_episode_publication(
        item[0],
        weather={},
        weather_max_age_minutes=180,
        target_support=publisher.target_support("data2_2019"),
    )
    supported_nodes = sum(
        any(
            target.active and target.support_state.value == "SUPPORTED"
            for target in state.target_support
        )
        for state in states
    )
    weather_supported = sum(
        state.current_state["current_weather"].support_state.value == "SUPPORTED"
        for state in states
    )
    assert summary["node_count"] == len(nodes)
    assert summary["eligible_nodes"] == supported_nodes
    assert summary["weather_supported_nodes"] == weather_supported
    assert summary["weather_abstain_nodes"] == len(nodes) - weather_supported


def _legacy_history(states, variant, window=None):
    full = tuple(states)
    if variant == "ADAPTIVE":
        return full
    if variant == "CURRENT":
        return (full[-1],)
    lower = full[-1].decision_node.decision_time - timedelta(minutes=window)
    return tuple(item for item in full if item.decision_node.decision_time >= lower)


def test_current_history_old_new_exact():
    _, _, states, _, _ = _new_and_old()
    assert current_history(states) == _legacy_history(states, "CURRENT")


def test_fixed_history_30_old_new_exact():
    _, _, states, _, _ = _new_and_old()
    assert fixed_history(states, 30) == _legacy_history(states, "FIXED", 30)


def test_adaptive_history_old_new_exact():
    _, _, states, _, _ = _new_and_old()
    assert adaptive_history(states) == _legacy_history(states, "ADAPTIVE")


def test_frozen_h_aggregation_fixture_parity():
    evidence = json.loads(
        (
            ROOT
            / "artifacts"
            / "diagnostics"
            / "v5_development_freeze"
            / "m1_hstar_evidence.json"
        ).read_text(encoding="utf-8")
    )
    for hidden_size in (16, 32):
        rows = [
            row["episode_balanced_joint_nll"]
            for row in evidence["per_seed"]
            if row["hidden_size"] == hidden_size
        ]
        assert statistics.mean(rows) == evidence["candidate_summary"][str(hidden_size)][
            "mean_joint_nll"
        ]


def test_frozen_w_aggregation_and_recommendation_fixture_parity():
    evidence = json.loads(
        (
            ROOT
            / "artifacts"
            / "diagnostics"
            / "v5_development_freeze"
            / "m1_wstar_evidence.json"
        ).read_text(encoding="utf-8")
    )
    means = {
        int(window): values["mean_joint_nll"]
        for window, values in evidence["per_candidate"].items()
    }
    raw_best, recommendation, relative, equivalent = recommend_window(means)
    assert raw_best == evidence["best_raw_W"]
    assert recommendation == evidence["codex_recommendation"]
    assert relative == {
        int(key): value for key, value in evidence["relative_difference_to_best"].items()
    }
    assert equivalent == {
        int(key): value for key, value in evidence["within_0_5_percent_equivalence"].items()
    }
