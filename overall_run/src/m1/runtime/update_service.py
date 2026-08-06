from __future__ import annotations

import hashlib
import struct
from dataclasses import replace
from typing import Mapping

import torch

from ..adapter.feature_schema import M1FeatureSchema
from ..contracts import (
    M1MarginalDistribution,
    M1PredictionBundle,
    M1SnapshotNode,
    M1_CONTRACT_ID,
    StateCommitStatus,
    TriggerType,
)
from ..distribution import DiscreteBins, apply_temperature
from ..model import SingleLightweightGRU
from .replay import (
    ReplayResult,
    SnapshotSequenceProvider,
    replay_episode,
    revision_reason,
)
from .state_store import InMemoryStateStore, StateEntry


def _float_hash(values: tuple[float, ...]) -> str:
    payload = b"".join(struct.pack("!d", float(value)) for value in values)
    return hashlib.sha256(payload).hexdigest()


class M1UpdateService:
    def __init__(
        self,
        model: SingleLightweightGRU,
        feature_schema: M1FeatureSchema,
        bins: Mapping[str, DiscreteBins],
        temperatures: Mapping[str, float],
        *,
        model_version: str,
        model_artifact_hash: str,
        temperature_version: str,
        temperature_artifact_hash: str,
        snapshot_provider: SnapshotSequenceProvider | None = None,
        state_store: InMemoryStateStore | None = None,
    ) -> None:
        self.model = model.eval()
        self.feature_schema = feature_schema
        self.bins = dict(bins)
        self.temperatures = dict(temperatures)
        self.model_version = model_version
        self.model_artifact_hash = model_artifact_hash
        self.temperature_version = temperature_version
        self.temperature_artifact_hash = temperature_artifact_hash
        self.snapshot_provider = snapshot_provider
        self.state_store = state_store or InMemoryStateStore()
        if set(self.bins) != set(self.temperatures):
            raise ValueError("M1_TEMPERATURE_TARGET_MISMATCH")
        if any(value <= 0 for value in self.temperatures.values()):
            raise ValueError("M1_TEMPERATURE_NOT_POSITIVE")
        if self.model.input_size != len(self.feature_schema.final_feature_order):
            raise ValueError("M1_MODEL_FEATURE_SCHEMA_DIMENSION_MISMATCH")

    def _key(self, snapshot: M1SnapshotNode) -> tuple[str, str, int, str, str, str, str]:
        return (
            snapshot.episode_id,
            snapshot.snapshot_id,
            snapshot.snapshot_version,
            snapshot.pre_bundle_identity.pre_manifest_hash,
            snapshot.feature_schema_hash,
            self.model_artifact_hash,
            self.temperature_artifact_hash,
        )

    def _snapshot_tensor(self, snapshot: M1SnapshotNode) -> torch.Tensor:
        self.feature_schema.validate_vector(snapshot.feature_vector)
        if snapshot.feature_schema_hash != self.feature_schema.schema_hash:
            raise ValueError("M1_RUNTIME_FEATURE_SCHEMA_MISMATCH")
        return torch.tensor([[snapshot.feature_vector]], dtype=torch.float32)

    def _hidden_tensor(
        self,
        hidden_state: tuple[float, ...] | None,
    ) -> torch.Tensor | None:
        if hidden_state is None:
            return None
        return torch.tensor(hidden_state, dtype=torch.float32).reshape(1, 1, -1)

    def predict_snapshot(
        self,
        snapshot: M1SnapshotNode,
        previous_hidden: tuple[float, ...] | None,
        status: StateCommitStatus,
        *,
        trigger_type: str,
        replay_reason: str | None,
        replay_node_count: int,
    ) -> M1PredictionBundle:
        with torch.no_grad():
            logits, next_hidden = self.model.step(
                self._snapshot_tensor(snapshot),
                self._hidden_tensor(previous_hidden),
            )
        distributions: dict[str, M1MarginalDistribution] = {}
        for target, contract in snapshot.target_contracts.items():
            if not contract.active or target not in logits:
                continue
            probabilities = apply_temperature(
                logits[target].cpu().numpy(),
                self.temperatures[target],
            )[0]
            target_bins = self.bins[target]
            distributions[target] = M1MarginalDistribution(
                episode_id=snapshot.episode_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_version=snapshot.snapshot_version,
                query_time=snapshot.query_time,
                information_cutoff=snapshot.information_cutoff,
                pre_manifest_hash=snapshot.pre_bundle_identity.pre_manifest_hash,
                feature_schema_hash=snapshot.feature_schema_hash,
                m1_contract_id=M1_CONTRACT_ID,
                model_version=self.model_version,
                model_artifact_hash=self.model_artifact_hash,
                temperature_version=self.temperature_version,
                temperature_artifact_hash=self.temperature_artifact_hash,
                target_name=target,
                target_support_level=contract.m1_support_level,
                evidence_status=snapshot.evidence_status,
                bin_lower_minutes=target_bins.lower_minutes,
                bin_upper_minutes=target_bins.upper_minutes,
                probabilities=tuple(float(value) for value in probabilities),
            )
        hidden_state = tuple(
            float(value) for value in next_hidden.reshape(-1).cpu().numpy()
        )
        return M1PredictionBundle(
            episode_id=snapshot.episode_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_version=snapshot.snapshot_version,
            query_time=snapshot.query_time,
            information_cutoff=snapshot.information_cutoff,
            pre_manifest_hash=snapshot.pre_bundle_identity.pre_manifest_hash,
            feature_schema_hash=snapshot.feature_schema_hash,
            m1_contract_id=M1_CONTRACT_ID,
            model_version=self.model_version,
            model_artifact_hash=self.model_artifact_hash,
            temperature_version=self.temperature_version,
            temperature_artifact_hash=self.temperature_artifact_hash,
            target_support_level={
                target: contract.m1_support_level
                for target, contract in snapshot.target_contracts.items()
            },
            evidence_status=snapshot.evidence_status,
            distributions=distributions,
            hidden_state=hidden_state,
            state_commit_status=status,
            replay_reason=replay_reason,
            replay_node_count=replay_node_count,
        )

    def state_entry(
        self,
        snapshot: M1SnapshotNode,
        prediction: M1PredictionBundle,
        trigger_type: str,
    ) -> StateEntry:
        return StateEntry.committed(
            snapshot=snapshot,
            prediction=prediction,
            model_artifact_hash=self.model_artifact_hash,
            temperature_artifact_hash=self.temperature_artifact_hash,
            snapshot_vector_hash=_float_hash(snapshot.feature_vector),
            hidden_state_hash=_float_hash(prediction.hidden_state),
            trigger_type=trigger_type,
        )

    def _previous_hidden(self, snapshot: M1SnapshotNode) -> tuple[float, ...] | None:
        previous = self.state_store.latest_before(
            snapshot.episode_id,
            snapshot.query_time,
        )
        return previous.prediction.hidden_state if previous is not None else None

    def update_and_predict(
        self,
        snapshot: M1SnapshotNode,
        trigger_type: TriggerType | str,
        commit_state: bool,
    ) -> M1PredictionBundle:
        trigger = TriggerType(
            trigger_type.value if isinstance(trigger_type, TriggerType) else str(trigger_type)
        ).value
        exact = self.state_store.find_exact(self._key(snapshot))
        if exact is not None:
            status = StateCommitStatus.REUSED if commit_state else StateCommitStatus.TEMPORARY
            return replace(exact.prediction, state_commit_status=status)
        working_store = self.state_store
        if not commit_state:
            working_store = self.state_store.clone_episode_state(snapshot.episode_id)
        if snapshot.state_reset_signal:
            working_store.clear_episode(snapshot.episode_id)
        entries = working_store.entries(snapshot.episode_id)
        reason = revision_reason(entries, snapshot)
        if reason is not None:
            if self.snapshot_provider is None:
                raise ValueError("M1_REPLAY_PROVIDER_REQUIRED")
            original_store = self.state_store
            self.state_store = working_store
            try:
                result = replay_episode(
                    snapshot.episode_id,
                    snapshot.query_time,
                    max(snapshot.query_time, entries[-1].snapshot.query_time),
                    self.snapshot_provider,
                    working_store,
                    self,
                    reason=reason,
                    status=(
                        StateCommitStatus.COMMITTED
                        if commit_state
                        else StateCommitStatus.TEMPORARY
                    ),
                    replacement_snapshot=snapshot,
                )
            finally:
                self.state_store = original_store
            return result.final_prediction
        latest = working_store.latest(snapshot.episode_id)
        if latest is not None and snapshot.query_time <= latest.snapshot.query_time:
            raise ValueError("M1_STATE_OUT_OF_ORDER_REQUIRES_REPLAY")
        status = StateCommitStatus.COMMITTED if commit_state else StateCommitStatus.TEMPORARY
        prediction = self.predict_snapshot(
            snapshot,
            latest.prediction.hidden_state if latest is not None else None,
            status,
            trigger_type=trigger,
            replay_reason=None,
            replay_node_count=0,
        )
        if commit_state:
            self.state_store.append(self.state_entry(snapshot, prediction, trigger))
        return prediction

    def replay_revision(
        self,
        snapshot: M1SnapshotNode,
        *,
        commit_state: bool,
    ) -> ReplayResult:
        if self.snapshot_provider is None:
            raise ValueError("M1_REPLAY_PROVIDER_REQUIRED")
        working_store = (
            self.state_store
            if commit_state
            else self.state_store.clone_episode_state(snapshot.episode_id)
        )
        latest = working_store.latest(snapshot.episode_id)
        end = snapshot.query_time if latest is None else max(snapshot.query_time, latest.snapshot.query_time)
        original_store = self.state_store
        self.state_store = working_store
        try:
            return replay_episode(
                snapshot.episode_id,
                snapshot.query_time,
                end,
                self.snapshot_provider,
                working_store,
                self,
                reason="EXPLICIT_REVISION_REPLAY",
                status=(
                    StateCommitStatus.COMMITTED
                    if commit_state
                    else StateCommitStatus.TEMPORARY
                ),
                replacement_snapshot=snapshot,
            )
        finally:
            self.state_store = original_store

    def scheduled_update(self, snapshot: M1SnapshotNode) -> M1PredictionBundle:
        return self.update_and_predict(snapshot, TriggerType.SCHEDULED, True)

    def event_update(self, snapshot: M1SnapshotNode) -> M1PredictionBundle:
        return self.update_and_predict(snapshot, TriggerType.EVENT, True)

    def predict_now(self, snapshot: M1SnapshotNode) -> M1PredictionBundle:
        return self.update_and_predict(snapshot, TriggerType.DIRECT, False)
