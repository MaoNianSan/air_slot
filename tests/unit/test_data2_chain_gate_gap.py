from datetime import datetime, timezone, timedelta
import pytest
from model.common.errors import ContractError
from model.PRE.episode.builder import (build_episode_chain, build_data2_episode_chain,
                                       build_data2_episode_records,
                                       DATA2_CHAIN_RULE_ID, DATA2_CHAIN_RULE_VERSION)
from model.PRE.transformation import current_transformation_registry
from model.PRE.feature_registry.loader import load_registry_bundle
from pathlib import Path


UTC = timezone.utc


def flight(fid, aircraft, origin, dest, arr, dep, *, start=None, end=None, dataset="data2_2019"):
    if start is None:
        start = arr
    if end is None:
        end = dep
    return {"flight_id": fid, "aircraft_id": aircraft, "aircraft_id_namespace": "REGISTRATION",
            "origin_airport_id": origin, "destination_airport_id": dest,
            "actual_arrival_utc": arr, "actual_departure_utc": dep,
            "event_start_time": start, "event_end_time": end, "dataset_instance_id": dataset}


def test_data2_chain_links_on_actual_gate_gap_not_schedule():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1),
               start=t + timedelta(hours=6), end=t + timedelta(hours=7))
    s = flight("s", "N1", "B", "C", t + timedelta(minutes=150), t + timedelta(minutes=95),
               start=t + timedelta(hours=13, minutes=30), end=t + timedelta(hours=14, minutes=30))
    episode = build_data2_episode_chain(p, s)
    assert episode.chain_rule_id == DATA2_CHAIN_RULE_ID
    assert episode.chain_rule_version == DATA2_CHAIN_RULE_VERSION
    assert "gap_source=actual_gate_utc" in episode.chain_rule_parameters
    with pytest.raises(ContractError, match="EPISODE_GAP_EXCEEDS_RULE"):
        build_episode_chain(p, s)  # schedule anchors are 390 min apart -> not linked


def test_data2_chain_rejects_actual_gap_beyond_360():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1))
    s = flight("s", "N1", "B", "C", t + timedelta(minutes=400), t + timedelta(minutes=460))
    with pytest.raises(ContractError, match="EPISODE_GAP_EXCEEDS_RULE"):
        build_data2_episode_chain(p, s)


def test_data2_chain_includes_exact_360_boundary():
    t = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(minutes=40))
    s = flight("s", "N1", "B", "C", t + timedelta(hours=6, minutes=50), t + timedelta(hours=6))
    episode = build_data2_episode_chain(p, s)
    assert episode.successor_flight_id == "s"


def test_data2_chain_rejects_time_order_invalid_and_zero_gap():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1))
    s = flight("s", "N1", "B", "C", t + timedelta(minutes=30), t - timedelta(minutes=30))
    with pytest.raises(ContractError, match="EPISODE_TIME_ORDER_INVALID"):
        build_data2_episode_chain(p, s)
    s2 = flight("s", "N1", "B", "C", t + timedelta(minutes=60), t)
    with pytest.raises(ContractError, match="EPISODE_TIME_ORDER_INVALID"):
        build_data2_episode_chain(p, s2)


def test_data2_chain_rejects_airport_discontinuity_and_aircraft_mismatch():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1))
    s = flight("s", "N1", "X", "C", t + timedelta(hours=2), t + timedelta(hours=3))
    with pytest.raises(ContractError, match="EPISODE_AIRPORT_DISCONTINUITY"):
        build_data2_episode_chain(p, s)
    s2 = flight("s", "N2", "B", "C", t + timedelta(hours=2), t + timedelta(hours=3))
    with pytest.raises(ContractError, match="EPISODE_AIRCRAFT_MISMATCH"):
        build_data2_episode_chain(p, s2)


def test_data2_chain_rejects_mixed_dataset_rows():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1), dataset="data1_2019")
    s = flight("s", "N1", "B", "C", t + timedelta(hours=2), t + timedelta(hours=3), dataset="data2_2019")
    with pytest.raises(ContractError, match="EPISODE_DATASET_MISMATCH"):
        build_data2_episode_chain(p, s)


