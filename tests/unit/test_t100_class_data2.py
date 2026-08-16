from pathlib import Path

from model.PRE.canonical.normalization import canonicalize_aggregate_row
from model.PRE.feature_registry.loader import load_registry_bundle
from model.common.enums import DecisionTimeRole

D1_RULE_IDS = {
    "D1-OPENSKY-STATE", "D1-OPENSKY-FLIGHT", "D1-OPENSKY-FLIGHT-EVENT",
    "D1-TRAJECTORY-EVENT", "D1-METAR", "D1-EUROSTAT", "D1-OURAIRPORTS",
}


def t100_row(*, passengers=100, seats=120, aircraft_type=614, service_class="F",
             origin="ATL", dest="ORD", year="2019", month="1"):
    row = {
        "ORIGIN": origin, "DEST": dest, "PASSENGERS": passengers, "SEATS": seats,
        "AIRCRAFT_TYPE": aircraft_type, "YEAR": year, "MONTH": month,
    }
    if service_class is not None:
        row["CLASS"] = service_class
    return row


def canonical(*, service_class="F", **kwargs):
    return canonicalize_aggregate_row(
        t100_row(service_class=service_class, **kwargs),
        dataset_instance_id="data2_2019",
        source_family="bts_t100",
    )


def test_service_class_values_preserved_for_official_codes():
    for code in ("F", "L", "G", "P"):
        ref = canonical(service_class=code)
        assert ref.value["service_class"] == code
        assert ref.value["passengers"] == 100
        assert ref.value["seats"] == 120


def test_missing_or_blank_class_is_explicit_none():
    assert canonical(service_class=None).value["service_class"] is None
    assert canonical(service_class="").value["service_class"] is None
    assert canonical(service_class="   ").value["service_class"] is None


def test_record_metadata_unchanged():
    ref = canonical()
    assert ref.canonical_object_type == "AggregateReference"
    assert ref.grain == "origin_destination_period"
    assert ref.reference_period == "2019-01"
    assert ref.decision_time_role == DecisionTimeRole.FROZEN_REFERENCE
    assert ref.provenance_rule_id == "D2-T100"
    assert ref.provenance.rule_id == "D2-T100"
    assert ref.dataset_instance_id == "data2_2019"


def test_db1b_path_unaffected_by_class():
    ref = canonicalize_aggregate_row(
        {"ORIGIN": "ATL", "DEST": "ORD", "PASSENGERS": 10, "CLASS": "F"},
        dataset_instance_id="data2_2019",
        source_family="bts_db1b",
    )
    assert ref.value == 10
    assert ref.provenance_rule_id == "D2-DB1B"


def test_registry_d1_entries_unchanged_and_d2_class_rule_registered():
    bundle = load_registry_bundle(Path("registries"))
    rules = bundle.data_usage_rules
    d1_ids = {rule.rule_id for rule in rules if rule.dataset_id == "data1_2019"}
    assert d1_ids == D1_RULE_IDS
    d2_ids = [rule.rule_id for rule in rules if rule.dataset_id == "data2_2019"]
    assert len(d2_ids) == 19
    class_rule = next(rule for rule in rules if rule.rule_id == "D2-T100-CLASS")
    assert "CLASS" in class_rule.raw_columns
    assert "M2" in class_rule.downstream_consumers
    assert "M3" in class_rule.downstream_consumers
    assert "EVALUATION_ONLY" in class_rule.downstream_consumers
    assert "PRE" not in class_rule.downstream_consumers
    assert "M1" not in class_rule.downstream_consumers
    assert class_rule.external_evidence_rule_ids == ("D2-T100",)
    assert class_rule.freeze_state.value == "FROZEN"
    assert class_rule.semantic_status == "DOCUMENTED"
    t100 = next(rule for rule in rules if rule.rule_id == "D2-T100")
    assert "CLASS" not in t100.raw_columns
    assert t100.semantic_status == "AIRCRAFT_TYPE_UNVERIFIED"
    assert t100.freeze_state.value == "DEVELOPMENT_FROZEN"
