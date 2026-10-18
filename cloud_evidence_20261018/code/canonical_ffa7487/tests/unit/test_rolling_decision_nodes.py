from datetime import datetime, timedelta, timezone

import pytest

from model.common.enums import OperationalStage, SupportState
from model.common.errors import NodeInvalidationError
from model.PRE.canonical.normalization import canonicalize_flightlist_row
from model.PRE.episode.builder import build_episode_records
from model.PRE.episode.node_builder import (
    build_decision_node,
    build_rolling_decision_nodes,
    stage_at,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry


UTC = timezone.utc


def _flight_row(callsign, origin, destination, first_seen, last_seen, icao24='abc123'):
    return {
        'callsign': callsign, 'day': first_seen.date().isoformat(),
        'origin': origin, 'destination': destination, 'icao24': icao24,
        'firstseen': first_seen.isoformat(), 'lastseen': last_seen.isoformat(),
    }


def _flight_dict(flight):
    return {
        'flight_id': flight.flight_id, 'aircraft_id': flight.aircraft_id,
        'aircraft_id_namespace': flight.aircraft_id_namespace,
        'origin_airport_id': flight.origin_airport_id,
        'destination_airport_id': flight.destination_airport_id,
        'event_start_time': flight.event_start_time,
        'event_end_time': flight.event_end_time,
        'dataset_instance_id': flight.dataset_instance_id,
        'canonical_record_id': flight.canonical_record_id,
    }


def test_flightlist_firstseen_lastseen_anchor_episode_interval():
    first_seen = datetime(2018, 12, 31, 23, 0, tzinfo=UTC)
    last_seen = datetime(2019, 1, 1, 1, 30, tzinfo=UTC)
    flight, event = canonicalize_flightlist_row(
        _flight_row('AF123', 'LFPG', 'EDDF', first_seen, last_seen))
    assert flight.event_start_time == first_seen
    assert flight.event_end_time == last_seen
    assert flight.aircraft_id_namespace == 'ICAO24'
    assert flight.decision_time_role.value == 'EPISODE_CONSTRUCTION'
    assert event.event_type == 'ARCHIVE_FLIGHT_INTERVAL_PROXY'
    assert event.availability_basis.value == 'POSTHOC_ONLY'


def test_rolling_grid_t0_is_episode_start_and_stops_at_episode_end():
    pred_start = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)
    pred_end = datetime(2019, 1, 1, 1, 0, tzinfo=UTC)
    succ_start = datetime(2019, 1, 1, 4, 0, tzinfo=UTC)
    succ_end = datetime(2019, 1, 1, 5, 30, tzinfo=UTC)
    pred_flight, pred_event = canonicalize_flightlist_row(
        _flight_row('AF123', 'LFPG', 'EDDF', pred_start, pred_end))
    succ_flight, succ_event = canonicalize_flightlist_row(
        _flight_row('LH456', 'EDDF', 'EGLL', succ_start, succ_end))
    episodes = build_episode_records(
        [_flight_dict(pred_flight), _flight_dict(succ_flight)])
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.episode_start_time == pred_start
    assert episode.episode_end_time == succ_end
    nodes = build_rolling_decision_nodes(
        episode=episode, predecessor_outcome=pred_event, successor_outcome=succ_event,
        config_hash='sha256:c', registry_hash='sha256:r')
    expected_count = 1 + int((succ_end - pred_start).total_seconds() // 300)
    assert len(nodes) == expected_count == 67
    assert nodes[0].decision_time == pred_start
    assert nodes[-1].decision_time == succ_end
    assert all((b.decision_time - a.decision_time).total_seconds() == 300
               for a, b in zip(nodes, nodes[1:]))
    assert all(node.information_cutoff == node.decision_time for node in nodes)
    assert all(node.roll_minutes == 5 for node in nodes)
    assert [node.node_index for node in nodes] == list(range(len(nodes)))


def test_decision_node_rejects_non_five_minute_roll():
    t0 = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)
    with pytest.raises(NodeInvalidationError, match='FORMAL_ROLL_INTERVAL_MUST_BE_FIVE_MINUTES'):
        build_decision_node(
            episode_id='e', predecessor_id='p', successor_id='s',
            decision_time=t0, information_cutoff=t0,
            config_hash='sha256:c', registry_hash='sha256:r',
            legal_record_ids=(), roll_minutes=10)


def test_operational_stage_progression_at_typed_outcome_times():
    t0 = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)
    in_block = datetime(2019, 1, 1, 1, 0, tzinfo=UTC)
    off_block = datetime(2019, 1, 1, 4, 0, tzinfo=UTC)
    takeoff = datetime(2019, 1, 1, 4, 30, tzinfo=UTC)
    assert stage_at(t0, predecessor_in_block=in_block, successor_off_block=off_block,
                    successor_takeoff=takeoff) is OperationalStage.PRE_IB
    assert stage_at(in_block + timedelta(minutes=30), predecessor_in_block=in_block,
                    successor_off_block=off_block, successor_takeoff=takeoff) is OperationalStage.POST_IB_PRE_OB
    assert stage_at(off_block + timedelta(minutes=10), predecessor_in_block=in_block,
                    successor_off_block=off_block, successor_takeoff=takeoff) is OperationalStage.POST_OB_PRE_TO
    assert stage_at(takeoff + timedelta(minutes=10), predecessor_in_block=in_block,
                    successor_off_block=off_block, successor_takeoff=takeoff) is OperationalStage.COMPLETED
    assert stage_at(t0, predecessor_in_block=None, successor_off_block=off_block,
                    successor_takeoff=takeoff) is OperationalStage.PRE_IB


def test_registry_records_approved_t0_anchor_formula():
    rule = current_transformation_registry().get('ROLLING_DECISION_NODE_5MIN', '1.0.0')
    assert rule.status is TransformationStatus.FROZEN
    assert rule.temporal_rule == 'T_N_EQUALS_T0_PLUS_5N'
    assert 'FIVE_MINUTE_GRID_T0_EPISODE_START_TO_EPISODE_END' in rule.formula_or_algorithm
    assert rule.formal_executable is True
