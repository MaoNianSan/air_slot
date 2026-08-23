"""Paper-aligned sequential decision-chain entry point."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .action_response import (
    ActionEligibility,
    ActionMaterialization,
    ActionResponseRule,
    ActionTemplate,
    materialize_action,
)
from .contracts import ConsequenceScenario, FrozenModel, HistoryConditionedState, OperationalInformation
from .risk import (
    RMBMappingRegistry,
    RMBMappingRule,
    ResidualRiskEvaluation,
    ResidualRiskPolicy,
    RiskEvaluationStatus,
    evaluate_residual_risk,
)


class DecisionChainInput(FrozenModel):
    """Explicit inputs for E -> S -> C -> CU -> A -> C^a -> CU^a -> risk."""

    information: OperationalInformation
    state: HistoryConditionedState
    actions: tuple[ActionTemplate, ...] = Field(min_length=1)
    eligibilities: tuple[ActionEligibility, ...] = Field(min_length=1)
    response_rules: tuple[ActionResponseRule, ...] = Field(min_length=1)
    mapping: RMBMappingRule | RMBMappingRegistry
    risk_policy: ResidualRiskPolicy
    seed: int = 0

    @model_validator(mode="after")
    def validate_lineage(self):
        if self.state.episode_id != self.information.episode_id or self.state.decision_node_id != self.information.decision_node_id:
            raise ValueError("DECISION_CHAIN_E_S_LINEAGE_MISMATCH")
        if self.state.information_hash != self.information.information_hash:
            raise ValueError("DECISION_CHAIN_INFORMATION_HASH_MISMATCH")
        action_ids = tuple(item.action_id for item in self.actions)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("DECISION_CHAIN_DUPLICATE_ACTION")
        return self


class DecisionChainOutput(FrozenModel):
    episode_id: str
    decision_node_id: str
    information_hash: str
    state_hash: str
    baseline_scenario_count: int
    materializations: tuple[ActionMaterialization, ...]
    risk_evaluations: tuple[ResidualRiskEvaluation, ...]
    decision_action_id: str | None = None
    decision_status: str
    claim_scope: str = "SEQUENTIAL_RESIDUAL_RISK_SELECTION_NOT_CAUSAL"
    final_test_access_count: int = 0
    paper_full_run: bool = False
    provenance: tuple[str, ...] = ("AIR_SLOT_DECISION_CHAIN",)

    @model_validator(mode="after")
    def safety_gate(self):
        if self.final_test_access_count != 0:
            raise ValueError("DECISION_CHAIN_FINAL_TEST_ACCESS_NONZERO")
        if self.paper_full_run:
            raise ValueError("DECISION_CHAIN_PAPER_FULL_RUN_DISABLED")
        if self.decision_action_id is not None and self.decision_status != "AUTHORITATIVE_SELECTION":
            raise ValueError("DECISION_CHAIN_SELECTION_STATUS_MISMATCH")
        return self


def _rule_by_action(rules: tuple[ActionResponseRule, ...], action_id: str) -> ActionResponseRule:
    matches = [rule for rule in rules if rule.action_id == action_id]
    if len(matches) != 1:
        raise ValueError(f"DECISION_CHAIN_RESPONSE_RULE_COUNT:{action_id}:{len(matches)}")
    return matches[0]


def _eligibility_by_action(eligibilities: tuple[ActionEligibility, ...], action_id: str, node: str) -> ActionEligibility:
    matches = [item for item in eligibilities if item.action_id == action_id and item.decision_node_id == node]
    if len(matches) != 1:
        raise ValueError(f"DECISION_CHAIN_ELIGIBILITY_COUNT:{action_id}:{len(matches)}")
    return matches[0]


def run_decision_chain(inputs: DecisionChainInput) -> DecisionChainOutput:
    """Run the reference chain with explicit gates and no hidden inference."""
    materializations: list[ActionMaterialization] = []
    evaluations: list[ResidualRiskEvaluation] = []
    # Each baseline scenario is materialized independently so its scenario
    # weight remains part of the joint distribution.
    for action in inputs.actions:
        eligibility = _eligibility_by_action(inputs.eligibilities, action.action_id, inputs.information.decision_node_id)
        rule = _rule_by_action(inputs.response_rules, action.action_id)
        action_scenarios: list[ActionMaterialization] = []
        for baseline in inputs.state.consequence_scenarios:
            materialization = materialize_action(
                baseline=baseline,
                eligibility=eligibility,
                action=action,
                response_rule=rule,
                seed=inputs.seed,
            )
            action_scenarios.append(materialization)
        # Merge scenario-level materializations into one action envelope while
        # preserving each scenario's weight and draw provenance.
        first = action_scenarios[0]
        merged = first.model_copy(update={"scenarios": tuple(item.scenarios[0] for item in action_scenarios)})
        materializations.append(merged)
        evaluations.append(
            evaluate_residual_risk(materialization=merged, mapping=inputs.mapping, policy=inputs.risk_policy)
        )

    ranked = [item for item in evaluations if item.ranking_allowed and item.objective is not None]
    if len(ranked) == len(evaluations) and ranked:
        selected = min(ranked, key=lambda item: (float(item.objective), item.action_id))
        decision_action_id = selected.action_id
        decision_status = "AUTHORITATIVE_SELECTION"
    elif any(item.status is RiskEvaluationStatus.CONDITIONAL for item in evaluations):
        decision_action_id = None
        decision_status = "CONDITIONAL_NO_AUTHORITATIVE_RANKING"
    else:
        decision_action_id = None
        decision_status = "ABSTAIN_NO_COMPARABLE_ACTION"
    return DecisionChainOutput(
        episode_id=inputs.information.episode_id,
        decision_node_id=inputs.information.decision_node_id,
        information_hash=inputs.information.information_hash,
        state_hash=inputs.state.state_hash,
        baseline_scenario_count=len(inputs.state.consequence_scenarios),
        materializations=tuple(materializations),
        risk_evaluations=tuple(evaluations),
        decision_action_id=decision_action_id,
        decision_status=decision_status,
    )


__all__ = ["DecisionChainInput", "DecisionChainOutput", "run_decision_chain"]
