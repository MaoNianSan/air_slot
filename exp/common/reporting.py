"""DEPRECATED (2026-08-24): legacy reporter layer; new outputs go through exp.reporting.output_contract (2026-08-24).
"""

from __future__ import annotations

"""Provenance-preserving serializers for common experiment results."""


import csv
import json
from pathlib import Path
from typing import Iterable

from .result_schema import ExperimentResult


class ExperimentReporter:
    """Write JSON, metric CSV, and Markdown summary artifacts."""

    def __init__(self, *, overwrite: bool = False):
        self.overwrite = overwrite

    def _require_writable(self, path: Path) -> None:
        if path.exists() and not self.overwrite:
            raise FileExistsError(f"EXPERIMENT_REPORT_OVERWRITE_REJECTED:{path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _lineage(result: ExperimentResult) -> str:
        return json.dumps(
            result.artifact_versions,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _json(value) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def write_json(self, result: ExperimentResult, path: Path) -> Path:
        if not isinstance(result, ExperimentResult):
            raise TypeError("EXPERIMENT_REPORT_RESULT_TYPE_REQUIRED")
        self._require_writable(path)
        path.write_text(result.model_dump_json(indent=2, by_alias=True) + "\n", encoding="utf-8")
        return path

    def metric_rows(self, results: Iterable[ExperimentResult]) -> tuple[dict, ...]:
        rows = []
        for result in results:
            if not isinstance(result, ExperimentResult):
                raise TypeError("EXPERIMENT_REPORT_RESULT_TYPE_REQUIRED")
            common = {
                "experiment_id": result.experiment_id,
                "variant_id": result.variant_id,
                "dataset_id": result.dataset_id,
                "split": result.split,
                "tier": result.tier,
                "episode_count": result.episode_count,
                "node_count": result.node_count,
                "seed": result.seed,
                "timestamp": result.timestamp.isoformat(),
                "scenario_hash": result.scenario_hash,
                "config_hash": result.config_hash,
                "support_status": result.support_status.value,
                "model_versions": self._json(result.model_versions),
                "model_hashes": self._json(result.model_hashes),
                "registry_hashes": self._json(result.registry_hashes),
                "artifact_lineage": self._lineage(result),
                "lineage": self._json(result.lineage),
                "runtime": self._json(result.runtime),
                "FINAL_TEST_ACCESS_COUNT": result.final_test_access_count,
                "provenance": self._json(result.provenance),
                "result_hash": result.result_hash,
            }
            if not result.metrics:
                rows.append({
                    **common,
                    "metric_id": "",
                    "metric_level": "",
                    "metric_value": "",
                    "metric_unit": "",
                    "metric_support_status": "",
                    "metric_metadata": "{}",
                })
                continue
            for metric_id in sorted(result.metrics):
                observation = result.metrics[metric_id]
                rows.append({
                    **common,
                    "metric_id": metric_id,
                    "metric_level": observation.level.value,
                    "metric_value": observation.value,
                    "metric_unit": observation.unit,
                    "metric_support_status": observation.support_status.value,
                    "metric_metadata": self._json(observation.metadata),
                })
        return tuple(rows)

    def write_csv(self, results: Iterable[ExperimentResult], path: Path) -> Path:
        rows = self.metric_rows(results)
        self._require_writable(path)
        fieldnames = (
            "experiment_id", "variant_id", "dataset_id", "split", "tier",
            "episode_count", "node_count", "seed", "timestamp", "scenario_hash",
            "config_hash", "support_status", "model_versions", "model_hashes",
            "registry_hashes", "artifact_lineage", "lineage", "runtime",
            "FINAL_TEST_ACCESS_COUNT", "provenance", "result_hash", "metric_id",
            "metric_level", "metric_value", "metric_unit",
            "metric_support_status", "metric_metadata",
        )
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    @staticmethod
    def _markdown(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    def write_summary_table(
        self, results: Iterable[ExperimentResult], path: Path,
    ) -> Path:
        rows = self.metric_rows(results)
        self._require_writable(path)
        headers = (
            "Experiment", "Variant", "Metric", "Level", "Value", "Support",
            "Scenario hash", "Artifact lineage",
        )
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for row in rows:
            values = (
                row["experiment_id"], row["variant_id"], row["metric_id"],
                row["metric_level"], row["metric_value"],
                row["metric_support_status"] or row["support_status"],
                row["scenario_hash"], row["artifact_lineage"],
            )
            lines.append("| " + " | ".join(self._markdown(value) for value in values) + " |")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_bundle(self, result: ExperimentResult, output: Path) -> dict[str, Path]:
        paths = {
            "json": output / "result.json",
            "csv": output / "metrics.csv",
            "summary": output / "summary.md",
        }
        for path in paths.values():
            self._require_writable(path)
        self.write_json(result, paths["json"])
        self.write_csv((result,), paths["csv"])
        self.write_summary_table((result,), paths["summary"])
        return paths


__all__ = ["ExperimentReporter"]
