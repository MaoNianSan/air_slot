"""JSON codecs for the frozen decision contracts.

Checkpoints are JSON documents, so every contract object crossing a stage
boundary is serialized here. The codec is lossless for the frozen scientific
fields: enums keep their exact wire values and ``None`` never becomes ``0``.
"""

from __future__ import annotations

from typing import Any, Mapping

from model.common.decision_contracts import (
    AttentionDecision,
    AttentionEntry,
    ConsequenceScenario,
    ConsequenceScenarioSet,
    HeadroomSummary,
    PrioritySignal,
    RecoveryDecision,
    SignalKind,
    SolverStatus,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TypedStatus,
)
from model.common.decision_contracts import HistoryScope, TemporalKind, UncertaintyKind
from model.common.enums import OperationalStage, SupportState


def representation_to_payload(spec: StateRepresentationSpec) -> dict[str, Any]:
    return {
        "temporal": spec.temporal.value,
        "uncertainty": spec.uncertainty.value,
        "history_capacity": spec.history_capacity,
        "history_scope": (
            None if spec.history_scope is None else spec.history_scope.value
        ),
    }


def representation_from_payload(data: Mapping[str, Any]) -> StateRepresentationSpec:
    scope = data.get("history_scope")
    return StateRepresentationSpec(
        temporal=TemporalKind(str(data["temporal"])),
        uncertainty=UncertaintyKind(str(data["uncertainty"])),
        history_capacity=data.get("history_capacity"),
        history_scope=None if scope is None else HistoryScope(str(scope)),
    )


def state_scenario_to_payload(scenario: StateScenario) -> dict[str, Any]:
    return {
        "scenario_id": int(scenario.scenario_id),
        "scenario_weight": float(scenario.scenario_weight),
        "stage": OperationalStage(scenario.stage).value,
        "t_ib_minutes": scenario.t_ib_minutes,
        "d_ob_minutes": scenario.d_ob_minutes,
        "d_tx_minutes": scenario.d_tx_minutes,
        "d_to_minutes": scenario.d_to_minutes,
        "tx_reference_minutes": scenario.tx_reference_minutes,
        "support": SupportState(scenario.support).value,
        "ib_observed": bool(scenario.ib_observed),
        "ob_observed": bool(scenario.ob_observed),
        "tx_observed": bool(scenario.tx_observed),
    }


def state_scenario_from_payload(data: Mapping[str, Any]) -> StateScenario:
    return StateScenario(
        scenario_id=int(data["scenario_id"]),
        scenario_weight=float(data["scenario_weight"]),
        stage=OperationalStage(str(data["stage"])),
        t_ib_minutes=_optional_float(data.get("t_ib_minutes")),
        d_ob_minutes=_optional_float(data.get("d_ob_minutes")),
        d_tx_minutes=_optional_float(data.get("d_tx_minutes")),
        d_to_minutes=_optional_float(data.get("d_to_minutes")),
        tx_reference_minutes=_optional_float(data.get("tx_reference_minutes")),
        support=SupportState(str(data.get("support", SupportState.SUPPORTED.value))),
        ib_observed=bool(data.get("ib_observed", False)),
        ob_observed=bool(data.get("ob_observed", False)),
        tx_observed=bool(data.get("tx_observed", False)),
    )


def state_set_to_payload(state_set: StateScenarioSet) -> dict[str, Any]:
    return {
        "episode_id": state_set.episode_id,
        "chain_id": state_set.chain_id,
        "node_id": state_set.node_id,
        "stage": OperationalStage(state_set.stage).value,
        "representation": representation_to_payload(state_set.representation),
        "representation_id": state_set.representation.representation_id,
        "scenarios": [
            state_scenario_to_payload(scenario) for scenario in state_set.scenarios
        ],
    }


def state_set_from_payload(data: Mapping[str, Any]) -> StateScenarioSet:
    return StateScenarioSet(
        episode_id=str(data["episode_id"]),
        chain_id=str(data["chain_id"]),
        node_id=str(data["node_id"]),
        stage=OperationalStage(str(data["stage"])),
        representation=representation_from_payload(data["representation"]),
        scenarios=tuple(
            state_scenario_from_payload(item) for item in data["scenarios"]
        ),
    )


