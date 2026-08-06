from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .adapter import (
    M1FeatureSchema,
    PublishedPreBundle,
    PublishedSnapshotSequenceProvider,
    build_snapshot_node,
)
from .calibration import load_temperature_artifact
from .config import M1Settings
from .contracts import (
    EventHorizonProbabilities,
    M1JointSample,
    M1PredictionBundle,
    M1RunManifest,
    M1ScenarioBundle,
    M1SnapshotNode,
    M1_CONTRACT_ID,
)
from .distribution import derive_horizon_probabilities, derive_joint_samples
from .distribution import EmpiricalTailArtifact
from .runtime import M1UpdateService, ReplayResult
from .training import load_checkpoint


@dataclass(frozen=True)
class M1PipelineResult:
    prediction: M1PredictionBundle
    joint_samples: tuple[M1JointSample, ...]
    horizon_probabilities: EventHorizonProbabilities
    scenario_bundle: M1ScenarioBundle


class M1Pipeline:
    def __init__(
        self,
        service: M1UpdateService,
        settings: M1Settings,
        bundle: PublishedPreBundle,
        feature_schema: M1FeatureSchema,
        tail_artifacts: dict[str, EmpiricalTailArtifact] | None = None,
    ) -> None:
        self.service = service
        self.settings = settings
        self.bundle = bundle
        self.feature_schema = feature_schema
        self.tail_artifacts = dict(tail_artifacts or {})

    @classmethod
    def from_artifacts(
        cls,
        bundle: PublishedPreBundle,
        settings: M1Settings,
        model_checkpoint: str | Path,
        temperature_artifact: str | Path,
    ) -> "M1Pipeline":
        checkpoint_path = Path(model_checkpoint)
        temperature_path = Path(temperature_artifact)
        if not checkpoint_path.is_file():
            raise FileNotFoundError("M1_MODEL_ARTIFACT_MISSING")
        if not temperature_path.is_file():
            raise FileNotFoundError("M1_TEMPERATURE_ARTIFACT_MISSING")
        feature_schema = M1FeatureSchema.from_column_registry(
            bundle.column_registry,
            schema_version=settings.feature_schema_version,
        )
        model_artifact = load_checkpoint(
            checkpoint_path,
            expected_pre_manifest_hash=bundle.identity.pre_manifest_hash,
            expected_feature_schema=feature_schema,
        )
        temperatures = load_temperature_artifact(
            temperature_path,
            checkpoint_hash=model_artifact.artifact_hash,
            pre_manifest_hash=bundle.identity.pre_manifest_hash,
            feature_schema_hash=feature_schema.schema_hash,
            formal=True,
        )
        provider = PublishedSnapshotSequenceProvider(
            bundle,
            feature_schema,
            roll_minutes=settings.roll_minutes,
            maximum_minutes=settings.maximum_snapshot_minutes,
            stale_after_minutes=settings.stale_after_minutes,
        )
        service = M1UpdateService(
            model_artifact.model,
            feature_schema,
            model_artifact.bins,
            temperatures.values,
            model_version=model_artifact.model_version,
            model_artifact_hash=model_artifact.artifact_hash,
            temperature_version=temperatures.artifact_version,
            temperature_artifact_hash=temperatures.artifact_hash,
            snapshot_provider=provider,
        )
        return cls(
            service,
            settings,
            bundle,
            feature_schema,
            tail_artifacts=dict(model_artifact.tail_artifacts),
        )

    def build_snapshot(
        self,
        episode_id: str,
        query_time: object,
        *,
        snapshot_version: int = 1,
        previous_query_time: object | None = None,
        state_reset_signal: bool = False,
    ) -> M1SnapshotNode:
        return build_snapshot_node(
            self.bundle,
            episode_id,
            query_time,
            self.feature_schema,
            snapshot_version=snapshot_version,
            previous_query_time=previous_query_time,
            state_reset_signal=state_reset_signal,
            stale_after_minutes=self.settings.stale_after_minutes,
        )

    def _result(
        self,
        snapshot: M1SnapshotNode,
        prediction: M1PredictionBundle,
    ) -> M1PipelineResult:
        samples = derive_joint_samples(
            snapshot,
            prediction.distributions,
            sample_count=self.settings.sample_count,
            base_seed=self.settings.base_seed,
            tail_artifacts=self.tail_artifacts,
        )
        horizons = derive_horizon_probabilities(
            samples,
            snapshot.query_time,
            self.settings.horizons_minutes,
        )
        overflow_targets = {
            target
            for sample in samples
            for target, overflow in sample.overflow_flags.items()
            if overflow
        }
        unresolved = [
            target
            for target in overflow_targets
            if target not in self.tail_artifacts
            or self.tail_artifacts[target].resolution_status != "RESOLVED"
        ]
        scenario = M1ScenarioBundle(
            metadata={
                "episode_id": snapshot.episode_id,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_version": snapshot.snapshot_version,
                "query_time": snapshot.query_time,
                "information_cutoff": snapshot.information_cutoff,
                "flight_chain_stage": snapshot.flight_chain_stage.value,
                "pre_bundle_id": snapshot.pre_bundle_identity.pre_manifest_hash,
                "m1_bundle_id": snapshot.snapshot_id,
                "m1_contract_id": M1_CONTRACT_ID,
                "model_version": prediction.model_version,
                "temperature_version": prediction.temperature_version,
            },
            operational_references=snapshot.operational_references,
            marginal_distributions=prediction.distributions,
            sampling_metadata={
                "sample_count": len(samples),
                "sampling_version": "M1_SAMPLING_V2",
                "base_seed": self.settings.base_seed,
                "dependence_mode": "CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING",
                "bin_representative_mode": "FIXED_WITHIN_BIN_UNIFORM",
                "overflow_mode": "TRAINING_EMPIRICAL_TAIL",
                "tail_artifact_version": {
                    name: artifact.artifact_version
                    for name, artifact in sorted(self.tail_artifacts.items())
                },
                "tail_resolution_status": (
                    "TAIL_UNRESOLVED"
                    if unresolved
                    else ("RESOLVED" if overflow_targets else "RESOLVED_NO_OVERFLOW")
                ),
                "unresolved_overflow_targets": tuple(sorted(unresolved)),
            },
            joint_samples=samples,
        )
        return M1PipelineResult(prediction, samples, horizons, scenario)

    def scheduled_update(self, snapshot: M1SnapshotNode) -> M1PipelineResult:
        return self._result(snapshot, self.service.scheduled_update(snapshot))

    def event_update(self, snapshot: M1SnapshotNode) -> M1PipelineResult:
        return self._result(snapshot, self.service.event_update(snapshot))

    def predict_now(self, snapshot: M1SnapshotNode) -> M1PipelineResult:
        return self._result(snapshot, self.service.predict_now(snapshot))

    def replay_revision(
        self,
        snapshot: M1SnapshotNode,
        *,
        commit_state: bool = True,
    ) -> ReplayResult:
        return self.service.replay_revision(snapshot, commit_state=commit_state)

    @staticmethod
    def not_run_manifest(bundle: PublishedPreBundle) -> M1RunManifest:
        return M1RunManifest(
            pre_bundle_identity=bundle.identity,
            m1_contract_id=M1_CONTRACT_ID,
            feature_schema_status="CODE_READY_NOT_RUN",
            snapshot_builder_status="CODE_READY_NOT_RUN",
            target_support_status="NOT_AUDITED",
            training_status="NOT_RUN",
            checkpoint_status="MISSING_NOT_RUN",
            calibration_status="NOT_RUN",
            evaluation_status="NOT_RUN",
            runtime_state_status="CODE_READY_NOT_RUN",
            m2_interface_status="M2_V2_CODE_READY_NOT_RUN",
            engineering_status="CODE_MODIFIED_NOT_VALIDATED",
            scientific_status="NOT_READY",
        )
