from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from ..adapter.feature_schema import M1FeatureSchema
from ..distribution import DiscreteBins, EmpiricalTailArtifact
from ..model import SingleLightweightGRU
from .checkpoint import save_checkpoint
from .collate import M1TrainingBatch
from .trainer import M1TrainerConfig, TrainingResult, fit


class M1TrainingRunner:
    def __init__(
        self,
        model: SingleLightweightGRU,
        feature_schema: M1FeatureSchema,
        bins: Mapping[str, DiscreteBins],
        config: M1TrainerConfig,
    ) -> None:
        self.model = model
        self.feature_schema = feature_schema
        self.bins = dict(bins)
        self.config = config

    def fit_and_checkpoint(
        self,
        train_batches: Iterable[M1TrainingBatch],
        validation_batches: Iterable[M1TrainingBatch],
        checkpoint_path: str | Path,
        *,
        pre_manifest_hash: str,
        split_definition: Mapping[str, object],
        random_seed: int,
        source_commit: str,
        artifact_version: str,
        tail_artifacts: Mapping[str, EmpiricalTailArtifact] | None = None,
    ) -> tuple[TrainingResult, str]:
        result = fit(self.model, train_batches, validation_batches, self.config)
        artifact_hash = save_checkpoint(
            checkpoint_path,
            state_dict=result.best_state_dict,
            model_architecture={
                "type": "single_lightweight_gru",
                "layers": 1,
                "hidden_size": self.model.hidden_size,
                "input_size": self.model.input_size,
                "bidirectional": False,
                "attention": False,
            },
            feature_schema=self.feature_schema,
            bins=self.bins,
            pre_manifest_hash=pre_manifest_hash,
            split_definition=split_definition,
            training_config={
                "max_epochs": self.config.max_epochs,
                "learning_rate": self.config.learning_rate,
                "gradient_clip": self.config.gradient_clip,
                "weight_decay": self.config.weight_decay,
                "early_stopping_patience": self.config.early_stopping_patience,
            },
            random_seed=random_seed,
            best_epoch=result.best_epoch,
            validation_metrics={"cross_entropy": result.best_validation_loss},
            source_commit=source_commit,
            artifact_version=artifact_version,
            tail_artifacts=tail_artifacts,
        )
        return result, artifact_hash
