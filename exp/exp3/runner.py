"""Exp3 runner: refresh and state-vintage synchronization."""

from __future__ import annotations

from exp.common.context import ExperimentContext, build_context_result, fast_context
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus
from exp.common.runner import BaseRunner

from .protocol import EXP3_VARIANTS, variant_definition


class Exp3Runner(BaseRunner):
    experiment = "EXP3"
    variants = EXP3_VARIANTS
    protocol_variants = EXP3_VARIANTS
    headline_metrics = (
        "RECOMMENDATION_EXECUTABLE_RATE", "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK",
        "FLIGHT_DELAY_MINUTES", "PASSENGER_DELAY_MINUTES", "TOP1_ACTION_AGREEMENT",
    )

    def execute_fast(self, *, dataset: str = "data2_2019", split: str = "DEVELOPMENT", seed: int = 0):
        context = fast_context(dataset_id=dataset, split=split, seed=seed, experiment_id=self.experiment)
        return tuple(self.execute(context, variant) for variant in self.variants)

    def execute(self, context: ExperimentContext, variant_id: str):
        definition = variant_definition(variant_id)
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.SYSTEM, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED, metadata=definition,
            ),
            "RECOMMENDATION_EXECUTABLE_RATE": MetricObservation(
                metric_id="RECOMMENDATION_EXECUTABLE_RATE", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_FORMAL_MULTI_ACTION_COHORT"},
            ),
            "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK": MetricObservation(
                metric_id="EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", level=MetricLevel.DECISION, value=None,
                unit="RMB", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE"},
            ),
            "TOP1_ACTION_AGREEMENT": MetricObservation(
                metric_id="TOP1_ACTION_AGREEMENT", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "NOT_RUN_SHARED_M4_GATE"},
            ),
        }
        return build_context_result(
            context=context, experiment_id=self.experiment, variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.NOT_RUN,
            provenance={
                "scientific_question": "HOW_RETAINED_INFORMATION_EVOLVES_IN_ROLLING_PROCESS",
                "decision_process_only": True, "rolling_novelty_claim": False,
                "one_shot_anchor_rule": "FIRST_NODE_WITH_TWO_COMPARABLE_ACTIONS_AND_ONE_NON_A00",
            },
        )


__all__ = ["Exp3Runner"]
