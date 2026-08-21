from datetime import datetime, timedelta, timezone

import pytest
import torch

from model.common.errors import ContractError
from model.common.enums import SupportState
from model.M1.data import (E_NAMES_V2, FEATURE_NAMES_V2, GROUP_SLICES_V2,
                           M1NormalizationArtifact, NormalizationValue,
                           encode_pre_sequence, fit_train_normalization)
from model.M1.target_builder import build_v2_target_labels
from model.M1.pipeline import M1Pipeline
from model.common.config import ScientificConfig, load_config_layers
from model.PRE.canonical.normalization import canonicalize_airport_row, canonicalize_ontime_row
from model.PRE.contracts.pre_state import EpisodeRecord
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre


UTC = timezone.utc
ZONES = {"JFK":"America/New_York", "LAX":"America/Los_Angeles"}


def _row(**updates):
    row = {"FlightDate":"2019-01-05", "Reporting_Airline":"AA", "Tail_Number":"N1",
        "Flight_Number_Reporting_Airline":"10", "Origin":"JFK", "Dest":"LAX",
        "CRSDepTime":"0800", "CRSArrTime":"1100", "DepTime":"0905", "ArrTime":"1230",
        "WheelsOff":"0920", "WheelsOn":"1215", "TaxiOut":"15", "TaxiIn":"15",
        "DepDelay":"65", "ArrDelay":"90",
        "DepDelayMinutes":"65", "ArrDelayMinutes":"90", "Cancelled":"0", "Diverted":"0"}
    row.update(updates)
    return row


def _normalization():
    return M1NormalizationArtifact(fitted_split="train",
        values={name: NormalizationValue(mean=0, std=1)
                for name in __import__("model.M1.data", fromlist=["NORMALIZED_NAMES_V2"]).NORMALIZED_NAMES_V2})


def test_multiday_data2_actual_timestamp_uses_posthoc_date_offset():
    schedule, outcome = canonicalize_ontime_row(_row(DepTime="0905", ArrTime="1218",
        DepDelay="1505", ArrDelay="1518",
        DepDelayMinutes="1505", ArrDelayMinutes="1518"), ZONES)
    assert outcome.actual_departure_utc == schedule.scheduled_departure_utc + timedelta(minutes=1505)
    assert outcome.actual_arrival_utc == schedule.scheduled_arrival_utc + timedelta(minutes=1518)
    assert outcome.wheels_off_utc == outcome.actual_departure_utc + timedelta(minutes=15)


def test_five_minute_rolling_grid_and_stage_contraction():
    pred_schedule, pred_outcome = canonicalize_ontime_row(_row(
        FlightDate="2019-01-04", Flight_Number_Reporting_Airline="9", Origin="LAX", Dest="JFK",
        CRSDepTime="2200", CRSArrTime="0600", DepTime="2200", ArrTime="0630",
        DepDelayMinutes="0", ArrDelayMinutes="30"), ZONES)
    succ_schedule, succ_outcome = canonicalize_ontime_row(_row(), ZONES)
    episode = EpisodeRecord(episode_id="e", dataset_instance_id="data2_2019",
        predecessor_flight_id=pred_schedule.flight_id, successor_flight_id=succ_schedule.flight_id,
        aircraft_id="N1", aircraft_id_namespace="REGISTRATION", connection_airport_id="JFK",
        episode_start_time=pred_schedule.scheduled_arrival_utc - timedelta(minutes=5),
        episode_end_time=succ_outcome.wheels_off_utc + timedelta(minutes=5),
        chain_rule_id="TEST", lineage_support=SupportState.SUPPORTED, formal_eligible=True)
    nodes = build_rolling_decision_nodes(episode=episode, predecessor_outcome=pred_outcome,
        successor_outcome=succ_outcome, config_hash="sha256:c", registry_hash="sha256:r")
    assert all((b.decision_time-a.decision_time).total_seconds() == 300 for a,b in zip(nodes,nodes[1:]))
    assert [node.node_index for node in nodes] == list(range(len(nodes)))
    stages = [node.operational_stage.value for node in nodes]
    assert stages[0] == "PRE_IB" and "POST_IB_PRE_OB" in stages
    assert "POST_OB_PRE_TO" in stages and stages[-1] == "COMPLETED"


