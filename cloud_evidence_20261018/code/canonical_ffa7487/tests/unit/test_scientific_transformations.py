from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.episode.builder import build_episode_chain, build_episode_records
from model.PRE.transformation import (
    ConstructionType,
    TransformationStatus,
    build_reference_fit_manifest,
    current_transformation_registry,
    derive_scientific_object,
)
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.value_objects import SupportedValue


UTC = timezone.utc


def flight(fid, start_hour, origin, destination):
    start = datetime(2019, 1, 1, start_hour, tzinfo=UTC)
    return {
        "flight_id": fid,
        "aircraft_id": "N1",
        "aircraft_id_namespace": "REGISTRATION",
        "origin_airport_id": origin,
        "destination_airport_id": destination,
        "event_start_time": start,
        "event_end_time": start + timedelta(hours=1),
        "dataset_instance_id": "data2_2019",
    }


def supported(value, evidence=EvidenceClass.DIRECT):
    return SupportedValue(
        value=value,
        unit="min",
        evidence_class=evidence,
        support_ceiling=evidence,
        support_state=SupportState.SUPPORTED,
    )


def test_physical_row_order_does_not_change_flight_chain_identity():
    rows = [flight("f1", 1, "A", "B"), flight("f2", 3, "B", "C"), flight("f3", 5, "C", "D")]
    forward = build_episode_records(rows)
    reverse = build_episode_records(list(reversed(rows)))
    assert tuple(item.episode_id for item in forward) == tuple(item.episode_id for item in reverse)


def test_posthoc_fields_do_not_change_offline_episode_identity():
    rows = [flight("f1", 1, "A", "B"), flight("f2", 3, "B", "C")]
    changed = [{**row, "actual_departure_utc": datetime(2020, 1, 1, tzinfo=UTC)} for row in rows]
    assert build_episode_records(rows)[0].episode_id == build_episode_records(changed)[0].episode_id


def test_valid_multi_parent_derivation_is_derived_not_unsupported():
    rule = current_transformation_registry().get("ROLLING_DECISION_NODE_5MIN", "1.0.0")
    value = derive_scientific_object(
        rule=rule,
        parents={"start": supported(10), "end": supported(25)},
        parent_object_ids=("record:end", "record:start"),
        transform=lambda parents: parents["end"] - parents["start"],
    )
    assert value.value == 15
    assert value.evidence_class is EvidenceClass.DERIVED
    assert value.support_state is SupportState.SUPPORTED
    assert value.source_object_types == ("EpisodeRecord",)
    assert value.source_fields == ("episode_start_time", "episode_end_time")
    assert value.temporal_rule == "T_N_EQUALS_T0_PLUS_5N"
    assert value.evidence_rule == "DERIVED"
    assert value.support_rule == "EPISODE_IDENTITY_REQUIRED"
    assert value.transformation_status is TransformationStatus.FROZEN
    assert value.provenance[-1] == "ROLLING_DECISION_NODE_5MIN@1.0.0"


def test_derived_support_never_exceeds_weaker_parent_evidence():
    rule = current_transformation_registry().get("ROLLING_DECISION_NODE_5MIN", "1.0.0")
    proxy_parent = SupportedValue(
        value=25, unit="min", evidence_class=EvidenceClass.DOMAIN_PROXY,
        support_ceiling=EvidenceClass.DOMAIN_PROXY,
        support_state=SupportState.DEGRADED, reason_code="AGGREGATE_PROXY")
    value = derive_scientific_object(
        rule=rule, parents={"start": supported(10), "end": proxy_parent},
        parent_object_ids=("direct:start", "proxy:end"),
        transform=lambda parents: parents["end"] - parents["start"])
    assert value.evidence_class is EvidenceClass.DOMAIN_PROXY
    assert value.support_ceiling is EvidenceClass.DOMAIN_PROXY
    assert value.support_state is SupportState.DEGRADED


def test_missing_critical_parent_never_fabricates_value():
    rule = current_transformation_registry().get("ROLLING_DECISION_NODE_5MIN", "1.0.0")
    missing = SupportedValue(
        value=None, unit="min", evidence_class=EvidenceClass.UNSUPPORTED,
        support_ceiling=EvidenceClass.UNSUPPORTED, support_state=SupportState.ABSTAIN,
        reason_code="NO_PARENT")
    value = derive_scientific_object(
        rule=rule, parents={"start": supported(10), "end": missing},
        parent_object_ids=("record:start", "record:end"),
        transform=lambda parents: 999)
    assert value.value is None
    assert value.support_state is SupportState.ABSTAIN


def test_development_candidate_rule_cannot_execute_formal_path():
    rule = current_transformation_registry().get("TURNAROUND_REFERENCE", "0.1.0")
    assert rule.status is TransformationStatus.DEVELOPMENT_CANDIDATE
    with pytest.raises(ContractError, match="CONSTRUCTION_RULE_NOT_FROZEN"):
        derive_scientific_object(
            rule=rule, parents={"state": supported(True)}, parent_object_ids=("s",),
            transform=lambda parents: "takeoff")


