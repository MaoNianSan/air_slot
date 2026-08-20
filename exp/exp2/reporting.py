"""Exp2 result construction and common artifact reporting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from exp.common.reporting import ExperimentReporter
from exp.common.result_schema import ExperimentResult, MetricObservation, SupportStatus
from model.common.identity import content_id


def build_exp2_result(
    *,
    variant_id: str,
    dataset_id: str,
    seed: int,
    artifact_version: str,
    scenario_hash: str,
    metrics: dict[str, MetricObservation],
    support_status: SupportStatus,
    model_versions: dict[str, str],
    provenance: dict[str, Any],
    config_hash: str | None = None,
    timestamp: datetime | None = None,
) -> ExperimentResult:
    """Map the requested singular artifact version into the common V1 map."""

    config_hash = config_hash or content_id({
        "experiment_id": "EXP2",
        "variant_id": variant_id,
        "dataset_id": dataset_id,
        "seed": seed,
        "artifact_version": artifact_version,
    })
    return ExperimentResult(
        experiment_id="EXP2",
        variant_id=variant_id,
        dataset_id=dataset_id,
        seed=seed,
        timestamp=timestamp or datetime.now(timezone.utc),
        model_versions=model_versions,
        artifact_versions={"EXP2_SOURCE_ARTIFACT": artifact_version},
        scenario_hash=scenario_hash,
        config_hash=config_hash,
        metrics=metrics,
        support_status=support_status,
        provenance={
            **provenance,
            "artifact_version": artifact_version,
            "paper_result": False,
            "model_retrained": False,
            "experiment_scope": "REPRESENTATION_COMPARISON_ONLY",
        },
    )


class Exp2Reporter(ExperimentReporter):
    """The common reporter with an Exp2-specific entry-point name."""

    def write_result(self, result: ExperimentResult, output: Path) -> dict[str, Path]:
        if result.experiment_id != "EXP2":
            raise ValueError("EXP2_REPORTER_EXPERIMENT_ID_MISMATCH")
        return self.write_bundle(result, output)


__all__ = ["Exp2Reporter", "build_exp2_result"]
