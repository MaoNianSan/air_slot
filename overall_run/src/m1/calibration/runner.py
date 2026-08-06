from __future__ import annotations

from typing import Iterable

import numpy as np
import torch

from ..distribution.calibration import apply_temperature, fit_temperature
from ..model import SingleLightweightGRU
from ..training.collate import M1TrainingBatch
from .artifacts import TemperatureArtifact


def _objective(
    logits: np.ndarray,
    labels: np.ndarray,
    temperature: float,
) -> float:
    probabilities = apply_temperature(logits, temperature)
    return float(
        -(labels * np.log(np.clip(probabilities, 1e-12, 1.0))).sum(axis=1).mean()
    )


def fit_temperature_artifact(
    model: SingleLightweightGRU,
    batches: Iterable[M1TrainingBatch],
    *,
    checkpoint_hash: str,
    pre_manifest_hash: str,
    feature_schema_hash: str,
    artifact_version: str,
) -> TemperatureArtifact:
    logits_by_target: dict[str, list[np.ndarray]] = {
        target: [] for target in ("R_IB", "R_OB", "T_TX")
    }
    labels_by_target: dict[str, list[np.ndarray]] = {
        target: [] for target in logits_by_target
    }
    episode_ids: set[str] = set()
    model.eval()
    with torch.no_grad():
        for batch in batches:
            output = model.forward_sequence(
                batch.feature_sequence,
                batch.valid_node_mask,
            )
            for target in logits_by_target:
                if target not in batch.target_available_mask:
                    continue
                mask = batch.valid_node_mask & batch.target_available_mask[target]
                if not mask.any():
                    continue
                logits_by_target[target].append(
                    output.logits_by_target[target][mask].cpu().numpy()
                )
                labels_by_target[target].append(
                    batch.target_distributions[target][mask].cpu().numpy()
                )
                for index, episode_id in enumerate(batch.episode_ids):
                    if mask[index].any():
                        episode_ids.add(episode_id)
    values: dict[str, float] = {}
    objectives: list[float] = []
    for target in logits_by_target:
        if not logits_by_target[target]:
            raise ValueError(f"M1_CALIBRATION_TARGET_UNAVAILABLE:{target}")
        logits = np.concatenate(logits_by_target[target], axis=0)
        labels = np.concatenate(labels_by_target[target], axis=0)
        temperature = fit_temperature(logits, labels)
        values[target] = temperature
        objectives.append(_objective(logits, labels, temperature))
    return TemperatureArtifact.build(
        values=values,
        checkpoint_hash=checkpoint_hash,
        pre_manifest_hash=pre_manifest_hash,
        feature_schema_hash=feature_schema_hash,
        calibration_episode_ids=tuple(sorted(episode_ids)),
        objective_value=sum(objectives) / len(objectives),
        artifact_version=artifact_version,
    )