def test_keyed_airports_preserve_origin_destination_connection_lineage():
    schedule, _ = canonicalize_ontime_row(_row(), ZONES)
    airports = tuple(canonicalize_airport_row({"ident":ident, "iata_code":iata,
        "latitude_deg":lat, "longitude_deg":lon, "elevation_ft":"10", "type":"large_airport"},
        dataset_instance_id="data2_2019", rule_id="D2-AIRPORT-REFERENCE",
        logical_source="airport_reference") for ident,iata,lat,lon in (
            ("KJFK","JFK","40.6","-73.7"),("KLAX","LAX","33.9","-118.4")))
    pre = publish_production_pre(ProductionPRERequest(episode_id="e", predecessor_id="p",
        successor_id="s", dataset_instance_id="data2_2019", decision_time=schedule.scheduled_departure_utc,
        information_cutoff=schedule.scheduled_departure_utc, records=(schedule,*airports),
        config_hash="sha256:c", registry_hash="sha256:r",
        connection_airport_id="JFK")).pre_state
    keyed = pre.reference_state.entries["airport_reference"].value
    assert keyed.origin.supported_value.value["airport_id"] == "KJFK"
    assert keyed.destination.supported_value.value["airport_id"] == "KLAX"
    assert keyed.connection.supported_value.value["airport_id"] == "KJFK"
    assert {(x.reference_role,x.source_record_id) for x in pre.variable_lineage
            if x.scientific_variable == "airport_reference"} >= {
                ("origin", keyed.origin.source_record_id),
                ("destination", keyed.destination.source_record_id),
                ("connection", keyed.connection.source_record_id)}


def test_typed_features_use_approved_groups_and_ignore_outcomes_ids_and_airports():
    schedule, outcome = canonicalize_ontime_row(_row(), ZONES)
    request = ProductionPRERequest(episode_id="e", predecessor_id="p", successor_id="s",
        dataset_instance_id="data2_2019", decision_time=schedule.scheduled_departure_utc,
        information_cutoff=schedule.scheduled_departure_utc, records=(schedule,outcome),
        config_hash="sha256:c", registry_hash="sha256:r")
    first = publish_production_pre(request).pre_state
    changed_schedule, changed_outcome = canonicalize_ontime_row(_row(
        DepDelayMinutes="120", ArrDelayMinutes="180", TaxiOut="40"), ZONES)
    second = publish_production_pre(request.model_copy(update={"records":(changed_schedule,changed_outcome)})).pre_state
    a=encode_pre_sequence([first],_normalization());b=encode_pre_sequence([second],_normalization())
    assert a.shape == (1,len(FEATURE_NAMES_V2)) and torch.equal(a,b)
    assert all("airport" not in name and "flight_id" not in name and "dataset" not in name
               for name in FEATURE_NAMES_V2)
    e=a[0,GROUP_SLICES_V2["E"]]
    assert e.shape[0] == len(E_NAMES_V2)


def test_train_only_normalization_and_typed_labels_preserve_identity_and_split():
    with pytest.raises(ContractError,match="TRAIN_ONLY"):
        fit_train_normalization([],split="development")
    pred_schedule,pred_outcome=canonicalize_ontime_row(_row(
        Flight_Number_Reporting_Airline="9",CRSArrTime="0700",ArrTime="0730",
        ArrDelayMinutes="30"),ZONES)
    succ_schedule,succ_outcome=canonicalize_ontime_row(_row(),ZONES)
    episode=EpisodeRecord(episode_id="e",dataset_instance_id="data2_2019",
        predecessor_flight_id=pred_schedule.flight_id,successor_flight_id=succ_schedule.flight_id,
        aircraft_id="N1",aircraft_id_namespace="REGISTRATION",connection_airport_id="JFK",
        episode_start_time=pred_schedule.scheduled_arrival_utc,
        episode_end_time=succ_schedule.scheduled_arrival_utc,chain_rule_id="TEST",
        lineage_support=SupportState.SUPPORTED,formal_eligible=True)
    node=build_rolling_decision_nodes(episode=episode,predecessor_outcome=pred_outcome,
        successor_outcome=succ_outcome,config_hash="sha256:c",registry_hash="sha256:r")[0]
    pre=publish_production_pre(ProductionPRERequest(episode_id="e",predecessor_id=episode.predecessor_flight_id,
        successor_id=episode.successor_flight_id,dataset_instance_id="data2_2019",
        decision_time=node.decision_time,information_cutoff=node.information_cutoff,records=(succ_schedule,),
        config_hash="sha256:c",registry_hash="sha256:r")).pre_state
    labels=build_v2_target_labels(episode=episode,node=node,predecessor_outcome=pred_outcome,
        successor_schedule=succ_schedule,successor_outcome=succ_outcome,target_support=pre.target_support,
        taxi_reference_minutes=0.0,taxi_reference_id="DATA2_TAXI_REFERENCE@1.0.0",
        taxi_reference_hash="sha256:reference")
    assert {x.target_name for x in labels} == {"T_IB_REMAINING_HAZARD","D_OB","D_TX"}
    assert all(x.episode_id == "e" and x.split == "train" and x.provenance for x in labels)
    assert {x.target_name:x.exact_minutes for x in labels} == {
        "T_IB_REMAINING_HAZARD":30.0,"D_OB":65.0,"D_TX":15.0}


