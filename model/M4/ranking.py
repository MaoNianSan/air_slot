from __future__ import annotations

from model.common.errors import ContractError
from model.common.estimand import FormalEstimandStatus


def compatible_formal_ranking(evaluations):
    formal = [item for item in evaluations if item.lane == "FORMAL"]
    identities = {
        (item.estimand_id, item.estimand_version, item.scope_hash, item.valuation_registry_id)
        for item in formal
    }
    if len(identities) > 1:
        raise ContractError("FORMAL_RANKING_ESTIMAND_SCOPE_MISMATCH")
    if any(
        item.formal_aggregate_status is not FormalEstimandStatus.FORMAL_AVAILABLE
        or item.residual_risk_j is None
        for item in formal
    ):
        raise ContractError("FORMAL_RANKING_AGGREGATE_INVALID")
    return sorted(formal, key=lambda item: (
        item.residual_risk_j,
        item.action_index,
        item.candidate_index,
        item.candidate_action_id,
    ))


def finalize_ranking(evaluations, *, baseline_valid: bool):
    if not baseline_valid:
        return tuple(evaluations), (), "AUTHORITATIVE_DECISION_UNAVAILABLE", False
    formal = compatible_formal_ranking(evaluations)
    ranks = {item.candidate_action_id: index + 1 for index, item in enumerate(formal)}
    ranked = tuple(item.model_copy(update={"ranking_position": ranks.get(item.candidate_action_id)})
                   for item in evaluations)
    ranking = tuple(item.candidate_action_id for item in formal)
    a00 = next((item for item in formal if item.template_id == "A00"), None)
    if not formal:
        outcome, authoritative = "AUTHORITATIVE_DECISION_UNAVAILABLE", False
    elif len(formal) == 1 and a00:
        outcome, authoritative = "NO_OTHER_ACTION_CURRENTLY_FORMALLY_COMPARABLE", True
    elif formal[0].template_id == "A00":
        outcome, authoritative = "FORMAL_A00_PREFERRED_WITHIN_DECLARED_ESTIMAND", True
    else:
        outcome, authoritative = "FORMAL_ACTION_PREFERRED_WITHIN_DECLARED_ESTIMAND", True
    return ranked, ranking, outcome, authoritative
