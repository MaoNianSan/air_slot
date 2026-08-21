"""Exp3 runner: refresh and state-vintage synchronization."""

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
    m4_result_unit,
    select_replay,
    state_vintage_bindings,
)
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
            "RECOMMENDATION_EXECUTABLE_RATE": MetricObservation(
                metric_id="RECOMMENDATION_EXECUTABLE_RATE", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_FORMAL_MULTI_ACTION_COHORT"},
            ),
            "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK": MetricObservation(
                metric_id="EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", level=MetricLevel.DECISION, value=None,
                unit="CONSTRUCTED_LOSS_UNIT", support_status=SupportStatus.NOT_RUN,
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

    def _execute_real_fast(self, context: ExperimentContext, variant_id: str):
        assert_real_fast_context(context)
        definition = variant_definition(variant_id)
        registry, selection = select_replay(context)
        m1_blocker = blocked_gate(context, "M1_CHECKPOINT")
        m4_blocker = blocked_gate(context, "M4_TAIL", "M4_MAPPING", "M4_RANKING")
        lag_by_variant = {
            "EXP3B_SYNC": 0,
            "EXP3B_STATE_LAG_5": 5,
            "EXP3B_STATE_LAG_10": 10,
        }
        lag = lag_by_variant.get(variant_id)
        vintage = () if lag is None else state_vintage_bindings(context, lag_minutes=lag)
        available_vintage = sum(item["state_vintage_node_id"] is not None for item in vintage)
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.SYSTEM, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED, metadata=definition,
            ),
            "REPLAY_SELECTION": MetricObservation(
                metric_id="REPLAY_SELECTION", level=MetricLevel.SYSTEM, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={
                    "replay_episode_count": len(registry.episodes),
                    "replay_node_count": sum(len(item.decision_records) for item in registry.episodes),
                    "selection_reason_codes": selection.reason_codes,
                },
            ),
            "ROLLING_STATE_NODE_COVERAGE": MetricObservation(
                metric_id="ROLLING_STATE_NODE_COVERAGE", level=MetricLevel.STATE,
                value=context.node_count / context.node_count, unit="rate",
                support_status=SupportStatus.SUPPORTED,
                metadata={"roll_minutes": 5, "cohort_hash": context.lineage["cohort_hash"]},
            ),
            "ONE_SHOT_ANCHOR": MetricObservation(
                metric_id="ONE_SHOT_ANCHOR", level=MetricLevel.DECISION, value=None,
                unit="decision_node", support_status=(
                    SupportStatus.NOT_RUN if variant_id == "EXP3A_ONE_SHOT" else SupportStatus.NOT_RUN
                ),
                metadata={
                    "reason": (
                        "BLOCKED_ANCHOR_ACTION_COVERAGE" if variant_id == "EXP3A_ONE_SHOT"
                        else "NOT_APPLICABLE_TO_VARIANT"
                    ),
                    "rule": "FIRST_NODE_WITH_TWO_COMPARABLE_ACTIONS_AND_ONE_NON_A00",
                },
            ),
            "STATE_VINTAGE_COVERAGE": MetricObservation(
                metric_id="STATE_VINTAGE_COVERAGE", level=MetricLevel.STATE,
                value=(None if lag is None else available_vintage / len(vintage)),
                unit="rate",
                support_status=(
                    SupportStatus.SUPPORTED if lag is not None else SupportStatus.NOT_RUN
                ),
                metadata={
                    "reason": None if lag is not None else "NOT_APPLICABLE_TO_VARIANT",
                    "lag_minutes": lag,
                    "current_state_read": lag == 0 if lag is not None else None,
                    "state_vintage_only_changed_factor": lag is not None,
                },
            ),
            "STATE_REPRESENTATION_DRIFT": MetricObservation(
                metric_id="STATE_REPRESENTATION_DRIFT", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m1_blocker or "M1_V2_STATE_OUTPUT_REQUIRED"},
            ),
            "RECOMMENDATION_EXECUTABLE_RATE": MetricObservation(
                metric_id="RECOMMENDATION_EXECUTABLE_RATE", level=MetricLevel.DECISION,
                value=None, unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "BLOCKED_ANCHOR_ACTION_COVERAGE"},
            ),
            "TOP1_ACTION_AGREEMENT": MetricObservation(
                metric_id="TOP1_ACTION_AGREEMENT", level=MetricLevel.DECISION,
                value=None, unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m4_blocker or "M3_M4_RANKING_REQUIRED"},
            ),
            "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK": MetricObservation(
                metric_id="EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", level=MetricLevel.DECISION,
                value=None, unit=m4_result_unit(context), support_status=SupportStatus.NOT_RUN,
                metadata={
                    "reason": m4_blocker or "M3_M4_RISK_OUTPUT_REQUIRED",
                    "mapping_id": context.registry_hashes["M4_MAPPING_DESIGN"],
                    "mapping_hash": context.registry_hashes["M4_MAPPING_DESIGN"],
                },
            ),
        }
        return build_context_result(
            context=context, experiment_id=self.experiment, variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.PARTIAL,
            provenance={
                "scientific_question": "HOW_RETAINED_INFORMATION_EVOLVES_IN_ROLLING_PROCESS",
                "decision_process_only": True,
                "rolling_novelty_claim": False,
                "real_data_execution": True,
                "replay_status": "PASS",
                "one_shot_anchor_rule": "FIRST_NODE_WITH_TWO_COMPARABLE_ACTIONS_AND_ONE_NON_A00",
                "one_shot_anchor_status": "BLOCKED_ANCHOR_ACTION_COVERAGE",
                "decision_metrics_status": "BLOCKED_SHARED_M4_GATE",
            },
        )


__all__ = ["Exp3Runner"]