def test_formal_pipeline_uses_frozen_target_supports():
    scientific=load_config_layers(__import__("pathlib").Path("configs")).scientific
    pipeline=M1Pipeline.from_scientific_config(scientific,input_size=len(FEATURE_NAMES_V2),
                                               normalization=_normalization(), hidden_size=16)
    assert {name:item.max_finite_minutes for name,item in pipeline.bins.items()} == {
        "T_IB_REMAINING_HAZARD":360,"D_OB":180,"D_TX":60}
    for target, finite, overflow in (("T_IB_REMAINING_HAZARD",360,365),("D_OB",180,185),("D_TX",60,65)):
        bins=pipeline.bins[target]
        assert bins.encode(finite-0.001) == bins.class_count-2
        assert bins.encode(finite) == bins.class_count-1
        assert bins.encode(overflow) == bins.class_count-1
        assert bins.encode(overflow+10_000) == bins.class_count-1
    # Formal D_OB / D_TX supports are nonnegative; signed DELTA_OB is legacy.
    for target in ("D_OB", "D_TX"):
        with pytest.raises(ValueError, match="nonnegative"):
            pipeline.bins[target].encode(-1)


def test_output_support_change_cannot_change_full_input_history():
    schedule, _ = canonicalize_ontime_row(_row(), ZONES)
    states=[]
    for index in range(3):
        decision_time=schedule.scheduled_departure_utc+timedelta(minutes=5*index)
        states.append(publish_production_pre(ProductionPRERequest(episode_id="history-e",
            predecessor_id="p",successor_id="s",dataset_instance_id="data2_2019",
            decision_time=decision_time,information_cutoff=decision_time,records=(schedule,),
            config_hash="sha256:c",registry_hash="sha256:r",node_index=index)).pre_state)
    normalization=_normalization()
    encoded_a=encode_pre_sequence(states,normalization)
    encoded_b=encode_pre_sequence(states,normalization)
    base=load_config_layers(__import__("pathlib").Path("configs")).scientific
    alternate=ScientificConfig.model_validate({"schema_version":base.schema_version,
        "parameters":{name:item.model_dump() for name,item in base.parameters.items()}})
    replacements={"m1_r_ib_max_finite_minutes":480,
                  "m1_delta_ob_max_finite_minutes":240,
                  "m1_t_tx_max_finite_minutes":90}
    alternate=alternate.model_copy(update={"parameters":{
        name:(item.model_copy(update={"value":replacements[name]}) if name in replacements else item)
        for name,item in alternate.parameters.items()}})
    pipeline_a=M1Pipeline.from_scientific_config(base,input_size=len(FEATURE_NAMES_V2),normalization=normalization, hidden_size=16)
    pipeline_b=M1Pipeline.from_scientific_config(alternate,input_size=len(FEATURE_NAMES_V2),normalization=normalization, hidden_size=16)
    assert torch.equal(encoded_a,encoded_b)
    assert [state.decision_node.decision_time for state in states] == [
        schedule.scheduled_departure_utc+timedelta(minutes=5*i) for i in range(3)]
    assert encoded_a.shape[0] == 3
    assert {name:head.class_count for name,head in pipeline_a.bins.items()} != {
        name:head.class_count for name,head in pipeline_b.bins.items()}
    assert pipeline_a.bins["T_IB_REMAINING_HAZARD"].class_count != pipeline_b.bins["T_IB_REMAINING_HAZARD"].class_count
    assert pipeline_a.bins["D_OB"].class_count != pipeline_b.bins["D_OB"].class_count
    assert pipeline_a.bins["D_TX"].class_count != pipeline_b.bins["D_TX"].class_count
    assert pipeline_a.bins["D_OB"].encode(0) == 0


def test_history_prefix_rejects_omission_and_wrong_grid():
    schedule, _ = canonicalize_ontime_row(_row(), ZONES)
    def state(index, minutes):
        decision=schedule.scheduled_departure_utc+timedelta(minutes=minutes)
        return publish_production_pre(ProductionPRERequest(episode_id="history-e",
            predecessor_id="p",successor_id="s",dataset_instance_id="data2_2019",
            decision_time=decision,information_cutoff=decision,records=(schedule,),
            config_hash="sha256:c",registry_hash="sha256:r",node_index=index)).pre_state
    with pytest.raises(ContractError,match="START_AT_NODE_ZERO"):
        encode_pre_sequence([state(1,5)],_normalization())
    with pytest.raises(ContractError,match="NONCONTIGUOUS_DECISION_TIME"):
        encode_pre_sequence([state(0,0),state(1,10)],_normalization())
