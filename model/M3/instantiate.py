from dataclasses import dataclass

from model.common.identity import content_id
from .contracts import ActionInstantiationRecord, CandidateAction, InstantiationState
from .factual_adapter import adapt_pre_state, evaluate_action_facts


@dataclass(frozen=True)
class ActionInstantiationEvaluation:
    """χ_inst for one template, independent of its factual conditions."""

    state: InstantiationState
    parameters: dict[str, object]
    missing_parameters: tuple[str, ...]
    reason: str


def evaluate_action_instantiation(template, adapted) -> ActionInstantiationEvaluation:
    """Evaluate whether the declared mathematical action parameters exist."""
    parameters = {
        name: adapted.parameters.get(name) for name in template.required_parameters
    }
    missing = tuple(name for name, value in parameters.items() if value is None)
    if missing:
        return ActionInstantiationEvaluation(
            state=InstantiationState.NOT_FORMED,
            parameters=parameters,
            missing_parameters=missing,
            reason="REQUIRED_PARAMETER_MISSING",
        )
    return ActionInstantiationEvaluation(
        state=InstantiationState.FORMED,
        parameters=parameters,
        missing_parameters=(),
        reason="REQUIRED_PARAMETERS_PRESENT",
    )


def instantiate_action_records(
    pre_state: dict, registry, *, response_registry=None, sensitivity="BASE"
):
    """Return one auditable instantiation record for every action template."""
    adapted = adapt_pre_state(pre_state)
    if not isinstance(pre_state, dict):
        episode_id = pre_state.decision_node.episode_id
        decision_node_id = pre_state.decision_node.decision_node_id
    else:
        episode_id = pre_state["episode_id"]
        decision_node_id = pre_state["decision_node_id"]
    records = []
    for action_index, template in enumerate(registry.templates):
        # χ_fact is recorded on the instance; it does not decide χ_inst.
        factual = evaluate_action_facts(template, adapted)
        precondition = factual.state.value
        instantiation = evaluate_action_instantiation(template, adapted)
        if instantiation.state is not InstantiationState.FORMED:
            records.append(
                ActionInstantiationRecord(
                    template_id=template.template_id,
                    instantiation_state=instantiation.state,
                    reason=instantiation.reason,
                    missing_required_parameters=instantiation.missing_parameters,
                    source=(
                        f"registry_id={registry.registry_id}",
                        f"registry_schema_version={registry.schema_version}",
                    ),
                    lineage=(
                        f"episode_id={episode_id}",
                        f"decision_node_id={decision_node_id}",
                        f"action_index={action_index}",
                    ),
                    candidate=None,
                )
            )
            continue
        parameters = {
            "episode_id": episode_id,
            "decision_node_id": decision_node_id,
            **instantiation.parameters,
        }
        stable_parameters = {
            name: value
            for name, value in parameters.items()
            if name != "decision_node_id"
        }
        identity = content_id(
            {
                "template": template.template_id,
                "parameters": stable_parameters,
                "registry": registry.schema_version,
            }
        )
        response_model = template.response_model
        response_parameters = template.response_parameters
        response_provenance = template.response_provenance
        response_status = template.response_parameter_status
        response_registry_id = None
        response_registry_hash = None
        if (
            response_registry is not None
            and template.template_id in response_registry.actions
        ):
            merged = response_registry.parameters(
                template.template_id, sensitivity=sensitivity
            )
            response_model = merged.pop("response_model")
            response_status = merged.pop("response_parameter_status")
            response_provenance = merged.pop("response_provenance")
            response_parameters = merged
            response_registry_id = response_registry.registry_id
            response_registry_hash = response_registry.digest()
        candidate = CandidateAction(
                candidate_action_id=f"{template.template_id}:{identity.split(':')[1][:16]}",
                template_id=template.template_id,
                action_family=template.family,
                action_index=action_index,
                candidate_index=0,
                parameters=parameters,
                precondition_state=precondition,
                instantiation_state=instantiation.state,
                authority_capabilities=template.authority_capabilities,
                mitigation=template.mitigation,
                induced=template.induced,
                induced_response=template.induced_response,
                response_model=response_model,
                response_parameters=response_parameters,
                response_provenance=response_provenance,
                response_support=getattr(template, "response_support", None),
                response_parameter_status=response_status,
                response_registry_id=response_registry_id,
                response_registry_hash=response_registry_hash,
                response_sensitivity_level=sensitivity,
                coverage=template.coverage,
                preparation_time_minutes=template.preparation_time_minutes,
                deadline_semantics=template.deadline_semantics,
                precondition_reason=factual.reason,
                factual_provenance=factual.provenance,
            )
        records.append(
            ActionInstantiationRecord(
                template_id=template.template_id,
                instantiation_state=instantiation.state,
                reason=instantiation.reason,
                missing_required_parameters=instantiation.missing_parameters,
                source=(
                    f"registry_id={registry.registry_id}",
                    f"registry_schema_version={registry.schema_version}",
                ),
                lineage=(
                    f"episode_id={episode_id}",
                    f"decision_node_id={decision_node_id}",
                    f"action_index={action_index}",
                    *factual.provenance,
                ),
                candidate=candidate,
            )
        )
    return tuple(records)


def instantiate_candidates(
    pre_state: dict, registry, *, response_registry=None, sensitivity="BASE"
):
    """Compatibility projection containing only formed candidates."""
    return tuple(
        record.candidate
        for record in instantiate_action_records(
            pre_state,
            registry,
            response_registry=response_registry,
            sensitivity=sensitivity,
        )
        if record.instantiation_state is InstantiationState.FORMED
    )