def test_data2_chain_requires_actual_gate_fields():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1))
    s = {"flight_id": "s", "aircraft_id": "N1", "aircraft_id_namespace": "REGISTRATION",
         "origin_airport_id": "B", "destination_airport_id": "C",
         "event_start_time": t + timedelta(hours=2), "event_end_time": t + timedelta(hours=3),
         "dataset_instance_id": "data2_2019"}
    with pytest.raises(ContractError, match="EPISODE_IDENTITY_MISSING"):
        build_data2_episode_chain(p, s)


def test_data2_chain_uses_utc_actuals_across_midnight():
    t = datetime(2019, 1, 1, 23, 30, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(minutes=40))
    s = flight("s", "N1", "B", "C", t + timedelta(minutes=75), t + timedelta(minutes=120))
    episode = build_data2_episode_chain(p, s)
    assert episode.predecessor_flight_id == "p"
    assert episode.successor_flight_id == "s"


def test_data2_episode_anchors_are_crs_turnaround_window():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1),
               start=t + timedelta(hours=6), end=t + timedelta(hours=7))
    s = flight("s", "N1", "B", "C", t + timedelta(hours=2), t + timedelta(hours=3),
               start=t + timedelta(hours=12), end=t + timedelta(hours=13))
    episode = build_data2_episode_chain(p, s)
    assert episode.episode_start_time == p["event_end_time"]  # pred.CRSArr
    assert episode.episode_end_time == s["event_start_time"]  # succ.CRSDep
    assert "episode_anchors=schedule_turnaround_window" in episode.chain_rule_parameters
    assert "EPISODE_ANCHORS_PENDING_D2_2" not in episode.quality_flags


def test_data2_episode_records_sort_by_actual_times_and_reject_duplicates():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    rows = [
        flight("s1", "N1", "B", "C", t + timedelta(hours=2), t + timedelta(hours=3)),
        flight("p1", "N1", "A", "B", t, t + timedelta(hours=1)),
    ]
    episodes = build_data2_episode_records(rows)
    assert [e.predecessor_flight_id for e in episodes] == ["p1"]
    with pytest.raises(ContractError, match="EPISODE_DUPLICATE_ORDERING_KEY"):
        build_data2_episode_records(rows + [dict(rows[0])])


def test_data2_chain_rule_registered_frozen_and_data1_rule_untouched():
    registry = current_transformation_registry()
    rule = registry.get("DATA2_SAME_AIRCRAFT_AIRPORT_GAP", "1.0.0")
    assert rule.status.value == "FROZEN"
    assert rule.adjacency_rule == "POSITIVE_ACTUAL_GATE_GAP_WITHIN_MAX_360_MINUTES"
    assert rule.evidence_class.value == "DIRECT"
    data1_rule = registry.get("SAME_AIRCRAFT_AIRPORT_GAP", "1.0.0")
    assert data1_rule.status.value == "FROZEN"
    assert data1_rule.adjacency_rule == "POSITIVE_GAP_WITHIN_MAX_360_MINUTES"
    bundle = load_registry_bundle(Path("registries"))
    rule_ids = {r.rule_id for r in bundle.data_usage_rules}
    assert "D2-CHAIN-GATE-GAP" in rule_ids
    assert "D1-OPENSKY-FLIGHT" in rule_ids
    d2 = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-CHAIN-GATE-GAP")
    assert d2.freeze_state.value == "FROZEN"
    assert d2.dataset_id == "data2_2019"
    assert "D2-BTS-ACTUAL" in d2.external_evidence_rule_ids


def test_data2_episode_records_skips_inverted_turnaround_window():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(minutes=40),
               start=t + timedelta(hours=8), end=t + timedelta(hours=8, minutes=30))
    s = flight("s", "N1", "B", "C", t + timedelta(minutes=70), t + timedelta(minutes=120),
               start=t + timedelta(hours=6, minutes=30), end=t + timedelta(hours=7))
    episodes = build_data2_episode_records([p, s])
    assert episodes == []
    # zero-length turnaround window (pred.CRSArr == succ.CRSDep) is also excluded
    s2 = flight("s", "N1", "B", "C", t + timedelta(minutes=70), t + timedelta(minutes=120),
                start=t + timedelta(hours=8, minutes=30), end=t + timedelta(hours=9))
    episodes2 = build_data2_episode_records([p, s2])
    assert episodes2 == []
