from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


CORE_FIGURE_STEMS = (
    "fig01_execution_risk_validity",
    "fig02_channel_reconstruction",
    "fig03_action_response_library",
    "fig04_screening_and_recommendation",
    "fig05_representative_episode",
)

PUBLICATION_SOURCE_PATHS = (
    "metrics/m1_predictions_evaluation.parquet",
    "metrics/m1_summary_evaluation.parquet",
    "metrics/m2_summary.parquet",
    "m3_response_parameters.parquet",
    "m3_response_samples.parquet",
    "m3_response_audit.parquet",
    "metrics/m4_physical_screening.parquet",
    "m4_candidate_screen.parquet",
    "m4_action_scores.parquet",
    "m4_rankings.parquet",
    "m4_recommendations.parquet",
    "scientific_gate.json",
    "run_manifest.json",
    "parameter_manifest.parquet",
)

M4_AUDIT_FILES = (
    "m4_gate_decomposition.parquet",
    "m4_decision_value_decomposition.parquet",
    "m4_snapshot_retained_action_count.parquet",
    "m4_snapshot_retained_action_summary.parquet",
    "m4_a00_concentration_decomposition.parquet",
    "m4_threshold_margin_rows.parquet",
    "m4_threshold_margin_summary.parquet",
    "m4_score_gap_analysis.parquet",
)

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path.with_suffix(".parquet"), index=False)
    df.to_csv(path.with_suffix(".csv"), index=False)


