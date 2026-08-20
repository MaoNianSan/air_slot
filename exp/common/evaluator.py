"""Metric registration interfaces; no paper metric is implemented here."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .result_schema import MetricLevel, MetricObservation


class MetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_id: str = Field(min_length=1)
    level: MetricLevel
    description: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    claim_scope: str = Field(min_length=1)


MetricEvaluator = Callable[[Any], MetricObservation]


class EvaluationSuite:
    """Registry of metric definitions and optional future implementations."""

    def __init__(self):
        self._definitions: dict[str, MetricDefinition] = {}
        self._evaluators: dict[str, MetricEvaluator] = {}

    def register(
        self,
        definition: MetricDefinition,
        evaluator: MetricEvaluator | None = None,
    ) -> MetricDefinition:
        if not isinstance(definition, MetricDefinition):
            raise TypeError("METRIC_DEFINITION_TYPE_REQUIRED")
        if definition.metric_id in self._definitions:
            raise ValueError(f"METRIC_ID_ALREADY_REGISTERED:{definition.metric_id}")
        if evaluator is not None and not callable(evaluator):
            raise TypeError("METRIC_EVALUATOR_CALLABLE_REQUIRED")
        self._definitions[definition.metric_id] = definition
        if evaluator is not None:
            self._evaluators[definition.metric_id] = evaluator
        return definition

    def attach(self, metric_id: str, evaluator: MetricEvaluator) -> None:
        self.get(metric_id)
        if metric_id in self._evaluators:
            raise ValueError(f"METRIC_EVALUATOR_ALREADY_REGISTERED:{metric_id}")
        if not callable(evaluator):
            raise TypeError("METRIC_EVALUATOR_CALLABLE_REQUIRED")
        self._evaluators[metric_id] = evaluator

    def get(self, metric_id: str) -> MetricDefinition:
        try:
            return self._definitions[metric_id]
        except KeyError as exc:
            raise KeyError(f"METRIC_ID_NOT_REGISTERED:{metric_id}") from exc

    def definitions(
        self, level: MetricLevel | str | None = None,
    ) -> tuple[MetricDefinition, ...]:
        selected_level = None if level is None else MetricLevel(level)
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions)
            if selected_level is None
            or self._definitions[key].level is selected_level
        )

    def metric_ids(self, level: MetricLevel | str | None = None) -> tuple[str, ...]:
        return tuple(item.metric_id for item in self.definitions(level))

    def evaluate(self, metric_id: str, payload: Any) -> MetricObservation:
        definition = self.get(metric_id)
        evaluator = self._evaluators.get(metric_id)
        if evaluator is None:
            raise RuntimeError(f"METRIC_IMPLEMENTATION_NOT_REGISTERED:{metric_id}")
        observation = evaluator(payload)
        if not isinstance(observation, MetricObservation):
            raise TypeError("METRIC_EVALUATOR_RESULT_TYPE_INVALID")
        if observation.metric_id != definition.metric_id:
            raise ValueError("METRIC_EVALUATOR_ID_MISMATCH")
        if observation.level is not definition.level:
            raise ValueError("METRIC_EVALUATOR_LEVEL_MISMATCH")
        if observation.unit != definition.unit:
            raise ValueError("METRIC_EVALUATOR_UNIT_MISMATCH")
        return observation

    def evaluate_many(
        self, metric_ids: Iterable[str], payload: Any,
    ) -> dict[str, MetricObservation]:
        return {metric_id: self.evaluate(metric_id, payload) for metric_id in metric_ids}


def default_evaluation_suite() -> EvaluationSuite:
    """Declare the required metric surface without supplying formulas."""

    suite = EvaluationSuite()
    declarations = (
        ("STATE_CALIBRATION", MetricLevel.STATE, "Calibration interface", "DECLARED_BY_PROTOCOL"),
        ("STATE_CRPS", MetricLevel.STATE, "CRPS interface", "DECLARED_BY_PROTOCOL"),
        ("STATE_COVERAGE", MetricLevel.STATE, "Predictive coverage interface", "DECLARED_BY_PROTOCOL"),
        ("DECISION_ACTION_DISAGREEMENT", MetricLevel.DECISION, "Action disagreement interface", "rate"),
        ("DECISION_RANKING_CHANGE", MetricLevel.DECISION, "Ranking change interface", "rate"),
        ("DECISION_RISK_DIFFERENCE", MetricLevel.DECISION, "Risk difference interface", "DECLARED_BY_PROTOCOL"),
        ("SYSTEM_RUNTIME", MetricLevel.SYSTEM, "Runtime interface", "seconds"),
        ("SYSTEM_LATENCY", MetricLevel.SYSTEM, "Latency interface", "seconds"),
    )
    for metric_id, level, description, unit in declarations:
        suite.register(MetricDefinition(
            metric_id=metric_id,
            level=level,
            description=description,
            unit=unit,
            claim_scope="INTERFACE_ONLY_NOT_A_PAPER_RESULT",
        ))
    return suite


__all__ = [
    "EvaluationSuite",
    "MetricDefinition",
    "MetricEvaluator",
    "default_evaluation_suite",
]
