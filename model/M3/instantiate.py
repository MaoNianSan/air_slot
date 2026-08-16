from model.common.identity import content_id
from .contracts import CandidateAction

def instantiate_candidates(pre_state:dict,registry):
    if not isinstance(pre_state,dict):
        values={**pre_state.predecessor_state,**pre_state.current_state,**pre_state.successor_state,
                **pre_state.reference_state.entries}
        facts={name:(None if str(value.support_state.value)=="ABSTAIN" else bool(value.value)) for name,value in values.items()}
        episode_parameters={name:(None if str(value.support_state.value)=="ABSTAIN" else value.value) for name,value in values.items()}
        episode_id=pre_state.decision_node.episode_id;decision_node_id=pre_state.decision_node.decision_node_id
    else:
        facts=pre_state.get("facts",{});episode_parameters=pre_state.get("parameters",{})
        episode_id=pre_state["episode_id"];decision_node_id=pre_state["decision_node_id"]
    candidates=[]
    for action_index,template in enumerate(registry.templates):
        states=[facts.get(name) for name in template.required_facts]
        parameter_values={name:episode_parameters.get(name) for name in template.required_parameters}
        states.extend(None for value in parameter_values.values() if value is None)
        precondition="FALSE" if any(value is False for value in states) else "UNKNOWN" if any(value is None for value in states) else "TRUE"
        if precondition=="FALSE":continue
        parameters={"episode_id":episode_id,"decision_node_id":decision_node_id,**parameter_values}
        stable_parameters={name:value for name,value in parameters.items() if name!="decision_node_id"}
        identity=content_id({"template":template.template_id,"parameters":stable_parameters,"registry":registry.schema_version})
        candidates.append(CandidateAction(candidate_action_id=f"{template.template_id}:{identity.split(':')[1][:16]}",
            template_id=template.template_id,action_family=template.family,action_index=action_index,
            candidate_index=0,parameters=parameters,
            precondition_state=precondition,authority_capabilities=template.authority_capabilities,
            mitigation=template.mitigation,induced=template.induced,induced_response=template.induced_response,response_model=template.response_model,
            response_parameters=template.response_parameters,response_provenance=template.response_provenance,
            response_parameter_status=template.response_parameter_status,
            coverage=template.coverage,preparation_time_minutes=template.preparation_time_minutes,
            deadline_semantics=template.deadline_semantics))
    return tuple(candidates)