def test_train_reference_manifest_is_reproducible_and_excludes_nontrain():
    rule = current_transformation_registry().get("TAXI_REFERENCE", "0.1.0")
    records = [
        {"record_id": "t2", "source_fingerprint": "h2", "split": "train"},
        {"record_id": "d", "source_fingerprint": "hd", "split": "development"},
        {"record_id": "t1", "source_fingerprint": "h1", "split": "train"},
        {"record_id": "x", "source_fingerprint": "hx", "split": "test"},
    ]
    args = dict(rule=rule, fit_period="2019H1", grouping_keys=("airport",),
                statistic_id="NOT_FROZEN", minimum_support_rule="NOT_FROZEN",
                applicability_scope="AIRPORT_GROUP_NOT_FROZEN")
    first = build_reference_fit_manifest(records, **args)
    second = build_reference_fit_manifest(list(reversed(records)), **args)
    assert first == second
    assert first.training_record_ids == ("t1", "t2")
    assert first.sample_count == 2
    assert first.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE
    assert first.applicability_scope == "AIRPORT_GROUP_NOT_FROZEN"


def test_episode_link_retains_explicit_relation_and_source_lineage():
    episode = build_episode_records([
        {**flight("f1", 1, "A", "B"), "canonical_record_id": "canonical:f1"},
        {**flight("f2", 3, "B", "C"), "canonical_record_id": "canonical:f2"},
    ])[0]
    assert episode.chain_rule_id == "SAME_AIRCRAFT_AIRPORT_GAP"
    assert episode.chain_rule_version == "1.0.0"
    assert episode.relation_type == "SAME_AIRCRAFT_PREDECESSOR_SUCCESSOR"
    assert episode.source_record_ids == ("canonical:f1", "canonical:f2")
    assert episode.construction_provenance[-1] == "SAME_AIRCRAFT_AIRPORT_GAP@1.0.0"
    assert "ORDER_BY(event_start_time,event_end_time,flight_id)" in episode.ordering_rule


def test_exact_duplicate_scientific_ordering_key_is_rejected():
    row = flight("f1", 1, "A", "B")
    with pytest.raises(ContractError, match="EPISODE_DUPLICATE_ORDERING_KEY"):
        build_episode_records([row, dict(row)])


def test_registry_classifies_all_construction_types_and_unfrozen_objects():
    registry = current_transformation_registry()
    chain_rule = registry.get("SAME_AIRCRAFT_AIRPORT_GAP", "1.0.0")
    assert chain_rule.construction_type is ConstructionType.RELATIONAL_DERIVATION
    assert chain_rule.group_by_keys == ("dataset_instance_id", "aircraft_id_namespace", "aircraft_id")
    assert chain_rule.window_rule == "ADJACENT_ROWS_WITHIN_GROUP"
    assert chain_rule.duplicate_rule == "REJECT_EXACT_DUPLICATE_ORDERING_KEY"
    assert registry.get("TURNAROUND_REFERENCE", "0.1.0").reason_code == "CONSTRUCTION_RULE_NOT_FROZEN"


def test_approved_max_gap_360_boundary_accepted_and_recorded():
    f1 = flight('f1', 1, 'A', 'B')
    f2 = flight('f2', 8, 'B', 'C')
    episodes = build_episode_records([f1, f2])
    assert len(episodes) == 1
    assert episodes[0].chain_rule_id == 'SAME_AIRCRAFT_AIRPORT_GAP'
    assert episodes[0].chain_rule_parameters == ('max_gap_minutes=360',)


def test_max_gap_360_one_minute_over_rejected_and_episode_skipped():
    f1 = flight('f1', 1, 'A', 'B')
    f2 = {**flight('f2', 8, 'B', 'C'), 'event_start_time': datetime(2019, 1, 1, 8, 1, tzinfo=UTC)}
    with pytest.raises(ContractError, match='EPISODE_GAP_EXCEEDS_RULE'):
        build_episode_chain(f1, f2)
    assert build_episode_records([f1, f2]) == []


def test_zero_and_negative_gap_rejected_as_time_order_invalid():
    f1 = flight('f1', 1, 'A', 'B')
    zero = {**flight('f2', 2, 'B', 'C'), 'event_start_time': datetime(2019, 1, 1, 2, 0, tzinfo=UTC)}
    negative = {**flight('f2', 2, 'B', 'C'), 'event_start_time': datetime(2019, 1, 1, 1, 30, tzinfo=UTC)}
    for row in (zero, negative):
        with pytest.raises(ContractError, match='EPISODE_TIME_ORDER_INVALID'):
            build_episode_chain(f1, row)


def test_airport_discontinuity_rejects_link():
    f1 = flight('f1', 1, 'A', 'B')
    f2 = flight('f2', 3, 'X', 'C')
    with pytest.raises(ContractError, match='EPISODE_AIRPORT_DISCONTINUITY'):
        build_episode_chain(f1, f2)


def test_cross_dataset_link_rejected():
    f1 = flight('f1', 1, 'A', 'B')
    f2 = {**flight('f2', 3, 'B', 'C'), 'dataset_instance_id': 'data1_2019'}
    with pytest.raises(ContractError, match='EPISODE_DATASET_MISMATCH'):
        build_episode_chain(f1, f2)


def test_missing_chain_identity_key_rejected():
    f1 = flight('f1', 1, 'A', 'B')
    broken = {k: v for k, v in flight('f2', 3, 'B', 'C').items() if k != 'aircraft_id'}
    with pytest.raises(ContractError, match='EPISODE_IDENTITY_MISSING'):
        build_episode_records([f1, broken])


def test_registry_records_approved_max_gap_360_parameter():
    rule = current_transformation_registry().get('SAME_AIRCRAFT_AIRPORT_GAP', '1.0.0')
    assert rule.status is TransformationStatus.FROZEN
    assert rule.adjacency_rule == 'POSITIVE_GAP_WITHIN_MAX_360_MINUTES'
    assert 'WITH_MAX_GAP_360' in rule.formula_or_algorithm
