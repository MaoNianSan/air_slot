from hashlib import sha256
from scipy.special import betaincinv
from model.common.errors import ContractError

def stable_uniform(seed,episode,scenario,action,response_component):
    key=f"m3_m4_response|{seed}|{episode}|{scenario}|{action}|{response_component}"
    return (int(sha256(key.encode()).hexdigest()[:16],16)+.5)/2**64

def response_value(candidate,*,seed,episode,scenario,component=None):
    if candidate.template_id=="A00":return 0.0
    status=getattr(candidate.response_parameter_status,"value",candidate.response_parameter_status)
    if status!="FROZEN":raise ContractError("ACTION_RESPONSE_PARAMETERS_NOT_FROZEN")
    if candidate.response_model=="DETERMINISTIC":
        if "value" not in candidate.response_parameters:raise ContractError("ACTION_RESPONSE_PARAMETERS_NOT_FROZEN")
        return float(candidate.response_parameters["value"])
    parameters=candidate.response_parameters; action=candidate.candidate_action_id
    if candidate.response_model in {"DISCRETE_SCENARIO","EMPIRICAL"}:
        values=parameters.get("values")
        probabilities=parameters.get("probabilities")
        if not values or probabilities is None and candidate.response_model=="DISCRETE_SCENARIO":
            raise ContractError("ACTION_RESPONSE_PARAMETERS_NOT_FROZEN")
        probabilities=probabilities or [1/len(values)]*len(values)
        if len(values)!=len(probabilities) or any(p<0 for p in probabilities) or abs(sum(probabilities)-1)>1e-9:
            raise ContractError("ACTION_RESPONSE_PARAMETERS_INVALID")
        u=stable_uniform(seed,episode,scenario,action,candidate.response_model);total=0.0
        for value,probability in zip(values,probabilities):
            total+=probability
            if u<=total:return float(value)
        return float(values[-1])
    if candidate.response_model!="BERNOULLI_BETA":raise ContractError(f"RESPONSE_MODEL_NOT_IMPLEMENTED:{candidate.response_model}")
    failure="failure_probability" in parameters
    success="success_probability" in parameters
    required=("mean_intensity","concentration")
    if failure==success or any(name not in parameters for name in required):
        raise ContractError("ACTION_RESPONSE_PARAMETERS_NOT_FROZEN")
    probability=1-float(parameters["failure_probability"]) if failure else float(parameters["success_probability"])
    mean=float(parameters["mean_intensity"]); concentration=float(parameters["concentration"])
    if not 0<=probability<=1 or not 0<mean<1 or concentration<=0:
        raise ContractError("ACTION_RESPONSE_PARAMETERS_INVALID")
    implemented=stable_uniform(seed,episode,scenario,action,"BERNOULLI")<=probability
    if not implemented:return 0.0
    u=stable_uniform(seed,episode,scenario,action,"BETA_INTENSITY")
    return float(betaincinv(mean*concentration,(1-mean)*concentration,u))
