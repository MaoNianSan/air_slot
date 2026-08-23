"""Risk evaluation over constructed RMB values obtained from CU values."""

from __future__ import annotations

from model.M4.residual_risk import (
    ResidualRiskPolicy,
    RiskEvaluationSupport,
    RankingAuthority,
    weighted_expectation,
    weighted_var_cvar,
    weighted_variance,
)
from model.M4.rmb_interface import RMBActionEnvelopeInput
from model.common.rmb_mapping import RMBMappingRegistry


def evaluate_rmb_risk(
    envelope: RMBActionEnvelopeInput,
    *,
    rmb_mapping: RMBMappingRegistry,
    risk_policy: ResidualRiskPolicy,
) -> dict:
    """Return a typed, constructed-RMB risk summary for one action envelope.

    The returned values are model-implied constructed units.  No observed
    currency interpretation is attached.
    """
    if not isinstance(rmb_mapping, RMBMappingRegistry):
        rmb_mapping = RMBMappingRegistry.model_validate(rmb_mapping)
    totals = []
    component_rows = []
    for scenario in envelope.scenario_consequences:
        supported = [item for item in scenario.components if item.cu_value is not None]
        if len(supported) != len(scenario.components) or not rmb_mapping.executable:
            component_rows.append({"scenario_id": scenario.scenario_id, "rmb_by_component": None, "total_rmb": None})
            continue
        cu = {item.component_id: float(item.cu_value) for item in supported}
        mapped = rmb_mapping.to_component_rmb(cu)
        total = None if mapped is None else sum(mapped.values())
        component_rows.append({"scenario_id": scenario.scenario_id, "rmb_by_component": mapped, "total_rmb": total})
        if total is not None:
            totals.append(total)
    if len(totals) != len(envelope.scenario_consequences):
        return {
            "status": "ABSTAINED",
            "constructed_unit_id": "RMB",
            "monetary_ground_truth_claim": False,
            "support_state": RiskEvaluationSupport.ABSTAINED.value,
            "ranking_authority": RankingAuthority.NOT_RANKED.value,
            "reason_code": "RMB_MAPPING_OR_CONSEQUENCE_SUPPORT_UNAVAILABLE",
            "component_rows": component_rows,
        }
    weights = tuple(envelope.scenario_weights)
    expected = weighted_expectation(tuple(totals), weights)
    variance = weighted_variance(tuple(totals), weights)
    var, cvar = weighted_var_cvar(tuple(totals), weights, risk_policy.alpha)
    objective = risk_policy.expected_loss_coefficient * expected + risk_policy.cvar_coefficient * cvar
    support = RiskEvaluationSupport.SUPPORTED if rmb_mapping.authoritative else RiskEvaluationSupport.ASSUMPTION_BASED
    authority = RankingAuthority.AUTHORITATIVE if rmb_mapping.authoritative else RankingAuthority.CONDITIONAL
    return {
        "status": "EVALUATED",
        "constructed_unit_id": "RMB",
        "monetary_ground_truth_claim": False,
        "scenario_dependent": True,
        "support_state": support.value,
        "ranking_authority": authority.value,
        "expected_rmb": expected,
        "rmb_variance": variance,
        "rmb_var_alpha": var,
        "rmb_cvar_alpha": cvar,
        "residual_risk_objective": objective,
        "component_rows": component_rows,
    }


__all__ = ["evaluate_rmb_risk"]
