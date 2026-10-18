from datetime import datetime, timezone

from model.M1.contracts import AlignedScenario
from model.M2.contracts import ConsequenceRow, ScenarioConsequence
from model.M3.contracts import CandidateAction
from model.M4.contracts import M4DecisionRequest
from model.M4.decision import evaluate_request
from model.M4.response import response_value
from model.PRE.foundation import PREBuildRequest, build_pre_state


def _candidate(template="A11"):
    return CandidateAction(candidate_action_id=f"{template}:e", template_id=template,
        action_family="timing", parameters={}, precondition_state="TRUE",
        authority_capabilities=(), mitigation={"F_execution": .5}, induced={},
        response_model="BERNOULLI_BETA",
        response_parameters={"failure_probability": 0.0, "mean_intensity": .5, "concentration": 4.0},
        response_provenance="OPERATOR_INDUSTRY", coverage="FULL",
        preparation_time_minutes=0, deadline_semantics="scenario_deadline")


def test_bernoulli_beta_is_stochastic_stable_and_shared_across_components():
    action = _candidate()
    values = [response_value(action, seed=11, episode="e", scenario=s) for s in range(20)]
    assert values == [response_value(action, seed=11, episode="e", scenario=s,
                                     component="P_time") for s in range(20)]
    assert len({round(value, 8) for value in values}) > 1
    assert all(0 < value < 1 for value in values)
    reordered={s:response_value(action,seed=11,episode="e",scenario=s) for s in reversed(range(20))}
    assert reordered=={s:value for s,value in enumerate(values)}


def test_typed_m4_request_preserves_m1_m2_scenario_lineage_and_a00_identity():
    pre = build_pre_state(PREBuildRequest(episode_id="e", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=timezone.utc),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=timezone.utc),
        config_hash="sha256:c", registry_hash="sha256:r", dataset_instance_id="data2_2019")).pre_state
    scenario = AlignedScenario(episode_id="e", decision_node_id=pre.decision_node.decision_node_id,
        scenario_id=0, scenario_weight=1, operational_stage="PRE_IB", r_ib_minutes=5,
        r_ob_minutes=5, t_tx_minutes=5, ib_observed=False, ob_observed=False,
        ib_support="SUPPORTED", ob_support="SUPPORTED", tx_support="SUPPORTED",
        overflow_ib=False, overflow_ob=False, overflow_tx=False, scenario_seed_key="k")
    component = tuple(ConsequenceRow(component=name,
        aspect="Flight" if name.startswith("F_") else "Passenger" if name.startswith("P_") else "Resource",
        native_value=10 if name=="F_execution" else 0,native_unit="unit",driver="d",
        constructed_cu=10 if name=="F_execution" else 0,evidence_class="DERIVED",support="SUPPORTED",
        valuation_rule_id="r",valuation_parameter_version="v") for name in
        ("F_continuity","F_execution","F_propagation","P_time","P_itinerary","P_service","R_operating"))
    consequence = ScenarioConsequence(decision_node_id=pre.decision_node.decision_node_id,
        scenario_id=0, scenario_weight=1, components=component, available_component_sum_cu=10,
        formal_total_cu=10)
    a00 = _candidate("A00").model_copy(update={"action_family":"null", "mitigation":{},
        "response_model":"DETERMINISTIC", "response_parameters":{"value":0.0}})
    request = M4DecisionRequest(pre_state=pre, m1_scenarios=(scenario,),
                                m2_consequences=(consequence,), candidates=(a00,), seed=3)
    result = evaluate_request(request)
    assert result.actions[0].post_totals == (10.0,)
    assert result.ranking_at_1 == "A00:e"
