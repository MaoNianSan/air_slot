from model.M3.contracts import CandidateAction
from model.M4.decision import evaluate_decision
from model.M4.response import response_value
from model.common.errors import ContractError
import pytest

def candidate(cid,template,lane_basis="FORMAL",mitigation=.0,induced=.0):
    return CandidateAction(candidate_action_id=cid,template_id=template,action_family="null",parameters={},precondition_state="TRUE",authority_capabilities=(),mitigation={"F_execution":mitigation},induced={"F_execution":induced},response_model="DETERMINISTIC",response_parameters={"value":1},response_provenance="OPERATOR_INDUSTRY" if lane_basis=="FORMAL" else "PURE_SCENARIO",coverage="FULL",preparation_time_minutes=0,deadline_semantics="scenario_deadline")

def test_a00_identity_formal_ranking_prefixes_and_no_scenario_backfill():
    m1=[{"scenario_id":0,"scenario_weight":.5,"deadline_minutes":10},{"scenario_id":1,"scenario_weight":.5,"deadline_minutes":20}]
    m2=[{"scenario_id":0,"components":{"F_execution":10.0}},{"scenario_id":1,"components":{"F_execution":30.0}}]
    result=evaluate_decision("e",m1,m2,[candidate("A00:e","A00"),candidate("A11:e","A11",mitigation=.5),candidate("A13:e","A13",lane_basis="SCENARIO",mitigation=.9)],lambda_risk=.25,alpha=.9,seed=1)
    a00=next(x for x in result.actions if x.template_id=="A00")
    assert a00.post_totals==(10.0,30.0)
    assert result.ranking_at_1=="A11:e" and result.ranking_at_2==( "A11:e", "A00:e")
    assert result.ranking_at_3 is None and all(x.template_id!="A13" or x.lane=="SCENARIO" for x in result.actions)


def test_unfrozen_action_response_parameters_do_not_receive_hidden_defaults():
    action=candidate("A11:e","A11",lane_basis="SCENARIO")
    action=action.model_copy(update={"response_model":"BERNOULLI_BETA","response_parameters":{}})
    with pytest.raises(ContractError,match="ACTION_RESPONSE_PARAMETERS_NOT_FROZEN"):
        response_value(action,seed=1,episode="e",scenario=0,component="F_execution")


def test_closed_opportunity_has_no_induced_consequence():
    action=candidate("A11:e","A11",mitigation=0,induced=7).model_copy(update={"preparation_time_minutes":10})
    result=evaluate_decision("e",[{"scenario_id":0,"scenario_weight":1,"deadline_minutes":5}],
        [{"scenario_id":0,"components":{"F_execution":10.0}}],[candidate("A00:e","A00"),action])
    evaluated=next(item for item in result.actions if item.template_id=="A11")
    assert evaluated.lane=="EXCLUDED" and evaluated.post_totals==(10.0,)
