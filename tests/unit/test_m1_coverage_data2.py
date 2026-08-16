"""D2-9 M1 training coverage (all rolling grid nodes) focused tests.

Covers: registry freeze (transformation + data-usage), data1 / prior D2-*
non-regression, dataset isolation, all-node selection including episodes
without PRE_IB nodes (early arrival under D2-2 anchor B), stage-gated label
activation, and exclusion of all-realized (COMPLETED) nodes.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from model.common.enums import (AvailabilityBasis, DecisionTimeRole, EvidenceClass,
                                OperationalStage, SupportState)
from model.common.errors import ContractError
from model.common.value_objects import ProvenanceRef
from model.M1.coverage import active_node_prefixes, build_all_node_examples
from model.M1.data import FEATURE_NAMES, fit_train_normalization
from model.M1.pipeline import M1Pipeline
from model.PRE.contracts.canonical import FlightRecord, OperationalEventRecord
from model.PRE.contracts.pre_state import PREState, TargetSupportState
from model.PRE.episode.builder import build_data2_episode_chain
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.transformation import TransformationStatus, current_transformation_registry

UTC = timezone.utc


def _prov(rule_id="D2-BTS-ACTUAL", dataset="data2_2019"):
    return ProvenanceRef(dataset_instance_id=dataset, logical_source="bts_ontime",
                         source_record_id="fixture", source_field="*",
                         rule_id=rule_id, source_version="1.0.0")


def _flight_dict(fid, aircraft, origin, dest, crs_dep, crs_arr, actual_arr, actual_dep):
    return {"flight_id": fid, "aircraft_id": aircraft, "aircraft_id_namespace": "REGISTRATION",
            "origin_airport_id": origin, "destination_airport_id": dest,
            "actual_arrival_utc": actual_arr, "actual_departure_utc": actual_dep,
            "event_start_time": crs_dep, "event_end_time": crs_arr,
            "dataset_instance_id": "data2_2019"}


def _outcome(fid, *, arr, dep, wheels_off=None, taxi_out=None, dataset="data2_2019"):
    return OperationalEventRecord(
        canonical_record_id=f"ev:{fid}", dataset_instance_id=dataset,
        availability_basis=AvailabilityBasis.POSTHOC_ONLY,
        decision_time_role=DecisionTimeRole.TRAIN_LABEL,
        provenance_rule_id="D2-BTS-ACTUAL", provenance=_prov(dataset=dataset),
        event_type="GATE_ACTUAL", flight_id=fid,
        actual_arrival_utc=arr, actual_departure_utc=dep,
        wheels_off_utc=wheels_off, taxi_out_minutes=taxi_out,
        cancelled=False, diverted=False)


def _schedule(fid, *, crs_dep, crs_arr, service_date=date(2019, 1, 1)):
    return FlightRecord(
        canonical_record_id=f"fr:{fid}", dataset_instance_id="data2_2019",
        availability_basis=AvailabilityBasis.POSTHOC_ONLY,
        decision_time_role=DecisionTimeRole.FROZEN_REFERENCE,
        provenance_rule_id="D2-BTS-SCHEDULE", provenance=_prov("D2-BTS-SCHEDULE"),
        flight_id=fid, service_date=service_date,
        event_start_time=crs_dep, event_end_time=crs_arr,
        scheduled_departure_utc=crs_dep, scheduled_arrival_utc=crs_arr,
        schedule_semantics="CRS_LOCAL_TO_UTC", source_flight_id=fid,
        aircraft_id="N1", aircraft_id_namespace="REGISTRATION",
        origin_airport_id="B", destination_airport_id="C",
        offline_membership_only=False)


def _target_support():
    return tuple(
        TargetSupportState(target_name=name, active=True,
                           support_state=SupportState.SUPPORTED,
                           target_definition_id=f"{name}_V1",
                           dataset_ceiling=EvidenceClass.DIRECT,
                           formal_input_support=EvidenceClass.DIRECT,
                           realized_outcome_support=EvidenceClass.DIRECT)
        for name in ("R_IB", "R_OB", "T_TX"))


def _scenario(*, pred_actual_arr, succ_crs_dep, succ_crs_arr, succ_actual_dep,
              succ_wheels_off, taxi_out, crs_dep=None, pred_crs_arr=None):
    t0 = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    if crs_dep is None:
        crs_dep = t0
    if pred_crs_arr is None:
        pred_crs_arr = crs_dep + timedelta(minutes=120)
    pred = _flight_dict("p", "N1", "A", "B", crs_dep, pred_crs_arr,
                        pred_actual_arr, crs_dep + timedelta(minutes=55))
    succ = _flight_dict("s", "N1", "B", "C", succ_crs_dep, succ_crs_arr,
                        succ_crs_arr + timedelta(minutes=10), succ_actual_dep)
    episode = build_data2_episode_chain(pred, succ)
    pred_out = _outcome("p", arr=pred_actual_arr, dep=crs_dep + timedelta(minutes=55))
    succ_out = _outcome("s", arr=succ_crs_arr + timedelta(minutes=10),
                        dep=succ_actual_dep, wheels_off=succ_wheels_off,
                        taxi_out=taxi_out)
    nodes = build_rolling_decision_nodes(episode=episode, predecessor_outcome=pred_out,
                                         successor_outcome=succ_out,
                                         config_hash="cfg", registry_hash="reg")
    states = tuple(PREState(decision_node=node, target_support=_target_support())
                   for node in nodes)
    schedule = _schedule("s", crs_dep=succ_crs_dep, crs_arr=succ_crs_arr)
    return episode, nodes, states, schedule, pred_out, succ_out


# ---------------- registry freeze ----------------

def test_coverage_transformation_rule_registered_and_frozen():
    registry = current_transformation_registry()
    rule = registry.get("DATA2_M1_TRAINING_COVERAGE", "1.0.0")
    assert rule.status is TransformationStatus.FROZEN
    formula = rule.formula_or_algorithm
    assert "all rolling grid nodes" in formula
    assert "one M1 training example per node" in formula
    assert "node-level equal weight" in formula
    assert "D2-2 anchors unchanged" in formula
    assert "stage-gated labels" in formula
    assert "no active target" in formula


def test_coverage_data_usage_rule_entry_frozen():
    bundle = load_registry_bundle(Path("registries"))
    rule = {r.rule_id: r for r in bundle.data_usage_rules}["D2-M1-TRAINING-COVERAGE"]
    assert rule.freeze_state.value == "FROZEN"
    assert rule.dataset_id == "data2_2019"
    assert rule.decision_time_role.value == "TRAIN_LABEL"
    assert rule.availability_rule == "posthoc_only"
    assert "M1" in rule.downstream_consumers
    assert rule.transformation_rule == "all_nodes_stage_gated_node_equal_weight"
    assert "D2-LABEL-R-IB" in rule.external_evidence_rule_ids
    assert "D2-LABEL-T-TX" in rule.external_evidence_rule_ids


def test_data1_and_prior_d2_rules_untouched():
    bundle = load_registry_bundle(Path("registries"))
    rules = {r.rule_id: r for r in bundle.data_usage_rules}
    for rid in ("D1-OPENSKY-STATE", "D1-OPENSKY-FLIGHT", "D1-OPENSKY-FLIGHT-EVENT",
                "D1-TRAJECTORY-EVENT", "D1-METAR", "D1-EUROSTAT"):
        assert rules[rid].freeze_state.value == "FROZEN"
        assert rules[rid].dataset_id == "data1_2019"
    for rid in ("D2-CHAIN-GATE-GAP", "D2-LABEL-R-IB", "D2-LABEL-R-OB",
                "D2-LABEL-T-TX", "D2-NOAA-ISD", "D2-PASSENGER-REFERENCE"):
        assert rules[rid].freeze_state.value == "FROZEN"
    registry = current_transformation_registry()
    ib = registry.get("DATA2_LABEL_R_IB", "1.0.0")
    assert "m1_r_ib_max_finite_minutes=360" in ib.formula_or_algorithm


def test_label_builder_rejects_mixed_dataset_outcome():
    t = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    episode, nodes, states, schedule, pred_out, succ_out = _scenario(
        pred_actual_arr=t + timedelta(minutes=100),
        succ_crs_dep=t + timedelta(minutes=180),
        succ_crs_arr=t + timedelta(minutes=240),
        succ_actual_dep=t + timedelta(minutes=195),
        succ_wheels_off=t + timedelta(minutes=202), taxi_out=12.0)
    data1_out = _outcome("s", arr=t + timedelta(minutes=250),
                         dep=t + timedelta(minutes=195), dataset="data1_2019")
    from model.M1.target_builder import build_data2_target_labels
    with pytest.raises(ContractError, match="M1_DATA2_TARGET_BUILDER_DATASET_MISMATCH"):
        build_data2_target_labels(episode=episode, node=nodes[0],
                                  predecessor_outcome=pred_out,
                                  successor_schedule=schedule,
                                  successor_outcome=data1_out,
                                  target_support=states[0].target_support)


# ---------------- all-node selection semantics ----------------

def test_early_arrival_episode_without_pre_ib_still_contributes_nodes():
    t = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    episode, nodes, states, schedule, pred_out, succ_out = _scenario(
        pred_actual_arr=t + timedelta(minutes=100),   # early: actual < CRSArr (14:00)
        succ_crs_dep=t + timedelta(minutes=180),
        succ_crs_arr=t + timedelta(minutes=240),
        succ_actual_dep=t + timedelta(minutes=195),
        succ_wheels_off=t + timedelta(minutes=202), taxi_out=12.0)
    assert all(node.operational_stage is not OperationalStage.PRE_IB for node in nodes)
    assert nodes[0].operational_stage is OperationalStage.POST_IB_PRE_OB
    prefixes = list(active_node_prefixes(
        episode=episode, nodes=nodes, states=states,
        successor_schedule=schedule, predecessor_outcome=pred_out,
        successor_outcome=succ_out))
    assert len(prefixes) == len(nodes)          # every node still contributes
    first_node, first_prefix, first_labels = prefixes[0]
    assert first_node.operational_stage is OperationalStage.POST_IB_PRE_OB
    by_name = {label.target_name: label for label in first_labels}
    assert by_name["R_IB"].active is False       # already realized at this stage
    assert by_name["R_IB"].abstention_reason == "TARGET_OBSERVED_AT_STAGE"
    assert by_name["R_OB"].active is True
    assert by_name["T_TX"].active is True


def test_late_arrival_episode_keeps_pre_ib_nodes():
    t = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    episode, nodes, states, schedule, pred_out, succ_out = _scenario(
        pred_actual_arr=t + timedelta(minutes=140),  # late: actual > CRSArr (14:00)
        succ_crs_dep=t + timedelta(minutes=240),
        succ_crs_arr=t + timedelta(minutes=300),
        succ_actual_dep=t + timedelta(minutes=250),
        succ_wheels_off=t + timedelta(minutes=258), taxi_out=10.0)
    assert any(node.operational_stage is OperationalStage.PRE_IB for node in nodes)
    prefixes = list(active_node_prefixes(
        episode=episode, nodes=nodes, states=states,
        successor_schedule=schedule, predecessor_outcome=pred_out,
        successor_outcome=succ_out))
    assert len(prefixes) == len(nodes)
    assert prefixes[0][0].operational_stage is OperationalStage.PRE_IB
    by_name = {label.target_name: label for label in prefixes[0][2]}
    assert by_name["R_IB"].active is True
    assert by_name["R_OB"].active is True
    assert by_name["T_TX"].active is True


def test_completed_nodes_with_no_active_target_are_excluded():
    t = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    episode, nodes, states, schedule, pred_out, succ_out = _scenario(
        pred_actual_arr=t + timedelta(minutes=100),   # early
        succ_crs_dep=t + timedelta(minutes=180),
        succ_crs_arr=t + timedelta(minutes=240),
        succ_actual_dep=t + timedelta(minutes=150),   # departs before CRSDep
        succ_wheels_off=t + timedelta(minutes=160), taxi_out=8.0)
    assert any(node.operational_stage is OperationalStage.COMPLETED for node in nodes)
    prefixes = list(active_node_prefixes(
        episode=episode, nodes=nodes, states=states,
        successor_schedule=schedule, predecessor_outcome=pred_out,
        successor_outcome=succ_out))
    assert len(prefixes) < len(nodes)
    assert all(node.operational_stage is not OperationalStage.COMPLETED
               for node, _, _ in prefixes)
    stages = {node.operational_stage for node, _, _ in prefixes}
    assert OperationalStage.POST_OB_PRE_TO in stages


def test_build_all_node_examples_one_example_per_node_in_order():
    t = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    episode, nodes, states, schedule, pred_out, succ_out = _scenario(
        pred_actual_arr=t + timedelta(minutes=100),
        succ_crs_dep=t + timedelta(minutes=180),
        succ_crs_arr=t + timedelta(minutes=240),
        succ_actual_dep=t + timedelta(minutes=195),
        succ_wheels_off=t + timedelta(minutes=202), taxi_out=12.0)
    normalization = fit_train_normalization([], split="train")
    pipeline = M1Pipeline.smoke(input_size=len(FEATURE_NAMES))
    examples = build_all_node_examples(
        episode=episode, nodes=nodes, states=states,
        successor_schedule=schedule, predecessor_outcome=pred_out,
        successor_outcome=succ_out, normalization=normalization,
        bins=pipeline.bins)
    assert len(examples) == len(nodes)
    for index, example in enumerate(examples):
        assert example.values.shape[0] == index + 1     # full prefix per node
        assert example.episode_id == episode.episode_id
    assert examples[0].active == {"R_IB": False, "R_OB": True, "T_TX": True}
    assert examples[-1].active == {"R_IB": False, "R_OB": True, "T_TX": True}


def test_nodes_states_length_mismatch_rejected():
    t = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)
    episode, nodes, states, schedule, pred_out, succ_out = _scenario(
        pred_actual_arr=t + timedelta(minutes=100),
        succ_crs_dep=t + timedelta(minutes=180),
        succ_crs_arr=t + timedelta(minutes=240),
        succ_actual_dep=t + timedelta(minutes=195),
        succ_wheels_off=t + timedelta(minutes=202), taxi_out=12.0)
    with pytest.raises(ValueError, match="M1_COVERAGE_NODES_STATES_LENGTH_MISMATCH"):
        list(active_node_prefixes(
            episode=episode, nodes=nodes[:-1], states=states,
            successor_schedule=schedule, predecessor_outcome=pred_out,
            successor_outcome=succ_out))
