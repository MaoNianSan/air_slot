"""Exp1 runner: information-role necessity, not warning detection."""

from exp.common.context import ExperimentContext, build_context_result, fast_context
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus

from .variants import EXP1_VARIANTS, variant_definition


class Exp1Runner:
    experiment = "EXP1"
    variants = EXP1_VARIANTS
    headline_metrics = (
        "TOP1_ACTION_DISAGREEMENT",
        "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK",
        "CRPS_PRIMITIVE_TARGET",
        "BRIER_PRINCIPAL_DELAY_EVENT",
    )

    def execute_fast(self, *, dataset: str = "data2_2019", split: str = "DEVELOPMENT", seed: int = 0):
        context = fast_context(dataset_id=dataset, split=split, seed=seed, experiment_id=self.experiment)
        return tuple(self.execute(context, variant) for variant in self.variants)

    def execute(self, context: ExperimentContext, variant_id: str):
        definition = variant_definition(variant_id)
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED, metadata=definition,
            ),
            "TOP1_ACTION_DISAGREEMENT": MetricObservation(
                metric_id="TOP1_ACTION_DISAGREEMENT", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_FROZEN_MULTI_ACTION_M4_OUTPUT"},
            ),
            "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK": MetricObservation(
                metric_id="EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", level=MetricLevel.DECISION, value=None,
                unit="RMB", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE"},
            ),
            "CRPS_PRIMITIVE_TARGET": MetricObservation(
                metric_id="CRPS_PRIMITIVE_TARGET", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_FROZEN_OBSERVATION_ARTIFACT"},
            ),
        }
        return build_context_result(
            context=context, experiment_id=self.experiment, variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.NOT_RUN,
            provenance={
                "scientific_question": "WHY_CROSS_STAGE_INFORMATION_SHARING_AND_HISTORY_DEPENDENCE",
                "subexperiment": definition["subexperiment"],
                "warning_metrics_headline": False,
                "shared_state_efficiency_headline": False,
            },
        )

    def run(self, rows=None, *, smoke=False, **kwargs):
        if smoke:
            return self.execute_fast(
                dataset=kwargs.get("dataset", "data2_2019"),
                split=kwargs.get("split", "DEVELOPMENT"),
                seed=kwargs.get("seed", 0),
            )
        raise RuntimeError("EXP1_TYPED_CONTEXT_EXECUTION_REQUIRED")
