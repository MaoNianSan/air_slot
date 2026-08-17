from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from model.PRE.contracts.canonical import WeatherObservation
from model.PRE.contracts.pre_state import DecisionNodeRecord, TargetSupportState


UTC = timezone.utc


def test_weather_contract_rejects_raw_names_and_is_immutable():
    with pytest.raises(ValidationError):
        WeatherObservation.model_validate({"canonical_record_id": "x", "dataset_instance_id": "data1_2019",
            "event_time": datetime.now(UTC), "availability_time": datetime.now(UTC),
            "availability_basis": "REPLAY_EVENT_TIME", "provenance_rule_id": "D1-METAR",
            "tmpf": 30})


def test_node_and_object_abstention_are_separate():
    now = datetime.now(UTC)
    node = DecisionNodeRecord(decision_node_id="n", episode_id="e", decision_time=now,
        information_cutoff=now, operational_stage="PRE_IB", roll_minutes=5,
        node_index=0, status="CONSTRUCTED", formal_eligible=True, config_hash="sha256:a",
        registry_manifest_hash="sha256:b", legal_record_ids=())
    target = TargetSupportState(target_name="DELTA_OB", active=False, support_state="ABSTAIN",
        target_definition_id="DELTA_OB_V1", dataset_ceiling="UNSUPPORTED",
        formal_input_support="UNSUPPORTED", realized_outcome_support="DERIVED",
        abstention_reason="TARGET_SEMANTICS_UNSUPPORTED")
    assert node.status == "CONSTRUCTED" and target.support_state.value == "ABSTAIN"
