def project_authority(decision,user_capabilities:set[str],candidate_by_id):
    return {action.candidate_action_id:("DIRECT" if set(candidate_by_id[action.candidate_action_id].authority_capabilities)<=user_capabilities else "ESCALATE") for action in decision.actions}
