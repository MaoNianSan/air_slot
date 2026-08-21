"""Exp2 entry points.

The legacy scalar-row runner remains available for non-scientific smoke tests.
Every Development or formal Exp2 execution must use the typed protocol route.
"""

from __future__ import annotations

from pathlib import Path

from exp.common.context import (
    ExecutionTier,
    ExperimentContext,
    build_context_result,
    fast_context,
    real_fast_context,
)
from exp.common.real_fast import assert_real_fast_context, blocked_gate, m4_result_unit
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus
from exp.common.runner import BaseRunner, ExperimentRunner
from model.common.errors import ContractError

from .execution.artifact_loader import ArtifactScope, Exp2ArtifactLoader
from .execution.downstream_binding import Exp2DownstreamExecutor, M3Executor, M4Evaluator
from .execution.execution_manifest import Exp2ExecutionManifest
from .protocol import (
    MARGINAL_WEIGHT_POLICY,
    POINT_REPRESENTATIVE_RULE,
    Exp2Protocol,
    Exp2RunContext,
)
from .variants import EXP2_VARIANT_IDS


class Exp2Runner(BaseRunner):
    experiment = "EXP2"
    variants = EXP2_VARIANT_IDS
    protocol_variants = EXP2_VARIANT_IDS
    reference_evaluator = "COMPLETE_REFERENCE_MODEL_CONSISTENCY_DIAGNOSTIC_ONLY"
    headline_metrics = (
        "CRPS", "BRIER", "CALIBRATION", "COVERAGE", "VARIOGRAM_SCORE",
        "TOP1_ACTION_DISAGREEMENT", "ACTION_FAMILY_COMPOSITION",
    )

    def run(self, rows, *, smoke=False, **kwargs):
        if not smoke:
            raise ContractError("EXP2_TYPED_PROTOCOL_EXECUTION_REQUIRED")
        return super().run(rows, smoke=True, **kwargs)

    def execute_fast(self, *, dataset: str = "data2_2019", split: str = "DEVELOPMENT", seed: int = 0):
        context = fast_context(dataset_id=dataset, split=split, seed=seed, experiment_id=self.experiment)
        return tuple(self._execute_context(context, variant) for variant in self.variants)

    def execute_real_fast(self, *, context: ExperimentContext | None = None, seed: int = 0):
        bound = context or real_fast_context(seed=seed)
        assert_real_fast_context(bound)
        return tuple(self._execute_context(bound, variant) for variant in self.variants)

    def execute(self, context: Exp2RunContext | ExperimentContext):
        """Execute one frozen representation contrast through M3 then M4."""
        if isinstance(context, ExperimentContext):
            raise TypeError("EXP2_CONTEXT_EXECUTION_REQUIRES_VARIANT_ID")
        return ExperimentRunner().execute(Exp2Protocol(), context=context)

    @staticmethod
    def _execute_context(context: ExperimentContext, variant_id: str):
        if context.execution_tier is ExecutionTier.REAL_DATA_FAST:
            return Exp2Runner._execute_real_context(context, variant_id)
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={"variant_id": variant_id, "representation_only": True},
            ),
            "VARIOGRAM_SCORE": MetricObservation(
                metric_id="VARIOGRAM_SCORE", level=MetricLevel.STATE, value=None,
                unit="squared_delay_difference", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "FAST_CONTRACT_RUN_NO_FROZEN_OBSERVATIONS"},
            ),
            "TOP1_ACTION_DISAGREEMENT": MetricObservation(
                metric_id="TOP1_ACTION_DISAGREEMENT", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "NOT_RUN_SHARED_M4_GATE"},
            ),
            "COMPLETE_REFERENCE_J_DIAGNOSTIC": MetricObservation(
                metric_id="COMPLETE_REFERENCE_J_DIAGNOSTIC", level=MetricLevel.DECISION, value=None,
                unit="CONSTRUCTED_LOSS_UNIT", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": "INTERNAL_DIAGNOSTIC_NOT_INDEPENDENT_ACTION_EFFECT_EVIDENCE"},
            ),
        }
        return build_context_result(
            context=context, experiment_id="EXP2", variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.NOT_RUN,
            provenance={
                "scientific_question": "HOW_MUCH_AND_WHAT_INFORMATION_STRUCTURE_IS_SUFFICIENT",
                "representation_only": True,
                "complete_reference_j_status": "INTERNAL_NOT_INDEPENDENT_ACTION_EFFECT_EVIDENCE",
            },
        )

    @staticmethod
    def _execute_real_context(context: ExperimentContext, variant_id: str):
        assert_real_fast_context(context)
        m1_blocker = blocked_gate(context, "M1_CHECKPOINT")
        m2_blocker = blocked_gate(context, "M2_SEVEN_COMPONENT")
        m4_blocker = blocked_gate(context, "M4_TAIL", "M4_MAPPING", "M4_RANKING")
        representation_blocker = m1_blocker if variant_id.startswith("EXP2A_") else m2_blocker
        metrics = {
            "VARIANT_CONTRACT": MetricObservation(
                metric_id="VARIANT_CONTRACT", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={
                    "variant_id": variant_id,
                    "point_representative_rule": POINT_REPRESENTATIVE_RULE,
                    "marginal_weight_policy": MARGINAL_WEIGHT_POLICY,
                },
            ),
            "REAL_COHORT_BINDING": MetricObservation(
                metric_id="REAL_COHORT_BINDING", level=MetricLevel.STATE, value=True,
                unit="boolean", support_status=SupportStatus.SUPPORTED,
                metadata={
                    "cohort_hash": context.lineage["cohort_hash"],
                    "selection_rule": context.lineage["selection_rule"],
                    "episode_count": context.episode_count,
                    "node_count": context.node_count,
                },
            ),
            "CRPS": MetricObservation(
                metric_id="CRPS", level=MetricLevel.STATE, value=None,
                unit="minutes", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": representation_blocker or "FROZEN_M1_SCENARIOS_AND_OBSERVATIONS_REQUIRED"},
            ),
            "BRIER": MetricObservation(
                metric_id="BRIER", level=MetricLevel.STATE, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": representation_blocker or "FROZEN_M1_EVENT_PROBABILITIES_REQUIRED"},
            ),
            "CALIBRATION": MetricObservation(
                metric_id="CALIBRATION", level=MetricLevel.STATE, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": representation_blocker or "FROZEN_M1_PREDICTIONS_REQUIRED"},
            ),
            "COVERAGE": MetricObservation(
                metric_id="COVERAGE", level=MetricLevel.STATE, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": representation_blocker or "FROZEN_M1_PREDICTIONS_REQUIRED"},
            ),
            "VARIOGRAM_SCORE": MetricObservation(
                metric_id="VARIOGRAM_SCORE", level=MetricLevel.STATE, value=None,
                unit="squared_delay_difference", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": representation_blocker or "FROZEN_JOINT_SCENARIOS_AND_OBSERVATIONS_REQUIRED"},
            ),
            "MARGINAL_WEIGHT_CHECK": MetricObservation(
                metric_id="MARGINAL_WEIGHT_CHECK", level=MetricLevel.STATE, value=None,
                unit="boolean", support_status=SupportStatus.NOT_RUN,
                metadata={
                    "reason": (
                        representation_blocker if variant_id == "EXP2A_MARGINAL"
                        else "NOT_APPLICABLE_TO_VARIANT"
                    ),
                    "policy": MARGINAL_WEIGHT_POLICY,
                },
            ),
            "TOP1_ACTION_DISAGREEMENT": MetricObservation(
                metric_id="TOP1_ACTION_DISAGREEMENT", level=MetricLevel.DECISION, value=None,
                unit="rate", support_status=SupportStatus.NOT_RUN,
                metadata={"reason": m4_blocker or "M3_M4_DOWNSTREAM_OUTPUT_REQUIRED"},
            ),
            "COMPLETE_REFERENCE_J_DIAGNOSTIC": MetricObservation(
                metric_id="COMPLETE_REFERENCE_J_DIAGNOSTIC", level=MetricLevel.DECISION, value=None,
                unit=m4_result_unit(context), support_status=SupportStatus.NOT_RUN,
                metadata={
                    "reason": m4_blocker or "M3_M4_DOWNSTREAM_OUTPUT_REQUIRED",
                    "mapping_id": context.registry_hashes["M4_MAPPING_DESIGN"],
                    "mapping_hash": context.registry_hashes["M4_MAPPING_DESIGN"],
                },
            ),
        }
        return build_context_result(
            context=context, experiment_id="EXP2", variant_id=variant_id,
            metrics=metrics, support_status=SupportStatus.PARTIAL,
            provenance={
                "scientific_question": "HOW_MUCH_AND_WHAT_INFORMATION_STRUCTURE_IS_SUFFICIENT",
                "representation_status": "BLOCKED_M1_OR_M2_ARTIFACT_NOT_MATERIALIZED",
                "downstream_status": "BLOCKED_M4_MAPPING_OR_TAIL",
                "M3_NON_A00_INTERPRETATION": "CONDITIONAL_NON_CAUSAL_NON_AUTHORITATIVE",
                "point_representative_rule": POINT_REPRESENTATIVE_RULE,
                "marginal_weight_policy": MARGINAL_WEIGHT_POLICY,
                "m4_bypassed": False,
            },
        )

    def execute_manifest(
        self,
        manifest: Exp2ExecutionManifest,
        *,
        artifact_root: Path,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
        model_versions: dict[str, str],
    ):
        """Load one exact artifact set and execute its declared variant.

        Every argument is mandatory.  The method does not discover artifacts,
        select actions, choose M3/M4 parameters, or provide fallback values.
        """

        return self._execute_manifest(
            manifest,
            artifact_root=artifact_root,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=model_versions,
            execution_scope=ArtifactScope.SCIENTIFIC,
        )

    def execute_smoke_manifest(
        self,
        manifest: Exp2ExecutionManifest,
        *,
        artifact_root: Path,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
        model_versions: dict[str, str],
    ):
        """Execute one mechanics-only manifest isolated from science."""

        self._assert_smoke_manifest(manifest)
        return self._execute_manifest(
            manifest,
            artifact_root=artifact_root,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=model_versions,
            execution_scope=ArtifactScope.TEST_ONLY_SMOKE,
        )

    def _execute_manifest(
        self,
        manifest: Exp2ExecutionManifest,
        *,
        artifact_root: Path,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
        model_versions: dict[str, str],
        execution_scope: ArtifactScope,
    ):
        self._validate_execution_inputs(manifest, model_versions)
        artifacts = Exp2ArtifactLoader(
            artifact_root=artifact_root,
            execution_scope=execution_scope,
        ).load_all(manifest)
        downstream = Exp2DownstreamExecutor(
            manifest=manifest,
            artifacts=artifacts,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
        )
        return self.execute(self._context(
            manifest=manifest,
            artifacts=artifacts,
            downstream=downstream,
            model_versions=model_versions,
            execution_scope=execution_scope,
        ))

    @staticmethod
    def _validate_execution_inputs(manifest, model_versions):
        if not isinstance(manifest, Exp2ExecutionManifest):
            raise TypeError("EXP2_EXECUTION_MANIFEST_REQUIRED")
        if not model_versions or any(
            not str(key).strip() or not str(value).strip()
            for key, value in model_versions.items()
        ):
            raise ValueError("EXP2_MODEL_VERSIONS_REQUIRED")

    @staticmethod
    def _assert_smoke_manifest(manifest):
        if not isinstance(manifest, Exp2ExecutionManifest):
            raise TypeError("EXP2_EXECUTION_MANIFEST_REQUIRED")
        references = (
            manifest.m1_artifact,
            manifest.m2_artifact,
            manifest.m3_artifact,
            manifest.m4_artifact,
        )
        if (
            manifest.dataset_id != "TEST_ONLY_SMOKE"
            or manifest.split != "SMOKE"
            or any(
                not reference.artifact_version.startswith("TEST_ONLY_SMOKE")
                for reference in references
            )
        ):
            raise ValueError("EXP2_SMOKE_MANIFEST_NOT_TEST_ONLY_SMOKE")

    @staticmethod
    def _context(
        *, manifest, artifacts, downstream, model_versions, execution_scope
    ):
        return Exp2RunContext(
            variant_id=manifest.variant_id,
            dataset_id=manifest.dataset_id,
            seed=manifest.seed,
            m1_scenarios=artifacts.m1.scenarios,
            m2_consequences=artifacts.m2.consequences,
            m1_artifact_version=artifacts.m1.reference.artifact_version,
            m2_artifact_version=artifacts.m2.reference.artifact_version,
            model_versions=dict(model_versions),
            downstream=downstream,
            scenario_hash=artifacts.m1.scenario_hash,
            config_hash=manifest.config_hash,
            artifact_lineage={
                "execution_scope": execution_scope.value,
                "execution_manifest_hash": manifest.manifest_hash,
                "downstream_binding_hash": downstream.binding_hash,
                "m1_artifact_hash": manifest.m1_artifact.artifact_hash,
                "m1_cutoff_source_manifest_hash": (
                    artifacts.m1.cutoff_provenance.source_manifest_hash
                ),
                "m2_artifact_hash": manifest.m2_artifact.artifact_hash,
                "m2_cu_registry_hash": artifacts.m2.cu_lineage.registry_hash,
                "m3_artifact_hash": manifest.m3_artifact.artifact_hash,
                "m3_action_registry_hash": artifacts.m3.action_registry_hash,
                "m3_response_registry_hash": artifacts.m3.response_registry_hash,
                "m4_artifact_hash": manifest.m4_artifact.artifact_hash,
                "m4_monetary_mapping_hash": artifacts.m4.monetary_mapping_hash,
                "m4_risk_policy_hash": artifacts.m4.risk_policy_hash,
            },
        )

    def execute_manifests(
        self,
        manifests: tuple[Exp2ExecutionManifest, ...],
        *,
        artifact_root: Path,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
        model_versions: dict[str, str],
    ):
        """Execute explicitly supplied compatible variants through one binding."""

        return self._execute_manifests(
            manifests,
            artifact_root=artifact_root,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=model_versions,
            execution_scope=ArtifactScope.SCIENTIFIC,
        )

    def execute_smoke_manifests(
        self,
        manifests: tuple[Exp2ExecutionManifest, ...],
        *,
        artifact_root: Path,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
        model_versions: dict[str, str],
    ):
        """Execute compatible TEST_ONLY_SMOKE variants through one binding."""

        for manifest in manifests:
            self._assert_smoke_manifest(manifest)
        return self._execute_manifests(
            manifests,
            artifact_root=artifact_root,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
            model_versions=model_versions,
            execution_scope=ArtifactScope.TEST_ONLY_SMOKE,
        )

    def _execute_manifests(
        self,
        manifests: tuple[Exp2ExecutionManifest, ...],
        *,
        artifact_root: Path,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
        model_versions: dict[str, str],
        execution_scope: ArtifactScope,
    ):
        if not manifests:
            raise ValueError("EXP2_EXECUTION_MANIFEST_SET_EMPTY")
        anchor = manifests[0]
        self._validate_execution_inputs(anchor, model_versions)
        artifacts = Exp2ArtifactLoader(
            artifact_root=artifact_root,
            execution_scope=execution_scope,
        ).load_all(anchor)
        downstream = Exp2DownstreamExecutor(
            manifest=anchor,
            artifacts=artifacts,
            m3_executor=m3_executor,
            m4_evaluator=m4_evaluator,
        )
        downstream.assert_variant_manifests(manifests)
        return tuple(
            self.execute(self._context(
                manifest=manifest,
                artifacts=artifacts,
                downstream=downstream,
                model_versions=model_versions,
                execution_scope=execution_scope,
            ))
            for manifest in manifests
        )


__all__ = ["Exp2Runner"]
