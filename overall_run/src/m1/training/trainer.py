from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import torch
from torch.nn import functional as F

from ..model import SingleLightweightGRU
from .collate import M1TrainingBatch


@dataclass(frozen=True)
class M1TrainerConfig:
    max_epochs: int
    learning_rate: float
    gradient_clip: float
    weight_decay: float
    early_stopping_patience: int

    def __post_init__(self) -> None:
        if min(self.max_epochs, self.early_stopping_patience) <= 0:
            raise ValueError("M1_TRAINER_EPOCH_CONFIG_INVALID")
        if self.learning_rate <= 0 or self.gradient_clip <= 0 or self.weight_decay < 0:
            raise ValueError("M1_TRAINER_OPTIMIZER_CONFIG_INVALID")


@dataclass(frozen=True)
class TrainingResult:
    best_epoch: int
    best_validation_loss: float
    validation_history: tuple[float, ...]
    best_state_dict: Mapping[str, torch.Tensor]


def _batch_loss(
    model: SingleLightweightGRU,
    batch: M1TrainingBatch,
) -> torch.Tensor:
    output = model.forward_sequence(batch.feature_sequence, batch.valid_node_mask)
    target_losses: list[torch.Tensor] = []
    for target, labels in batch.target_distributions.items():
        logits = output.logits_by_target[target]
        node_loss = -(labels * F.log_softmax(logits, dim=-1)).sum(dim=-1)
        mask = batch.valid_node_mask & batch.target_available_mask[target]
        available_per_episode = mask.sum(dim=1)
        usable = available_per_episode > 0
        if not usable.any():
            continue
        episode_loss = (node_loss * mask).sum(dim=1) / available_per_episode.clamp_min(1)
        weights = batch.episode_weights[usable]
        target_losses.append(
            (episode_loss[usable] * weights).sum() / weights.sum()
        )
    if not target_losses:
        raise ValueError("M1_TRAINING_BATCH_HAS_NO_SUPPORTED_TARGET")
    return torch.stack(target_losses).mean()


def train_epoch(
    model: SingleLightweightGRU,
    batches: Iterable[M1TrainingBatch],
    optimizer: torch.optim.Optimizer,
    *,
    gradient_clip: float,
) -> float:
    model.train()
    losses: list[float] = []
    for batch in batches:
        optimizer.zero_grad(set_to_none=True)
        loss = _batch_loss(model, batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), gradient_clip)
        optimizer.step()
        losses.append(float(loss.detach()))
    if not losses:
        raise ValueError("M1_TRAINING_EPOCH_EMPTY")
    return sum(losses) / len(losses)


def validate_epoch(
    model: SingleLightweightGRU,
    batches: Iterable[M1TrainingBatch],
) -> float:
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for batch in batches:
            losses.append(float(_batch_loss(model, batch)))
    if not losses:
        raise ValueError("M1_VALIDATION_EPOCH_EMPTY")
    return sum(losses) / len(losses)


def fit(
    model: SingleLightweightGRU,
    train_batches: Iterable[M1TrainingBatch],
    validation_batches: Iterable[M1TrainingBatch],
    config: M1TrainerConfig,
) -> TrainingResult:
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    best_loss = float("inf")
    best_epoch = 0
    best_state: dict[str, torch.Tensor] = {}
    history: list[float] = []
    stale_epochs = 0
    for epoch in range(1, config.max_epochs + 1):
        train_epoch(model, train_batches, optimizer, gradient_clip=config.gradient_clip)
        validation_loss = validate_epoch(model, validation_batches)
        history.append(validation_loss)
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= config.early_stopping_patience:
            break
    return TrainingResult(best_epoch, best_loss, tuple(history), best_state)
