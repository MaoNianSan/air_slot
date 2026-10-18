def audit_cases(cases,provider=None,protocol="BLINDED_CHOICE"):
    if provider is None:return tuple({"case_id":case["case_id"],"protocol":protocol,"status":"NOT_RUN","reason_code":"LLM_PROVIDER_NOT_CONFIGURED"} for case in cases)
    results=[]
    for case in cases:
        response=provider.audit(case,protocol=protocol)
        results.append({"case_id":case["case_id"],"protocol":protocol,"status":"COMPLETED","response":response,"artifact_layer":"EVALUATION"})
    return tuple(results)
