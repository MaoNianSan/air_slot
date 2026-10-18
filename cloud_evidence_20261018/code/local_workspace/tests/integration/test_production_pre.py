from datetime import datetime, timezone, timedelta
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre


def test_production_pre_filters_future_and_publishes_lineage():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=timezone.utc)
    records = ({"canonical_record_id":"legal", "scientific_variable":"weather", "value":0,
        "unit":"degC", "event_time":cutoff-timedelta(minutes=10), "availability_time":cutoff-timedelta(minutes=5),
        "availability_basis":"REPLAY_EVENT_TIME", "provenance_rule_id":"D1-METAR", "source_path":"a",
        "evidence_class":"DIRECT", "support_ceiling":"DIRECT", "episode_member":True},
        {"canonical_record_id":"future", "scientific_variable":"weather", "value":1,
        "unit":"degC", "event_time":cutoff+timedelta(minutes=1), "availability_time":cutoff+timedelta(minutes=1),
        "availability_basis":"REPLAY_EVENT_TIME", "provenance_rule_id":"D1-METAR", "source_path":"a",
        "evidence_class":"DIRECT", "support_ceiling":"DIRECT", "episode_member":True})
    result = publish_production_pre(ProductionPRERequest(episode_id="e", predecessor_id="p", successor_id="s",
        dataset_instance_id="data1_2019", decision_time=cutoff, information_cutoff=cutoff,
        records=records, config_hash="sha256:c", registry_hash="sha256:r"))
    assert result.pre_state.decision_node.legal_record_ids == ("legal",)
    assert len(result.pre_state.evidence_ledger) == len(result.pre_state.variable_lineage) == 1
    assert result.pre_state.current_state["weather"].value == 0
    support={item.target_name:item.support_state.value for item in result.pre_state.target_support}
    assert support=={"R_IB":"SUPPORTED","R_OB":"ABSTAIN","T_TX":"SUPPORTED"}
    assert result.pre_state.decision_node.status=="CONSTRUCTED"
