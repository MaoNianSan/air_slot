from model.common.identity import content_id
from .contracts import CandidateAction

def instantiate_candidates(pre_state:dict,registry,*,response_registry=None,sensitivity="BASE"):
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
        # I(a): factual eligibility from current state only.
        structural_states=[facts.get(name) for name in template.required_facts]
        precondition=("FALSE" if any(value is False for value in structural_states)
                      else "UNKNOWN" if any(value is None for value in structural_states)
                      else "TRUE")
        if precondition=="FALSE":continue
        # I(a) also requires named action parameters to be instantiable.
        parameter_values={name:episode_parameters.get(name) for name in template.required_parameters}
        if any(value is None for value in parameter_values.values()):
            continue  # I(a)=0: not in A_{i,t}; never silently fabricated.
        parameters={"episode_id":episode_id,"decision_node_id":decision_node_id,**parameter_values}
        stable_parameters={name:value for name,value in parameters.items() if name!="decision_node_id"}
        identity=content_id({"template":template.template_id,"parameters":stable_parameters,"registry":registry.schema_version})
        response_model=template.response_model
        response_parameters=template.response_parameters
        response_provenance=template.response_provenance
        response_status=template.response_parameter_status
        response_registry_id=None
        response_registry_hash=None
        if response_registry is not None and template.template_id in response_registry.actions:
            merged=response_registry.parameters(template.template_id,sensitivity=sensitivity)
            response_model=merged.pop("response_model")
            response_status=merged.pop("response_parameter_status")
            response_provenance=merged.pop("response_provenance")
            response_parameters=merged
            response_registry_id=response_registry.registry_id
            response_registry_hash=response_registry.digest()
        candidates.append(CandidateAction(candidate_action_id=f"{template.template_id}:{identity.split(':')[1][:16]}",
            template_id=template.template_id,action_family=template.family,action_index=action_index,
            candidate_index=0,parameters=parameters,
            precondition_state=precondition,instantiable=True,
            authority_capabilities=template.authority_capabilities,
            mitigation=template.mitigation,induced=template.induced,induced_response=template.induced_response,response_model=response_model,
            response_parameters=response_parameters,response_provenance=response_provenance,
            response_support=getattr(template, "response_support", None),
            response_parameter_status=response_status,
            response_registry_id=response_registry_id,response_registry_hash=response_registry_hash,
            response_sensitivity_level=sensitivity,
            coverage=template.coverage,preparation_time_minutes=template.preparation_time_minutes,
            deadline_semantics=template.deadline_semantics))
    return tuple(candidates)
