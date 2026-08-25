"""Exp4 runner: complete-system adequacy contracts."""

from __future__ import annotations

from exp.common.context import (
    ExecutionTier,
    ExperimentContext,
    build_context_result,
    fast_context,
    real_fast_context,
)
from exp.common.real_fast import (
    assert_real_fast_context,
    blocked_gate,
    replay_latency_seconds,
)
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus
from exp.common.runner import BaseRunner

from .metrics import latency_percentiles
from .protocol import (
    EVALUATION_LEAD_MINUTES,
    MODEL_HORIZON_MINUTES,
    EXP4_VARIANTS,
    PredictiveBaseline,
    variant_definition,
)


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

    def execute_real_fast(self, *, context: ExperimentContext | None = None, seed: int = 0):
        bound = context or real_fast_context(seed=seed)
        assert_real_fast_context(bound)
        return tuple(self.execute(bound, variant) for variant in self.variants)

    def execute(self, context: ExperimentContext, variant_id: str):
        if context.execution_tier is ExecutionTier.REAL_DATA_FAST:
            return self._execute_real_fast(context, variant_id)
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
                metadata={"reason": "M4_MAPPING_AND_TAIL_GATED"},
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

    def _execute_real_fast(self, context: ExperimentContext, variant_id: str):
        assert_real_fast_context(context)
        definition = variant_definition(variant_id)
        m1_blocker = blocked_gate(context, "M1_CHECKPOINT")
        m4_blocker = blocked_gate(context, "M4_TAIL", "M4_MAPPING", "M4_RANKING")
        latency = latency_percentiles(
            tuple({"E2E_latency": value} for value in replay_latency_seconds(context)),
            "E2E_latency",
        )
        p95 = latency["p95"]
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.SYSTEM, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED, metadata=definition,
            ),
            "REAL_COHORT_BINDING": MetricObservation(
                metric_id="REAL_COHORT_BINDING", level=MetricLevel.SYSTEM, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={
                    "cohort_hash": context.lineage["cohort_hash"],
                    "episode_count": context.episode_count,
                    "node_count": context.node_count,
                },
            ),
            "LEAD_TIME_CONTRACT": MetricObservation(
                metric_id="LEAD_TIME_CONTRACT", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={
                    "evaluation_lead_minutes": EVALUATION_LEAD_MINUTES,
                    "model_horizon_minutes": MODEL_HORIZON_MINUTES,
                    "distinct_variables_required": True,
                },
            ),
            "PREDICTIVE_BASELINE_BINDING": MetricObservation(
                metric_id="PREDICTIVE_BASELINE_BINDING", level=MetricLevel.STATE, value=None,
                unit="boolean", support_status=SupportStatus.NOT_RUN,
                metadata={
                    "reason": m1_blocker or "REAL_PREDICTIVE_ARTIFACTS_REQUIRED",
                    "required_baselines": tuple(item.value for item in PredictiveBaseline),
                },
            ),
            "MAE_MINUTES": MetricObservation(
                metric_id="MAE_MINUTES", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m1_blocker or "REAL_PREDICTIVE_ARTIFACTS_REQUIRED"},
            ),
            "CRPS": MetricObservation(
                metric_id="CRPS", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m1_blocker or "REAL_PREDICTIVE_ARTIFACTS_REQUIRED"},
            ),
            "FORMAL_RECOMMENDATION_AVAILABILITY": MetricObservation(
                metric_id="FORMAL_RECOMMENDATION_AVAILABILITY", level=MetricLevel.DECISION,
                value=None, unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m4_blocker or "M3_M4_DECISION_OUTPUT_REQUIRED"},
            ),
            "E2E_P50_SECONDS": MetricObservation(
                metric_id="E2E_P50_SECONDS", level=MetricLevel.SYSTEM, value=latency["p50"],
                unit="seconds", support_status=SupportStatus.PARTIAL,
                metadata={"scope": "REAL_PRE_REPLAY_BINDING_ONLY", "complete_chain": False},
            ),
            "E2E_P95_SECONDS": MetricObservation(
                metric_id="E2E_P95_SECONDS", level=MetricLevel.SYSTEM, value=p95,
                unit="seconds", support_status=SupportStatus.PARTIAL,
                metadata={"scope": "REAL_PRE_REPLAY_BINDING_ONLY", "complete_chain": False},
            ),
            "E2E_P99_SECONDS": MetricObservation(
                metric_id="E2E_P99_SECONDS", level=MetricLevel.SYSTEM, value=latency["p99"],
                unit="seconds", support_status=SupportStatus.PARTIAL,
                metadata={"scope": "REAL_PRE_REPLAY_BINDING_ONLY", "complete_chain": False},
            ),
            "WITHIN_60S": MetricObservation(
                metric_id="WITHIN_60S", level=MetricLevel.SYSTEM, value=p95 is not None and p95 <= 60,
                unit="boolean", support_status=SupportStatus.PARTIAL,
                metadata={"budget_seconds": 60, "scope": "REAL_PRE_REPLAY_BINDING_ONLY"},
            ),
            "WITHIN_120S": MetricObservation(
                metric_id="WITHIN_120S", level=MetricLevel.SYSTEM, value=p95 is not None and p95 <= 120,
                unit="boolean", support_status=SupportStatus.PARTIAL,
                metadata={"budget_seconds": 120, "scope": "REAL_PRE_REPLAY_BINDING_ONLY"},
            ),
            "WITHIN_300S": MetricObservation(
                metric_id="WITHIN_300S", level=MetricLevel.SYSTEM, value=p95 is not None and p95 <= 300,
                unit="boolean", support_status=SupportStatus.PARTIAL,
                metadata={"budget_seconds": 300, "scope": "REAL_PRE_REPLAY_BINDING_ONLY"},
            ),
        }
        return build_context_result(
            context=context, experiment_id=self.experiment, variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.PARTIAL,
            provenance={
                "scientific_question": "DOES_THE_COMPLETE_CHAIN_WORK_ADEQUATELY",
                "adequacy_not_novelty": True,
                "real_data_execution": True,
                "predictive_status": "BLOCKED_M1_V2_ARTIFACT",
                "decision_validity_status": "BLOCKED_SHARED_M4_GATE",
                "latency_status": "PARTIAL_REAL_PRE_REPLAY_BINDING_ONLY",
                "evaluation_lead_minutes": EVALUATION_LEAD_MINUTES,
                "model_horizon_minutes": MODEL_HORIZON_MINUTES,
            },
        )


__all__ = ["Exp4Runner"]
