"""Exp1 runner: information-role necessity, not warning detection."""

from exp.common.context import (
    ExecutionTier,
    ExperimentContext,
    build_context_result,
    fast_context,
    real_fast_context,
)
from exp.common.real_fast import assert_real_fast_context, blocked_gate, m4_result_unit
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus

from .variants import EXP1_VARIANTS, EXP1_VARIANTS_WITH_SENSITIVITY, variant_definition


class Exp1Runner:
    experiment = "EXP1"
    variants = EXP1_VARIANTS
    headline_metrics = (
        "TOP1_ACTION_DISAGREEMENT",
        "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK",
        "CRPS_PRIMITIVE_TARGET",
        "BRIER_PRINCIPAL_DELAY_EVENT",
    )

    def execute_fast(
        self,
        *,
        dataset: str = "data2_2019",
        split: str = "DEVELOPMENT",
        seed: int = 0,
        include_sensitivity: bool = False,
    ):
        context = fast_context(dataset_id=dataset, split=split, seed=seed, experiment_id=self.experiment)
        return tuple(self.execute(context, variant) for variant in self.variants_for(
            include_sensitivity=include_sensitivity))

    def variants_for(self, *, include_sensitivity: bool = False) -> tuple[str, ...]:
        return EXP1_VARIANTS_WITH_SENSITIVITY if include_sensitivity else self.variants

    def execute_real_fast(
        self,
        *,
        context: ExperimentContext | None = None,
        seed: int = 0,
        include_sensitivity: bool = False,
    ):
        bound = context or real_fast_context(seed=seed)
        assert_real_fast_context(bound)
        return tuple(self.execute(bound, variant) for variant in self.variants_for(
            include_sensitivity=include_sensitivity))

    def execute(self, context: ExperimentContext, variant_id: str):
        if context.execution_tier is ExecutionTier.REAL_DATA_FAST:
            return self._execute_real_fast(context, variant_id)
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
                unit="CONSTRUCTED_LOSS_UNIT", support_status=SupportStatus.NOT_RUN,
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

    def _execute_real_fast(self, context: ExperimentContext, variant_id: str):
        assert_real_fast_context(context)
        definition = variant_definition(variant_id)
        m1_blocker = blocked_gate(context, "M1_CHECKPOINT")
        m4_blocker = blocked_gate(context, "M4_TAIL", "M4_MAPPING", "M4_RANKING")
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED, metadata=definition,
            ),
            "REAL_COHORT_BINDING": MetricObservation(
                metric_id="REAL_COHORT_BINDING", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={
                    "cohort_hash": context.lineage["cohort_hash"],
                    "selection_rule": context.lineage["selection_rule"],
                    "node_count": context.node_count,
                    "episode_count": context.episode_count,
                },
            ),
            "STATE_REPRESENTATION_DIFFERENCE": MetricObservation(
                metric_id="STATE_REPRESENTATION_DIFFERENCE", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m1_blocker or "M1_V2_PREDICTIVE_OUTPUT_REQUIRED"},
            ),
            "CRPS_PRIMITIVE_TARGET": MetricObservation(
                metric_id="CRPS_PRIMITIVE_TARGET", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m1_blocker or "M1_V2_PREDICTIVE_OUTPUT_REQUIRED"},
            ),
            "TOP1_ACTION_DISAGREEMENT": MetricObservation(
                metric_id="TOP1_ACTION_DISAGREEMENT", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m4_blocker or "M2_M3_M4_MULTI_ACTION_OUTPUT_REQUIRED"},
            ),
            "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK": MetricObservation(
                metric_id="EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", level=MetricLevel.DECISION, value=None,
                unit=m4_result_unit(context), support_status=SupportStatus.NOT_RUN,
                metadata={
                    "reason": m4_blocker or "M2_M3_M4_RISK_OUTPUT_REQUIRED",
                    "mapping_id": context.registry_hashes["M4_MAPPING_DESIGN"],
                    "mapping_hash": context.registry_hashes["M4_MAPPING_DESIGN"],
                },
            ),
        }
        return build_context_result(
            context=context, experiment_id=self.experiment, variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.PARTIAL,
            provenance={
                "scientific_question": "WHY_CROSS_STAGE_INFORMATION_SHARING_AND_HISTORY_DEPENDENCE",
                "subexperiment": definition["subexperiment"],
                "real_data_execution": True,
                "state_metrics_status": "BLOCKED_M1_V2_ARTIFACT",
                "decision_metrics_status": "BLOCKED_SHARED_M4_GATE",
                "M3_NON_A00_INTERPRETATION": "CONDITIONAL_NON_CAUSAL_NON_AUTHORITATIVE",
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
