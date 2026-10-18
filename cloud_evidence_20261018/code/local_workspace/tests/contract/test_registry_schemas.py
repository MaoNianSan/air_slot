import pytest
from pydantic import ValidationError
from model.PRE.feature_registry.models import DataUsageRule


def test_registry_unknown_keys_rejected():
    payload = {"rule_id":"r", "rule_version":"1.0.0", "freeze_state":"FROZEN",
        "dataset_id":"data1_2019", "logical_source":"metar", "raw_columns":["tmpf"],
        "raw_semantics":"temperature", "raw_unit":"degF", "canonical_object":"WeatherObservation",
        "canonical_variable":"temperature_c", "canonical_unit":"degC", "transformation_rule":"f_to_c",
        "event_time_source":"valid", "availability_rule":"replay", "decision_time_role":"INFERENCE_EVIDENCE",
        "evidence_class":"DIRECT", "support_ceiling":"DIRECT", "missing_rule":"explicit",
        "stale_rule":"development_frozen", "fallback_rule":"none", "pre_family":"current_operational_state",
        "downstream_consumers":["PRE","M1"], "scientific_purpose":"weather", "semantic_status":"DOCUMENTED",
        "confidence":"HIGH", "external_evidence_rule_ids":[], "typo":1}
    with pytest.raises(ValidationError): DataUsageRule.model_validate(payload)


def test_registry_rejects_support_upgrade():
    payload = {"rule_id":"r", "rule_version":"1.0.0", "freeze_state":"FROZEN",
        "dataset_id":"data1_2019", "logical_source":"metar", "raw_columns":["tmpf"],
        "raw_semantics":"temperature", "raw_unit":"degF", "canonical_object":"WeatherObservation",
        "canonical_variable":"temperature_c", "canonical_unit":"degC", "transformation_rule":"f_to_c",
        "event_time_source":"valid", "availability_rule":"replay", "decision_time_role":"INFERENCE_EVIDENCE",
        "evidence_class":"DIRECT", "support_ceiling":"DERIVED", "missing_rule":"explicit",
        "stale_rule":"development_frozen", "fallback_rule":"none", "pre_family":"current_operational_state",
        "downstream_consumers":["PRE","M1"], "scientific_purpose":"weather", "semantic_status":"DOCUMENTED",
        "confidence":"HIGH", "external_evidence_rule_ids":[]}
    with pytest.raises(ValidationError, match="support ceiling"):
        DataUsageRule.model_validate(payload)
