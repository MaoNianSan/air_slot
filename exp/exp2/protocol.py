"""Exp2 lifecycle and the mandatory common M3 -> M4 execution boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from exp.common.protocol import ExperimentProtocol
from exp.common.result_schema import ExperimentResult, SupportStatus
from model.M3.action_response import ActionEvaluationEnvelope
from model.M4.residual_risk import RiskEvaluationEnvelope

from .evaluator import Exp2EvaluationPayload, Exp2Evaluator
from .reporting import build_exp2_result
from .representation import (
    ConsequenceRepresentation,
    ConsequenceRepresentationAdapter,
    ScenarioRepresentation,
    ScenarioRepresentationAdapter,
)
from .variants import (
    EXP2A_JOINT,
    EXP2A_VARIANTS,
    EXP2B_COMPONENT,
    EXP2B_VARIANTS,
    EXP2_VARIANT_REGISTRY,
)


class Exp2DownstreamInterface(ABC):
    """One interface used by every variant; implementations call current M3/M4."""

    @abstractmethod
    def run_m3(
        self,
        *,
        variant_id: str,
        scenarios: ScenarioRepresentation,
        consequences: ConsequenceRepresentation,
    ) -> tuple[ActionEvaluationEnvelope, ...]:
        """Return current typed M3 action-response envelopes."""

    @abstractmethod
    def run_m4(
        self,
        *,
        variant_id: str,
        m3_envelopes: tuple[ActionEvaluationEnvelope, ...],
    ) -> tuple[RiskEvaluationEnvelope, ...]:
        """Return current typed M4 residual-risk envelopes; never raw CU scores."""


@dataclass(frozen=True)
class Exp2RunContext:
    variant_id: str
    dataset_id: str
    seed: int
    m1_scenarios: tuple[Any, ...]
    m2_consequences: Any
    m1_artifact_version: str
    m2_artifact_version: str
    model_versions: dict[str, str]
    downstream: Exp2DownstreamInterface
    scenario_hash: str | None = None
    config_hash: str | None = None
    state_metric_reason: str = "NO_FROZEN_STATE_UNCERTAINTY_METRIC_OR_OBSERVATIONS"
    artifact_lineage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedExp2Run:
    context: Exp2RunContext
    reference_variant_id: str
    reference_scenarios: ScenarioRepresentation
    reference_consequences: ConsequenceRepresentation
    variant_scenarios: ScenarioRepresentation
    variant_consequences: ConsequenceRepresentation


@dataclass(frozen=True)
class Exp2Execution:
    prepared: PreparedExp2Run
    reference_m3: tuple[ActionEvaluationEnvelope, ...]
    reference_m4: tuple[RiskEvaluationEnvelope, ...]
    variant_m3: tuple[ActionEvaluationEnvelope, ...]
    variant_m4: tuple[RiskEvaluationEnvelope, ...]


@dataclass(frozen=True)
class Exp2Evaluation:
    execution: Exp2Execution
    metrics: dict


class Exp2Protocol(ExperimentProtocol):
    def __init__(self, evaluator: Exp2Evaluator | None = None):
        self.evaluator = evaluator or Exp2Evaluator()

    def prepare(self, context: Exp2RunContext) -> PreparedExp2Run:
        if not isinstance(context, Exp2RunContext):
            raise TypeError("EXP2_RUN_CONTEXT_REQUIRED")
        EXP2_VARIANT_REGISTRY.get(context.variant_id)
        if not isinstance(context.downstream, Exp2DownstreamInterface):
            raise TypeError("EXP2_DOWNSTREAM_INTERFACE_REQUIRED")
        scenario_adapter = ScenarioRepresentationAdapter(
            context.m1_scenarios,
            artifact_version=context.m1_artifact_version,
            scenario_hash=context.scenario_hash,
        )
        consequence_adapter = ConsequenceRepresentationAdapter(
            context.m2_consequences,
            artifact_version=context.m2_artifact_version,
        )
        joint = scenario_adapter.transform(EXP2A_JOINT)
        component = consequence_adapter.transform(EXP2B_COMPONENT)
        if context.variant_id in EXP2A_VARIANTS:
            reference_id = EXP2A_JOINT
            variant_scenarios = scenario_adapter.transform(context.variant_id)
            variant_consequences = component
        elif context.variant_id in EXP2B_VARIANTS:
            reference_id = EXP2B_COMPONENT
            variant_scenarios = joint
            variant_consequences = consequence_adapter.transform(context.variant_id)
        else:  # registry validation above makes this defensive only.
            raise KeyError(f"EXP2_VARIANT_UNKNOWN:{context.variant_id}")
        return PreparedExp2Run(
            context=context,
            reference_variant_id=reference_id,
            reference_scenarios=joint,
            reference_consequences=component,
            variant_scenarios=variant_scenarios,
            variant_consequences=variant_consequences,
        )

    @staticmethod
    def _execute_downstream(
        downstream: Exp2DownstreamInterface,
        *,
        variant_id: str,
        scenarios: ScenarioRepresentation,
        consequences: ConsequenceRepresentation,
    ) -> tuple[tuple[ActionEvaluationEnvelope, ...], tuple[RiskEvaluationEnvelope, ...]]:
        m3 = tuple(downstream.run_m3(
            variant_id=variant_id,
            scenarios=scenarios,
            consequences=consequences,
        ))
        if any(not isinstance(item, ActionEvaluationEnvelope) for item in m3):
            raise TypeError("EXP2_M3_ACTION_EVALUATION_ENVELOPE_REQUIRED")
        m4 = tuple(downstream.run_m4(variant_id=variant_id, m3_envelopes=m3))
        if any(not isinstance(item, RiskEvaluationEnvelope) for item in m4):
            raise TypeError("EXP2_M4_RISK_EVALUATION_ENVELOPE_REQUIRED")
        m3_by_action = {item.action_id: item for item in m3}
        if len(m3_by_action) != len(m3):
            raise ValueError("EXP2_M3_DUPLICATE_ACTION")
        if set(item.action_id for item in m4) != set(m3_by_action):
            raise ValueError("EXP2_M4_ACTION_SET_MISMATCH")
        if any(
            item.m3_envelope_hash != m3_by_action[item.action_id].envelope_hash
            for item in m4
        ):
            raise ValueError("EXP2_M4_DID_NOT_CONSUME_M3_ENVELOPE")
        return m3, m4

    def run(self, prepared: PreparedExp2Run) -> Exp2Execution:
        if not isinstance(prepared, PreparedExp2Run):
            raise TypeError("EXP2_PREPARED_RUN_REQUIRED")
        downstream = prepared.context.downstream
        reference_m3, reference_m4 = self._execute_downstream(
            downstream,
            variant_id=prepared.reference_variant_id,
            scenarios=prepared.reference_scenarios,
            consequences=prepared.reference_consequences,
        )
        if prepared.context.variant_id == prepared.reference_variant_id:
            variant_m3, variant_m4 = reference_m3, reference_m4
        else:
            variant_m3, variant_m4 = self._execute_downstream(
                downstream,
                variant_id=prepared.context.variant_id,
                scenarios=prepared.variant_scenarios,
                consequences=prepared.variant_consequences,
            )
        reference_rules = {item.action_id: item.response_rule.rule_hash for item in reference_m3}
        variant_rules = {item.action_id: item.response_rule.rule_hash for item in variant_m3}
        if reference_rules != variant_rules:
            raise ValueError("EXP2_RESPONSE_REGISTRY_OR_ACTION_SET_MODIFIED")
        return Exp2Execution(
            prepared=prepared,
            reference_m3=reference_m3,
            reference_m4=reference_m4,
            variant_m3=variant_m3,
            variant_m4=variant_m4,
        )

    def evaluate(self, execution: Exp2Execution) -> Exp2Evaluation:
        if not isinstance(execution, Exp2Execution):
            raise TypeError("EXP2_EXECUTION_REQUIRED")
        prepared = execution.prepared
        lineage_preserved = (
            prepared.reference_scenarios.source_scenario_hash
            == prepared.variant_scenarios.source_scenario_hash
            and prepared.reference_consequences.source_artifact_hash
            == prepared.variant_consequences.source_artifact_hash
        )
        representation = (
            prepared.variant_scenarios
            if prepared.context.variant_id in EXP2A_VARIANTS
            else prepared.variant_consequences
        )
        metrics = self.evaluator.evaluate(Exp2EvaluationPayload(
            reference_variant_id=prepared.reference_variant_id,
            variant_id=prepared.context.variant_id,
            reference_m4=execution.reference_m4,
            variant_m4=execution.variant_m4,
            representation_lineage_preserved=lineage_preserved,
            artifact_lineage={
                **prepared.context.artifact_lineage,
                "m1_artifact_version": prepared.context.m1_artifact_version,
                "m1_scenario_hash": prepared.reference_scenarios.source_scenario_hash,
                "m2_artifact_version": prepared.context.m2_artifact_version,
                "m2_consequence_hash": prepared.reference_consequences.source_artifact_hash,
                "reference_scenario_representation_hash": prepared.reference_scenarios.representation_hash,
                "reference_consequence_representation_hash": prepared.reference_consequences.representation_hash,
                "comparison_representation_hash": representation.representation_hash,
                "reference_m3_envelope_hashes": tuple(
                    item.envelope_hash for item in execution.reference_m3
                ),
                "comparison_m3_envelope_hashes": tuple(
                    item.envelope_hash for item in execution.variant_m3
                ),
                "reference_m4_envelope_hashes": tuple(
                    item.risk_envelope_hash for item in execution.reference_m4
                ),
                "comparison_m4_envelope_hashes": tuple(
                    item.risk_envelope_hash for item in execution.variant_m4
                ),
            },
            state_metric_reason=prepared.context.state_metric_reason,
        ))
        return Exp2Evaluation(execution=execution, metrics=metrics)

    def report(self, evaluation: Exp2Evaluation) -> ExperimentResult:
        if not isinstance(evaluation, Exp2Evaluation):
            raise TypeError("EXP2_EVALUATION_REQUIRED")
        execution = evaluation.execution
        prepared = execution.prepared
        context = prepared.context
        required_downstream = {
            "DECISION_ACTION_DISAGREEMENT",
            "DECISION_RANKING_CHANGE",
            "DECISION_RISK_DIFFERENCE",
            "DECISION_CVAR_DIFFERENCE",
        }
        downstream_statuses = {
            metric_id: evaluation.metrics[metric_id].support_status
            for metric_id in required_downstream
        }
        if all(status is SupportStatus.SUPPORTED for status in downstream_statuses.values()):
            support = SupportStatus.SUPPORTED
        elif all(
            status in {SupportStatus.SUPPORTED, SupportStatus.PARTIAL}
            for status in downstream_statuses.values()
        ):
            support = SupportStatus.PARTIAL
        else:
            support = SupportStatus.BLOCKED
        representation = (
            prepared.variant_scenarios
            if context.variant_id in EXP2A_VARIANTS
            else prepared.variant_consequences
        )
        return build_exp2_result(
            variant_id=context.variant_id,
            dataset_id=context.dataset_id,
            seed=context.seed,
            artifact_version=(
                f"M1:{context.m1_artifact_version}|M2:{context.m2_artifact_version}"
            ),
            scenario_hash=prepared.reference_scenarios.source_scenario_hash,
            config_hash=context.config_hash,
            metrics=evaluation.metrics,
            support_status=support,
            model_versions=context.model_versions,
            provenance={
                "reference_variant_id": prepared.reference_variant_id,
                "source_m1_scenario_hash": prepared.reference_scenarios.source_scenario_hash,
                "source_m2_artifact_hash": prepared.reference_consequences.source_artifact_hash,
                "representation_hash": representation.representation_hash,
                "m3_envelope_hashes": tuple(item.envelope_hash for item in execution.variant_m3),
                "m4_risk_envelope_hashes": tuple(item.risk_envelope_hash for item in execution.variant_m4),
                "downstream_interface": "M3_ACTION_RESPONSE_THEN_M4_RESIDUAL_RISK",
                "action_set_modified": False,
                "response_registry_modified": False,
                "monetary_mapping_modified": False,
                "m4_bypassed": False,
            },
        )


__all__ = [
    "Exp2DownstreamInterface",
    "Exp2Evaluation",
    "Exp2Execution",
    "Exp2Protocol",
    "Exp2RunContext",
    "PreparedExp2Run",
]
