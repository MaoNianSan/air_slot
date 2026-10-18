def assign_lane(candidate,opportunity_probability):
    if candidate.precondition_state=="FALSE" or opportunity_probability==0:return "EXCLUDED"
    if candidate.template_id=="A00":return "FORMAL"
    if candidate.precondition_state=="UNKNOWN":return "CONDITIONAL"
    if candidate.response_provenance in {"PURE_SCENARIO","STRUCTURAL_BOUNDED_SCENARIO"}:return "SCENARIO"
    if candidate.coverage not in {"FULL","HIGH"}:return "SCENARIO"
    return "FORMAL"
