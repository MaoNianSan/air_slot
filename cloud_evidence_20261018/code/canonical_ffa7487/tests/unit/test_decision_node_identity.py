from tests.fixtures.pre.foundation_cases import build_request
from model.PRE.foundation import build_pre_state


def test_node_identity_is_deterministic_and_later_evidence_is_non_retrospective():
    request = build_request()
    first = build_pre_state(request)
    second = build_pre_state(request)
    assert first.pre_state.decision_node.decision_node_id == second.pre_state.decision_node.decision_node_id
    assert first.pre_state == second.pre_state