def consequence_set_to_payload(
    consequence: ConsequenceScenarioSet,
) -> dict[str, Any]:
    return {
        "episode_id": consequence.episode_id,
        "chain_id": consequence.chain_id,
        "node_id": consequence.node_id,
        "stage": OperationalStage(consequence.stage).value,
        "representation": representation_to_payload(consequence.representation),
        "representation_id": consequence.representation.representation_id,
        "registry_id": consequence.registry_id,
        "registry_hash": consequence.registry_hash,
        "support": SupportState(consequence.support).value,
        "scenarios": [_consequence_scenario(item) for item in consequence.scenarios],
    }


def _consequence_scenario(scenario: ConsequenceScenario) -> dict[str, Any]:
    return {
        "scenario_id": int(scenario.scenario_id),
        "scenario_weight": float(scenario.scenario_weight),
        "native_components": dict(scenario.native_components),
        "cu_components": dict(scenario.cu_components),
        "domain_scores": dict(scenario.domain_scores),
        "consequence_priority": scenario.consequence_priority,
        "support": SupportState(scenario.support).value,
    }


def consequence_set_from_payload(data: Mapping[str, Any]) -> ConsequenceScenarioSet:
    return ConsequenceScenarioSet(
        episode_id=str(data["episode_id"]),
        chain_id=str(data["chain_id"]),
        node_id=str(data["node_id"]),
        stage=OperationalStage(str(data["stage"])),
        representation=representation_from_payload(data["representation"]),
        registry_id=str(data["registry_id"]),
        registry_hash=str(data["registry_hash"]),
        support=SupportState(str(data.get("support", SupportState.SUPPORTED.value))),
        scenarios=tuple(
            ConsequenceScenario(
                scenario_id=int(item["scenario_id"]),
                scenario_weight=float(item["scenario_weight"]),
                native_components={
                    key: _optional_float(value)
                    for key, value in item["native_components"].items()
                },
                cu_components={
                    key: _optional_float(value)
                    for key, value in item["cu_components"].items()
                },
                domain_scores={
                    key: _optional_float(value)
                    for key, value in item["domain_scores"].items()
                },
                consequence_priority=_optional_float(
                    item.get("consequence_priority")
                ),
                support=SupportState(
                    str(item.get("support", SupportState.SUPPORTED.value))
                ),
            )
            for item in data["scenarios"]
        ),
    )


def priority_signal_to_payload(signal: PrioritySignal) -> dict[str, Any]:
    return {
        "signal_type": SignalKind(signal.signal_type).value,
        "episode_id": signal.episode_id,
        "chain_id": signal.chain_id,
        "node_id": signal.node_id,
        "representation_id": signal.representation_id,
        "score": signal.score,
        "support": SupportState(signal.support).value,
        "status": TypedStatus(signal.status).value,
        "comparison_support_mass": signal.comparison_support_mass,
        "comparison_support_threshold": signal.comparison_support_threshold,
        "reason_codes": list(signal.reason_codes),
    }


def priority_signal_from_payload(data: Mapping[str, Any]) -> PrioritySignal:
    return PrioritySignal(
        signal_type=SignalKind(str(data["signal_type"])),
        episode_id=str(data["episode_id"]),
        chain_id=str(data["chain_id"]),
        node_id=str(data["node_id"]),
        representation_id=str(data["representation_id"]),
        score=_optional_float(data.get("score")),
        support=SupportState(str(data["support"])),
        status=TypedStatus(str(data["status"])),
        comparison_support_mass=_optional_float(
            data.get("comparison_support_mass")
        ),
        comparison_support_threshold=_optional_float(
            data.get("comparison_support_threshold")
        ),
        reason_codes=tuple(str(code) for code in data.get("reason_codes", ())),
    )


def attention_decision_to_payload(decision: AttentionDecision) -> dict[str, Any]:
    return {
        "signal_type": SignalKind(decision.signal_type).value,
        "q": float(decision.q),
        "k": int(decision.k),
        "cohort_size": int(decision.cohort_size),
        "status": TypedStatus(decision.status).value,
        "entries": [
            {
                "episode_id": entry.episode_id,
                "chain_id": entry.chain_id,
                "node_id": entry.node_id,
                "score": float(entry.score),
                "rank": int(entry.rank),
                "selected": bool(entry.selected),
                "selected_for": SignalKind(entry.selected_for).value,
            }
            for entry in decision.entries
        ],
        "selected_node_ids": [
            entry.node_id for entry in decision.entries if entry.selected
        ],
    }


