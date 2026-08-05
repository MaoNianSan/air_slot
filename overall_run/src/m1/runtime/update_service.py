from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import numpy as np
import torch

from ..contracts import (
    M1InputBundle,
    M1MarginalDistribution,
    M1PredictionBundle,
    StateCommitStatus,
    TriggerType,
    M1_CONTRACT_ID,
)
from ..distribution import DiscreteBins, apply_temperature
from ..model import SingleLightweightGRU
from .replay import replay_reason
from .state_store import InMemoryStateStore, StateEntry


class M1UpdateService:
    def __init__(
        self,
        model: SingleLightweightGRU,
        feature_order: tuple[str, ...],
        bins: Mapping[str, DiscreteBins],
        temperatures: Mapping[str, float],
        *,
        model_version: str,
        temperature_version: str,
        state_store: InMemoryStateStore | None = None,
    ) -> None:
        self.model = model.eval()
        self.feature_order = feature_order
        self.bins = dict(bins)
        self.temperatures = dict(temperatures)
        self.model_version = model_version
        self.temperature_version = temperature_version
        self.state_store = state_store or InMemoryStateStore()
        if set(self.bins) != set(self.temperatures):
            raise ValueError("M1_TEMPERATURE_TARGET_MISMATCH")
        if any(value <= 0 for value in self.temperatures.values()):
            raise ValueError("M1_TEMPERATURE_NOT_POSITIVE")

    def _key(self, bundle: M1InputBundle) -> tuple[str, str, int, str, str]:
        return (
            bundle.episode_id,
            bundle.snapshot_id,
            bundle.snapshot_version,
            bundle.pre_bundle_identity.pre_manifest_hash,
            self.model_version,
        )

    def _sequence(self, bundle: M1InputBundle) -> torch.Tensor:
        source = bundle.sequence_features or (bundle.current_features,)
        rows: list[list[float]] = []
        for record in source:
            values = [float(record.get(name, bundle.current_features.get(name, 0.0))) for name in self.feature_order]
            rows.append(values)
        return torch.tensor([rows], dtype=torch.float32)

    def _hidden(self, bundle: M1InputBundle) -> torch.Tensor | None:
        latest = self.state_store.latest(bundle.episode_id)
        if latest is None or bundle.state_reset_signal:
            return None
        hidden = torch.tensor(latest.prediction.hidden_state, dtype=torch.float32)
        return hidden.reshape(1, 1, -1)

    def _predict(
        self,
        bundle: M1InputBundle,
        hidden: torch.Tensor | None,
        status: StateCommitStatus,
        reason: str | None,
        replay_nodes: int,
    ) -> M1PredictionBundle:
        with torch.no_grad():
            logits, next_hidden = self.model(self._sequence(bundle), hidden)
        distributions: dict[str, M1MarginalDistribution] = {}
        for target, contract in bundle.target_contracts.items():
            if not contract.active or target not in logits:
                continue
            probabilities = apply_temperature(
                logits[target].cpu().numpy(), self.temperatures[target]
            )[0]
            target_bins = self.bins[target]
            distributions[target] = M1MarginalDistribution(
                episode_id=bundle.episode_id,
                snapshot_id=bundle.snapshot_id,
                snapshot_version=bundle.snapshot_version,
                query_time=bundle.query_time,
                information_cutoff=bundle.information_cutoff,
                pre_manifest_hash=bundle.pre_bundle_identity.pre_manifest_hash,
                m1_contract_id=M1_CONTRACT_ID,
                model_version=self.model_version,
                temperature_version=self.temperature_version,
                target_name=target,
                target_support_level=contract.m1_support_level,
                evidence_status=bundle.evidence_status,
                bin_lower_minutes=target_bins.lower_minutes,
                bin_upper_minutes=target_bins.upper_minutes,
                probabilities=tuple(float(value) for value in probabilities),
            )
        return M1PredictionBundle(
            episode_id=bundle.episode_id,
            snapshot_id=bundle.snapshot_id,
            snapshot_version=bundle.snapshot_version,
            query_time=bundle.query_time,
            information_cutoff=bundle.information_cutoff,
            pre_manifest_hash=bundle.pre_bundle_identity.pre_manifest_hash,
            m1_contract_id=M1_CONTRACT_ID,
            model_version=self.model_version,
            temperature_version=self.temperature_version,
            target_support_level={
                target: contract.m1_support_level
                for target, contract in bundle.target_contracts.items()
            },
            evidence_status=bundle.evidence_status,
            distributions=distributions,
            hidden_state=tuple(float(value) for value in next_hidden.reshape(-1).cpu().numpy()),
            state_commit_status=status,
            replay_reason=reason,
            replay_node_count=replay_nodes,
        )

    def update_and_predict(
        self,
        input_bundle: M1InputBundle,
        trigger_type: TriggerType | str,
        commit_state: bool,
    ) -> M1PredictionBundle:
        normalized_trigger = (
            trigger_type.value if isinstance(trigger_type, TriggerType) else str(trigger_type)
        )
        TriggerType(normalized_trigger)
        existing = self.state_store.find(self._key(input_bundle))
        if existing is not None:
            return replace(existing, state_commit_status=StateCommitStatus.REUSED)
        if input_bundle.state_reset_signal:
            self.state_store.clear_episode(input_bundle.episode_id)
        entries = self.state_store.entries(input_bundle.episode_id)
        reason = replay_reason(entries, input_bundle)
        replay_nodes = 0
        if reason:
            removed = self.state_store.truncate_from(
                input_bundle.episode_id, input_bundle.query_time
            )
            replay_nodes = len(removed)
        status = StateCommitStatus.COMMITTED if commit_state else StateCommitStatus.TEMPORARY
        prediction = self._predict(
            input_bundle,
            self._hidden(input_bundle),
            status,
            reason,
            replay_nodes,
        )
        if commit_state:
            self.state_store.append(StateEntry(input_bundle, prediction))
        return prediction

    def scheduled_update(self, input_bundle: M1InputBundle) -> M1PredictionBundle:
        return self.update_and_predict(input_bundle, TriggerType.SCHEDULED, True)

    def event_update(self, input_bundle: M1InputBundle) -> M1PredictionBundle:
        return self.update_and_predict(input_bundle, TriggerType.EVENT, True)

    def predict_now(self, input_bundle: M1InputBundle) -> M1PredictionBundle:
        return self.update_and_predict(input_bundle, TriggerType.DIRECT, False)
