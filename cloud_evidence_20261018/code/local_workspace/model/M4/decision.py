from typing import Any
from model.common.value_objects import FrozenModel
from model.common.errors import ContractError
from .lanes import assign_lane
from .response import response_value
from .risk import weighted_mean,weighted_var_cvar
from .contracts import M4DecisionRequest

class ActionEvaluation(FrozenModel):
    candidate_action_id:str;template_id:str;lane:str;opportunity_probability:float
    expected_residual:float;var:float;cvar:float;residual_risk_j:float;post_totals:tuple[float,...]
    ranking_position:int|None=None

class EpisodeDecision(FrozenModel):
    episode_id:str;actions:tuple[ActionEvaluation,...];decision_outcome:str
    authoritative_ranking:tuple[str,...];ranking_at_1:str|None;ranking_at_2:tuple[str,...]|None
    ranking_at_3:tuple[str,...]|None;ranking_at_5:tuple[str,...]|None

def evaluate_decision(episode_id,m1_scenarios,m2_consequences,candidates,*,lambda_risk=.25,alpha=.9,seed=0):
    by_s={row["scenario_id"]:row for row in m2_consequences};evaluations=[]
    for candidate in candidates:
        if candidate.template_id=="A00":opportunities=[1.0 for _ in m1_scenarios]
        else:
            scalar=candidate.parameters.get("deadline_minutes")
            by_scenario=candidate.parameters.get("deadline_minutes_by_scenario",{})
            deadlines=[s.get("deadline_minutes",by_scenario.get(str(s["scenario_id"]),by_scenario.get(s["scenario_id"],scalar))) for s in m1_scenarios]
            if any(value is None for value in deadlines):raise ContractError("ACTION_DEADLINE_UNRESOLVED")
            opportunities=[1.0 if float(value)>candidate.preparation_time_minutes else 0.0 for value in deadlines]
        weights=[float(s["scenario_weight"]) for s in m1_scenarios];opp=weighted_mean(opportunities,weights)
        post=[]
        for scenario,open_ in zip(m1_scenarios,opportunities):
            components=by_s[scenario["scenario_id"]]["components"]
            total=0.0
            for component,pre in components.items():
                if candidate.template_id=="A00":value=float(pre)
                else:
                    response=response_value(candidate,seed=seed,episode=episode_id,scenario=scenario["scenario_id"])
                    reduction=float(candidate.mitigation.get(component,0))*response if open_ else 0
                    induced=(float(candidate.induced.get(component,0))+response*float(candidate.induced_response.get(component,0))) if open_ else 0
                    value=(1-reduction)*float(pre)+induced
                total+=value
            post.append(total)
        mean=weighted_mean(post,weights);var,cvar=weighted_var_cvar(post,weights,alpha);risk=(1-lambda_risk)*mean+lambda_risk*cvar
        evaluations.append(ActionEvaluation(candidate_action_id=candidate.candidate_action_id,template_id=candidate.template_id,
            lane=assign_lane(candidate,opp),opportunity_probability=opp,expected_residual=mean,var=var,cvar=cvar,residual_risk_j=risk,post_totals=tuple(post)))
    formal=sorted([x for x in evaluations if x.lane=="FORMAL"],key=lambda x:(x.residual_risk_j,x.template_id))
    ranks={x.candidate_action_id:i+1 for i,x in enumerate(formal)};evaluations=[x.model_copy(update={"ranking_position":ranks.get(x.candidate_action_id)}) for x in evaluations]
    ranking=tuple(x.candidate_action_id for x in formal);a00=next((x for x in formal if x.template_id=="A00"),None)
    outcome="NO_AUTHORITATIVE_DECISION" if not formal else "BASELINE_ONLY_FORMAL" if len(formal)==1 and a00 else "FORMAL_A00_PREFERRED" if formal[0].template_id=="A00" else "FORMAL_ACTION_PREFERRED"
    return EpisodeDecision(episode_id=episode_id,actions=tuple(evaluations),decision_outcome=outcome,authoritative_ranking=ranking,
        ranking_at_1=ranking[0] if ranking else None,ranking_at_2=ranking[:2] if len(ranking)>=2 else None,
        ranking_at_3=ranking[:3] if len(ranking)>=3 else None,ranking_at_5=ranking[:5] if len(ranking)>=5 else None)


def evaluate_request(request: M4DecisionRequest) -> EpisodeDecision:
    support={item.target_name:(item.support_state.value if hasattr(item.support_state,"value") else str(item.support_state))
             for item in request.pre_state.target_support}
    scenarios=[]
    for row in request.m1_scenarios:
        item=row.model_dump(mode="json")
        scenarios.append(item)
    consequences=[]
    for row in request.m2_consequences:
        components={item.component:item.constructed_cu for item in row.components if item.constructed_cu is not None}
        consequences.append({"scenario_id":row.scenario_id,"components":components})
    return evaluate_decision(request.pre_state.decision_node.episode_id,scenarios,consequences,
        request.candidates,lambda_risk=request.lambda_risk,alpha=request.alpha,seed=request.seed)