def attention_decision_from_payload(data: Mapping[str, Any]) -> AttentionDecision:
    return AttentionDecision(
        signal_type=SignalKind(str(data["signal_type"])),
        q=float(data["q"]),
        k=int(data["k"]),
        cohort_size=int(data["cohort_size"]),
        status=TypedStatus(str(data.get("status", TypedStatus.SUPPORTED.value))),
        entries=tuple(
            AttentionEntry(
                episode_id=str(item["episode_id"]),
                chain_id=str(item["chain_id"]),
                node_id=str(item["node_id"]),
                score=float(item["score"]),
                rank=int(item["rank"]),
                selected=bool(item["selected"]),
                selected_for=SignalKind(str(item["selected_for"])),
            )
            for item in data["entries"]
        ),
    )


def headroom_summary_to_payload(summary: HeadroomSummary) -> dict[str, Any]:
    return {
        "u_max": float(summary.u_max),
        "turnaround_lower_bound_q": float(summary.turnaround_lower_bound_q),
        "turnaround_quantile": float(summary.turnaround_quantile),
        "headroom_quantile": float(summary.headroom_quantile),
        "headroom_positive_n": int(summary.headroom_positive_n),
        "source_id": summary.source_id,
        "floor_to_minutes": float(summary.floor_to_minutes),
    }


def headroom_summary_from_payload(data: Mapping[str, Any]) -> HeadroomSummary:
    return HeadroomSummary(
        u_max=float(data["u_max"]),
        turnaround_lower_bound_q=float(data["turnaround_lower_bound_q"]),
        turnaround_quantile=float(data["turnaround_quantile"]),
        headroom_quantile=float(data["headroom_quantile"]),
        headroom_positive_n=int(data["headroom_positive_n"]),
        source_id=str(data["source_id"]),
        floor_to_minutes=float(data["floor_to_minutes"]),
    )


def recovery_decision_to_payload(decision: RecoveryDecision) -> dict[str, Any]:
    summary = decision.headroom_summary
    return {
        "episode_id": decision.episode_id,
        "chain_id": decision.chain_id,
        "node_id": decision.node_id,
        "representation_id": decision.representation_id,
        "stage": OperationalStage(decision.stage).value,
        "actionable_status": TypedStatus(decision.actionable_status).value,
        "headroom_summary": (
            None if summary is None else headroom_summary_to_payload(summary)
        ),
        "action_grid": [float(value) for value in decision.action_grid],
        "u_max": decision.u_max,
        "u_star": decision.u_star,
        "j_zero": decision.j_zero,
        "j_star": decision.j_star,
        "recoverable_value": decision.recoverable_value,
        "lambda_policy": decision.lambda_policy,
        "solver_status": SolverStatus(decision.solver_status).value,
        "tie_break_applied": decision.tie_break_applied,
        "near_tie_candidate_count": decision.near_tie_candidate_count,
        "reason_codes": list(decision.reason_codes),
    }


def recovery_decision_from_payload(data: Mapping[str, Any]) -> RecoveryDecision:
    summary = data.get("headroom_summary")
    return RecoveryDecision(
        episode_id=str(data["episode_id"]),
        chain_id=str(data["chain_id"]),
        node_id=str(data["node_id"]),
        representation_id=str(data["representation_id"]),
        stage=OperationalStage(str(data["stage"])),
        actionable_status=TypedStatus(str(data["actionable_status"])),
        headroom_summary=(
            None if summary is None else headroom_summary_from_payload(summary)
        ),
        action_grid=tuple(float(value) for value in data.get("action_grid", ())),
        u_max=_optional_float(data.get("u_max")),
        u_star=_optional_float(data.get("u_star")),
        j_zero=_optional_float(data.get("j_zero")),
        j_star=_optional_float(data.get("j_star")),
        recoverable_value=_optional_float(data.get("recoverable_value")),
        lambda_policy=_optional_float(data.get("lambda_policy")),
        solver_status=SolverStatus(
            str(data.get("solver_status", SolverStatus.NOT_RUN.value))
        ),
        tie_break_applied=data.get("tie_break_applied"),
        near_tie_candidate_count=data.get("near_tie_candidate_count"),
        reason_codes=tuple(str(code) for code in data.get("reason_codes", ())),
    )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


__all__ = [
    "attention_decision_from_payload",
    "attention_decision_to_payload",
    "consequence_set_from_payload",
    "consequence_set_to_payload",
    "headroom_summary_from_payload",
    "headroom_summary_to_payload",
    "priority_signal_from_payload",
    "priority_signal_to_payload",
    "recovery_decision_from_payload",
    "recovery_decision_to_payload",
    "representation_from_payload",
    "representation_to_payload",
    "state_scenario_from_payload",
    "state_scenario_to_payload",
    "state_set_from_payload",
    "state_set_to_payload",
]
