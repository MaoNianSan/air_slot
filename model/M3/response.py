"""Legacy V1 aggregate scenario response engine (M3_RESPONSE_SCENARIO_V1).

This module is retained for compatibility. It is not the M3 V2 component-wise
`C^{a,CU}` interface and is not activated by that interface.

Implements exactly:

    Z ~ Bernoulli(p)
    R | Z=1 ~ Beta(alpha, beta)   alpha = mean * kappa, beta = (1-mean) * kappa
    rho = Z * R
    U_mitigated = max(0, U_pre * (1 - mitigation_coefficient * rho))
    U_post = U_mitigated + induced_score_to_cu * induced_score

Deterministic common random numbers (spec section 15): hash-based uniforms
keyed by episode_id, decision_node_id, m1_scenario_id, action_template_id,
response_dimension, sensitivity_level, response_registry_hash.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Mapping

from scipy.special import betaincinv

from model.common.errors import ContractError


def _uniform(key_payload: tuple[str, ...]) -> float:
    key = "|".join(key_payload)
    integer = int(sha256(key.encode("utf-8")).hexdigest()[:16], 16)
    return (integer + 0.5) / 2**64


def response_uniform(*, seed, episode_id, decision_node_id, scenario_id,
                     action_template_id, response_dimension, sensitivity_level,
                     response_registry_hash) -> float:
    return _uniform((
        "m3_response",
        str(seed),
        str(episode_id),
        str(decision_node_id),
        str(scenario_id),
        str(action_template_id),
        str(response_dimension),
        str(sensitivity_level),
        str(response_registry_hash),
    ))


def response_draw(*, seed, episode_id, decision_node_id, scenario_id,
                  action_template_id, parameters, response_registry_hash,
                  sensitivity_level: str = "BASE") -> float:
    """Realized mitigation intensity rho in [0, 1] for one action/scenario."""
    if parameters.get("response_model") == "DETERMINISTIC":
        return float(parameters.get("value", 0.0))
    if parameters.get("response_model") != "BERNOULLI_BETA":
        raise ContractError(f"M3_RESPONSE_MODEL_NOT_IMPLEMENTED:{parameters.get('response_model')}")
    probability = float(parameters["success_probability"])
    mean = float(parameters["mean_intensity"])
    concentration = float(parameters["concentration"])
    if not 0 <= probability <= 1 or not 0 < mean < 1 or concentration <= 0:
        raise ContractError("M3_RESPONSE_PARAMETERS_INVALID")
    implemented = response_uniform(
        seed=seed, episode_id=episode_id, decision_node_id=decision_node_id,
        scenario_id=scenario_id, action_template_id=action_template_id,
        response_dimension="BERNOULLI", sensitivity_level=sensitivity_level,
        response_registry_hash=response_registry_hash,
    ) <= probability
    if not implemented:
        return 0.0
    uniform = response_uniform(
        seed=seed, episode_id=episode_id, decision_node_id=decision_node_id,
        scenario_id=scenario_id, action_template_id=action_template_id,
        response_dimension="BETA_INTENSITY", sensitivity_level=sensitivity_level,
        response_registry_hash=response_registry_hash,
    )
    alpha = mean * concentration
    beta = (1.0 - mean) * concentration
    return float(betaincinv(alpha, beta, uniform))


def scenario_update(*, pre_cu: float, mitigation_coefficient: float,
                    rho: float, induced_score: float,
                    induced_score_to_cu: float) -> float:
    """Frozen post-action consequence update per component.

    ``induced_score_to_cu`` (gamma) must come from the frozen response/action
    registry; no hard-coded scientific default is permitted (Round 2, spec 9.2).
    """
    if pre_cu is None:
        raise ContractError("M3_SCENARIO_UPDATE_PRE_CU_MISSING")
    if not 0.0 <= rho <= 1.0:
        raise ContractError("M3_SCENARIO_UPDATE_RHO_OUT_OF_RANGE")
    mitigated = max(0.0, float(pre_cu) * (1.0 - float(mitigation_coefficient) * rho))
    return mitigated + float(induced_score_to_cu) * float(induced_score)


def action_post_consequences(*, pre_by_component: Mapping[str, float],
                             mitigation: Mapping[str, float],
                             induced: Mapping[str, float],
                             rho: float,
                             induced_score_to_cu: float,
                             included_components) -> dict[str, float]:
    """Frozen per-component U_post for one action realization.

    Missing mitigation/induced entries are treated as zero (spec 11) but no
    entry is invented: only declared components are updated; included formal
    components without declarations remain at their pre value.
    """
    post = {}
    for component in included_components:
        pre = pre_by_component.get(component)
        if pre is None:
            raise ContractError(f"M3_SCENARIO_UPDATE_COMPONENT_MISSING:{component}")
        m = float(mitigation.get(component, 0.0))
        d = float(induced.get(component, 0.0))
        post[component] = scenario_update(
            pre_cu=pre,
            mitigation_coefficient=m,
            rho=rho,
            induced_score=d,
            induced_score_to_cu=induced_score_to_cu,
        )
    return post


__all__ = [
    "action_post_consequences",
    "response_draw",
    "response_uniform",
    "scenario_update",
]
