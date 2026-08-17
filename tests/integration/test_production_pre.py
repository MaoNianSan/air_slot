from datetime import datetime, timezone

from model.PRE.canonical.normalization import canonicalize_metar_row, canonicalize_ontime_row
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre


UTC = timezone.utc


def _publish(dataset, records, cutoff):
    return publish_production_pre(ProductionPRERequest(episode_id="e", predecessor_id="p",
        successor_id="s", dataset_instance_id=dataset, decision_time=cutoff,
        information_cutoff=cutoff, records=tuple(records), config_hash="sha256:c",
        registry_hash="sha256:r"))


def _ontime_row(**updates):
    row = {"FlightDate":"2019-01-01", "Reporting_Airline":"AA", "Tail_Number":"N1",
        "Flight_Number_Reporting_Airline":"10", "Origin":"JFK", "Dest":"LAX",
        "CRSDepTime":"0800", "CRSArrTime":"1100", "DepTime":"0810", "ArrTime":"1120",
        "WheelsOff":"0825", "WheelsOn":"1105", "TaxiOut":"15", "TaxiIn":"15",
        "DepDelayMinutes":"10", "ArrDelayMinutes":"20",
        "Cancelled":"0", "Diverted":"0"}
    row.update(updates)
    return row


def test_registry_controls_family_evidence_and_explicit_support():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=UTC)
    weather = canonicalize_metar_row({"station":"LSZH", "valid":"2019-01-01 11:50+00:00",
        "tmpf":"32", "dwpf":"23", "drct":"180", "sknt":"10", "gust":"M",
        "mslp":"M", "vsby":"10", "metar":"LSZH 011150Z 18010KT Q1013"},
        replay_lag_minutes=5)
    result = _publish("data1_2019", (weather,), cutoff).pre_state
    assert result.current_state["current_weather"].evidence_class.value == "DERIVED"
    assert "current_weather" not in result.predecessor_state
    assert result.successor_state["schedule_reference"].support_state.value == "ABSTAIN"
    assert result.successor_state["schedule_reference"].reason_code == "NO_SCHEDULE"
    support = {item.target_name:item for item in result.target_support}
    assert not support["DELTA_OB"].active and support["DELTA_OB"].abstention_reason == "TARGET_SEMANTICS_UNSUPPORTED"
    assert result.decision_node.status == "CONSTRUCTED"


def test_data2_actual_changes_cannot_change_decision_time_prestate():
    zones = {"JFK":"America/New_York", "LAX":"America/Los_Angeles"}
    schedule1, outcome1 = canonicalize_ontime_row(_ontime_row(), zones)
    schedule2, outcome2 = canonicalize_ontime_row(_ontime_row(DepTime="1000", ArrTime="1300",
        WheelsOff="1015", WheelsOn="1245", TaxiOut="30", TaxiIn="20"), zones)
    assert schedule1 == schedule2 and outcome1 != outcome2
    cutoff = datetime(2019, 1, 1, 13, tzinfo=UTC)
    first = _publish("data2_2019", (schedule1, outcome1), cutoff).pre_state
    second = _publish("data2_2019", (schedule2, outcome2), cutoff).pre_state
    assert first.successor_state == second.successor_state
    assert first.predecessor_state == second.predecessor_state
    assert first.current_state == second.current_state
    assert first.predecessor_state["predecessor_motion"].reason_code == "NO_TRAJECTORY"
    # D2-6/D2-8 sync: data2 weather is a registered inference evidence source
    # (D2-NOAA-ISD, DIRECT); with no legal record at this decision time the
    # mapping abstains per the missing-record rule (NO_WEATHER was the
    # pre-D2-6 "whole scientific object unsupported" code).
    weather = first.current_state["current_weather"]
    assert weather.reason_code == "NO_LEGAL_RECORD_AT_DECISION_TIME"
    assert weather.support_state.value == "ABSTAIN"
    assert all(item.rule_id != "D2-BTS-ACTUAL" for item in first.variable_lineage)
