import pytest

from exp.common.evaluator import (
    EvaluationSuite,
    MetricDefinition,
    default_evaluation_suite,
)
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus


def test_default_suite_registers_all_three_metric_levels_without_formulas():
    suite = default_evaluation_suite()

    assert set(suite.metric_ids(MetricLevel.STATE)) == {
        "STATE_CALIBRATION", "STATE_CRPS", "STATE_COVERAGE",
    }
    assert set(suite.metric_ids(MetricLevel.DECISION)) == {
        "DECISION_ACTION_DISAGREEMENT",
        "DECISION_RANKING_CHANGE",
        "DECISION_RISK_DIFFERENCE",
    }
    assert set(suite.metric_ids(MetricLevel.SYSTEM)) == {
        "SYSTEM_RUNTIME", "SYSTEM_LATENCY",
    }
    with pytest.raises(RuntimeError, match="METRIC_IMPLEMENTATION_NOT_REGISTERED"):
        suite.evaluate("STATE_CRPS", payload={})


def test_metric_registration_and_typed_evaluation():
    suite = EvaluationSuite()
    definition = MetricDefinition(
        metric_id="SYSTEM_FIXTURE",
        level=MetricLevel.SYSTEM,
        description="Interface test metric",
        unit="seconds",
        claim_scope="TEST_ONLY",
    )
    suite.register(definition)
    suite.attach(
        definition.metric_id,
        lambda payload: MetricObservation(
            metric_id=definition.metric_id,
            level=definition.level,
            value=payload["value"],
            unit=definition.unit,
            support_status=SupportStatus.NOT_RUN,
            metadata={"fixture": True},
        ),
    )

    observation = suite.evaluate(definition.metric_id, {"value": 0.0})
    assert observation.value == 0.0
    assert observation.support_status is SupportStatus.NOT_RUN


def test_metric_registry_rejects_duplicate_ids():
    definition = MetricDefinition(
        metric_id="STATE_FIXTURE",
        level=MetricLevel.STATE,
        description="Interface test metric",
        unit="unitless",
        claim_scope="TEST_ONLY",
    )
    suite = EvaluationSuite()
    suite.register(definition)
    with pytest.raises(ValueError, match="METRIC_ID_ALREADY_REGISTERED"):
        suite.register(definition)

