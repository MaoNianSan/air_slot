"""Exp4 runner: complete-system adequacy contracts."""

from __future__ import annotations

from exp.common.context import ExperimentContext, build_context_result, fast_context
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus
from exp.common.runner import BaseRunner

from .protocol import EXP4_VARIANTS, variant_definition


class Exp4Runner(BaseRunner):
    experiment = "EXP4"
    variants = EXP4_VARIANTS
    protocol_variants = EXP4_VARIANTS
    headline_metrics = (
        "MAE_MINUTES", "CRPS", "FORMAL_RECOMMENDATION_AVAILABILITY",
        "EXECUTION_FEASIBLE_RATE", "STRUCTURAL_FEASIBLE_RATE",
        "FACTUAL_CONSISTENCY_RATE", "EVIDENCE_SUPPORTED_RATE",
        "E2E_P50_SECONDS", "E2E_P95_SECONDS", "E2E_P99_SECONDS",
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
            "MAE_MINUTES": MetricObservation(
                metric_id="MAE_MINUTES", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_OBSERVED_TARGET_ARTIFACT"},
            ),
            "CRPS": MetricObservation(
                metric_id="CRPS", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_FROZEN_PREDICTIVE_DISTRIBUTION"},
            ),
            "FORMAL_RECOMMENDATION_AVAILABILITY": MetricObservation(
                metric_id="FORMAL_RECOMMENDATION_AVAILABILITY", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "M4_MATERIAL_COVERAGE_UNFROZEN"},
            ),
            "E2E_P95_SECONDS": MetricObservation(
                metric_id="E2E_P95_SECONDS", level=MetricLevel.SYSTEM, value=None,
                unit="seconds", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_PIPELINE_TIMINGS"},
            ),
        }
        return build_context_result(
            context=context, experiment_id=self.experiment, variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.NOT_RUN,
            provenance={
                "scientific_question": "DOES_THE_COMPLETE_CHAIN_WORK_ADEQUATELY",
                "adequacy_not_novelty": True,
                "data1_portability_role": "WITHIN_DATASET_FULL_MINUS_LIGHTGBM",
                "llm_audit_role": "AUXILIARY_ONLY",
            },
        )


__all__ = ["Exp4Runner"]
