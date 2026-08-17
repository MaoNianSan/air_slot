from tests.fixtures.pre.foundation_cases import build_data1_case


def test_fixture_pre_state_partially_publishes_with_explicit_support():
    result = build_data1_case()
    state = result.pre_state
    assert state.decision_node.status == "CONSTRUCTED"
    assert state.predecessor_state["motion"].value == 0
    assert len(state.evidence_ledger) == len(state.variable_lineage) == 2
    assert [target.target_name for target in state.target_support] == ["R_IB", "DELTA_OB", "T_TX"]
    assert result.FIXTURE_ONLY and not result.paper_result
    assert result.evaluation_scope == "FOUNDATION_ONLY"
