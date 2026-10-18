from tests.fixtures.pre.foundation_cases import build_data1_case
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from model.PRE.contracts.pre_state import DecisionNodeRecord


def test_object_abstain_does_not_abstain_decision_node():
    result = build_data1_case()
    assert result.pre_state.decision_node.status == "CONSTRUCTED"
    assert result.pre_state.target_support[0].support_state.value == "SUPPORTED"
    assert result.pre_state.target_support[1].support_state.value == "ABSTAIN"
    assert result.pre_state.target_support[2].support_state.value == "SUPPORTED"


def test_node_abstained_requires_node_level_reason_and_ineligibility():
    common = dict(decision_node_id="n", episode_id="e", decision_time=datetime.now(timezone.utc),
        information_cutoff=datetime.now(timezone.utc), operational_stage="PRE_IB", roll_minutes=5,
        node_index=0, status="ABSTAINED", config_hash="sha256:a",
        registry_manifest_hash="sha256:b", legal_record_ids=())
    with pytest.raises(ValidationError): DecisionNodeRecord(**common, formal_eligible=True)
    valid = DecisionNodeRecord(**common, formal_eligible=False,
        node_invalidation_reason="CRITICAL_EPISODE_IDENTITY_FAILURE")
    assert valid.status == "ABSTAINED"
