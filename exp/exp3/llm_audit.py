from collections import defaultdict

from exp.common.rng import stream_generator


ALLOWED_JUDGEMENTS = {"ACCEPT", "ACCEPT_WITH_RESERVATIONS", "REJECT", "INSUFFICIENT_INFORMATION"}
ALLOWED_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
REQUIRED_SECTIONS = (
    "PLAUSIBLE_OPERATIONAL_OUTCOMES", "PRIMARY_MITIGATION", "EXECUTION_BURDENS",
    "RESOURCE_DEPENDENCIES", "DOWNSTREAM_EFFECTS", "TIMING_FEASIBILITY",
    "MISSING_CRITICAL_INFORMATION", "FINAL_JUDGEMENT", "CONFIDENCE",
)

CASE_STRATA = (
    "formal_non_null_top1",
    "formal_a00_top1",
    "relaxed_only_invalidated_top1",
    "scenario_conditional_close_call",
)


def select_audit_cases(cases, *, target_episodes=400, global_seed=0):
    """Development-frozen stratified selection, at most one node per episode."""
    by_stratum = defaultdict(dict)
    for case in cases:
        stratum = case.get("stratum")
        if stratum not in CASE_STRATA:
            continue
        by_stratum[stratum].setdefault(case["episode_id"], case)
    quota = max(1, target_episodes // len(CASE_STRATA))
    selected = []
    used_episodes = set()
    for stratum in CASE_STRATA:
        candidates = [case for episode, case in sorted(by_stratum[stratum].items())
                      if episode not in used_episodes]
        rng = stream_generator("llm_case_selection", global_seed, stratum)
        order = rng.permutation(len(candidates)) if candidates else ()
        for index in order[:quota]:
            case = candidates[int(index)]
            selected.append(case)
            used_episodes.add(case["episode_id"])
    return tuple(selected)


def validate_audit_response(response):
    if not isinstance(response, dict) or any(name not in response for name in REQUIRED_SECTIONS):
        raise ValueError("DEEPSEEK_AUDIT_SCHEMA_INVALID")
    if response["FINAL_JUDGEMENT"] not in ALLOWED_JUDGEMENTS:
        raise ValueError("DEEPSEEK_AUDIT_JUDGEMENT_INVALID")
    if response["CONFIDENCE"] not in ALLOWED_CONFIDENCE:
        raise ValueError("DEEPSEEK_AUDIT_CONFIDENCE_INVALID")
    return response


def audit_cases(cases,provider=None,protocol="BLINDED_CHOICE"):
    if provider is None:return tuple({"case_id":case["case_id"],"protocol":protocol,"status":"NOT_RUN","reason_code":"LLM_PROVIDER_NOT_CONFIGURED"} for case in cases)
    results=[]
    for case in cases:
        response=validate_audit_response(provider.audit(case,protocol=protocol))
        results.append({"case_id":case["case_id"],"protocol":protocol,"status":"COMPLETED","response":response,"artifact_layer":"EVALUATION"})
    return tuple(results)
