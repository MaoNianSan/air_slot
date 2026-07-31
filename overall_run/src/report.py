from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .report_contract import (
    CORE_FIGURE_STEMS,
    M4_AUDIT_FILES,
    PUBLICATION_SOURCE_PATHS,
    _save_table,
    _sha256,
)
from .report_figures import (
    figure_m1_validity,
    figure_m3_appendix,
    figure_precision,
    figure_rolling,
)
from .report_m4 import (
    _publish_m4_diagnostics,
    build_m4_diagnostics,
    write_audit_report,
)
from .visualize import generate as generate_metric_figures


def generate_report(run_dir: Path, manifest: dict[str, Any]) -> None:
    metrics = run_dir / "metrics"
    figures = run_dir / "figures"
    tables = run_dir / "tables"
    core = figures / "core"
    optional = figures / "optional"
    audit_dir = figures / "audit"
    for path in (
        core,
        optional,
        audit_dir,
        tables / "core",
        tables / "optional",
        run_dir / "audits",
        run_dir / "logs",
    ):
        path.mkdir(parents=True, exist_ok=True)

    prediction_path = metrics / "m1_predictions_evaluation.parquet"
    summary_path = metrics / "m1_summary_evaluation.parquet"
    if prediction_path.exists() and summary_path.exists():
        prediction = pd.read_parquet(prediction_path)
        m1_summary = pd.read_parquet(summary_path)
        m1_summary = m1_summary.copy()
        m1_summary["evaluation_rows"] = int(len(prediction))
        _save_table(m1_summary, tables / "core" / "table01_m1_distributional_validity")

    scientific_gate_path = run_dir / "scientific_gate.json"
    if scientific_gate_path.exists():
        gates = json.loads(scientific_gate_path.read_text(encoding="utf-8"))
        acceptance = pd.DataFrame([
            {"gate_name": name, **details} for name, details in gates.items()
        ])
        _save_table(acceptance, run_dir / "audits" / "acceptance_checks")
        _save_table(acceptance, tables / "core" / "table02_interface_acceptance")

    m2_summary_path = metrics / "m2_summary.parquet"
    if m2_summary_path.exists():
        m2 = pd.read_parquet(m2_summary_path)
        rows = []
        for stage, group in m2.groupby("snapshot_stage", sort=False):
            row = {"snapshot_stage": stage, "snapshots": len(group)}
            for channel in ("F", "P", "R"):
                values = pd.to_numeric(group[f"cost_rmb_mean_{channel}"], errors="coerce")
                row[f"median_cost_rmb_{channel}"] = float(values.median())
                row[f"mean_cost_rmb_{channel}"] = float(values.mean())
            row["passenger_proxy_support_rate"] = float(group["passenger_proxy_used"].mean())
            rows.append(row)
        _save_table(pd.DataFrame(rows), tables / "core" / "table03_m2_channel_cost_summary")

    m3_parameters_path = run_dir / "m3_response_parameters.parquet"
    if m3_parameters_path.exists():
        _save_table(pd.read_parquet(m3_parameters_path), tables / "optional" / "table_m3_response_parameters")
    m3_audit_path = run_dir / "m3_response_audit.parquet"
    if m3_audit_path.exists():
        _save_table(
            pd.read_parquet(m3_audit_path),
            tables / "core" / "table04_m3_response_library",
        )

    candidate_path = run_dir / "m4_candidate_screen.parquet"
    ranking_path = run_dir / "m4_rankings.parquet"
    if candidate_path.exists() and ranking_path.exists():
        candidate = pd.read_parquet(candidate_path)
        ranking = pd.read_parquet(ranking_path)
        nonnull = candidate[candidate["action_id"].astype(str).ne("A00")]
        rows = []
        for stage, group in nonnull.groupby("snapshot_stage", sort=False):
            key_count = max(group[["episode_id", "snapshot_id"]].drop_duplicates().shape[0], 1)
            recommended = ranking[
                ranking["snapshot_stage"].astype(str).eq(str(stage))
                & ranking["recommended"].astype(bool)
            ]
            rows.append({
                "snapshot_stage": stage,
                "snapshots": key_count,
                "mean_physical_feasible_actions": float(group["physical_feasible"].sum() / key_count),
                "mean_decision_value_pass_actions": float((group["physical_feasible"] & group["decision_value_pass"]).sum() / key_count),
                "mean_evaluated_nonnull_actions": float(group["is_evaluated"].sum() / key_count),
                "a00_recommendation_rate": float(recommended["action_id"].astype(str).eq("A00").mean()) if len(recommended) else np.nan,
                "nonnull_recommendation_rate": float(recommended["action_id"].astype(str).ne("A00").mean()) if len(recommended) else np.nan,
            })
        _save_table(pd.DataFrame(rows), tables / "core" / "table05_m4_screening_and_recommendation")
        scientific = manifest.get("scientific", {})
        if scientific:
            _publish_m4_diagnostics(run_dir, candidate, ranking, scientific)

    # Publication figures are generated solely from frozen metric parquet tables.
    quantiles = list(manifest.get("quantiles", []))
    generate_metric_figures(run_dir, quantiles)

    primary_pred_path = metrics / "m1_predictions_evaluation.parquet"
    primary_summary_path = metrics / "m1_summary_evaluation.parquet"
    if not primary_pred_path.exists():
        primary_pred_path = metrics / "m1_predictions_all_valid.parquet"
    if not primary_summary_path.exists():
        primary_summary_path = metrics / "m1_summary_all_valid.parquet"
    if primary_pred_path.exists() and primary_summary_path.exists():
        figure_m1_validity(
            pd.read_parquet(primary_pred_path),
            pd.read_parquet(primary_summary_path),
            quantiles,
            core / "fig01_execution_risk_validity.png",
        )

    required = [
        metrics / "m4_rankings.parquet",
        primary_pred_path,
        metrics / "m4_physical_screening.parquet",
    ]
    balanced_path = run_dir / "cohorts" / "balanced_rolling.parquet"
    if all(path.exists() for path in required) and balanced_path.exists():
        ranking = pd.read_parquet(required[0])
        prediction = pd.read_parquet(required[1])
        audit = pd.read_parquet(required[2])
        balanced = pd.read_parquet(balanced_path)
        # The representative episode is produced by visualize.py; retain the
        # former rolling transition plot only as an audit diagnostic.
        figure_rolling(ranking, prediction, audit, balanced, audit_dir / "rolling_transition_diagnostic.png")
        figure_m3_appendix(audit, audit_dir / "gate_action_diagnostics.png")

    precision_action = run_dir / "precision" / "action_comparison.parquet"
    precision_summary = run_dir / "precision" / "precision_summary.parquet"
    if precision_action.exists() and precision_summary.exists():
        figure_precision(
            pd.read_parquet(precision_action),
            pd.read_parquet(precision_summary),
            audit_dir / "precision_convergence.png",
        )

    figure_metadata = pd.DataFrame([
        {
            "figure_id": "fig01_execution_risk_validity",
            "subject": "M1 execution-risk validity",
            "claim_boundary": "Distributional prediction diagnostic",
            "unit_note": "Risk probability, coverage, and CRPS",
        },
        {
            "figure_id": "fig02_channel_reconstruction",
            "subject": "M2 three-channel RMB reconstruction",
            "claim_boundary": "Constructed operational cost, not observed accounting cost",
            "unit_note": "Constructed cost (RMB); 1 internal unit = 1 RMB",
        },
        {
            "figure_id": "fig03_action_response_library",
            "subject": "M3 response library",
            "claim_boundary": "Declared scenario-response distributions; not observed causal effects",
            "unit_note": "Recovery rate and implementation cost (RMB)",
        },
        {
            "figure_id": "fig04_screening_and_recommendation",
            "subject": "M4 screening and recommendation",
            "claim_boundary": "Frozen physical and decision-value rules",
            "unit_note": "Rates, action counts, and recommendation shares",
        },
        {
            "figure_id": "fig05_representative_episode",
            "subject": "Rolling representative episode",
            "claim_boundary": "Deterministic median-risk case; not selected by method advantage",
            "unit_note": "Risk probability, constructed RMB cost, retained actions, Mean-CVaR score",
        },
    ])
    _save_table(figure_metadata, tables / "core" / "figure_metadata")
    (figures / "figure_metadata.json").write_text(
        json.dumps(figure_metadata.to_dict("records"), indent=2), encoding="utf-8"
    )


def publish_report(
    run_dir: Path,
    *,
    manifest: dict[str, Any],
    scientific: dict[str, Any],
    publication_implementation_hash: str,
) -> dict[str, Any]:
    missing = [relative for relative in PUBLICATION_SOURCE_PATHS if not (run_dir / relative).is_file()]
    if missing:
        raise FileNotFoundError("PUBLICATION_SOURCE_MISSING:" + ",".join(missing))
    source_hashes = {
        relative: _sha256(run_dir / relative) for relative in PUBLICATION_SOURCE_PATHS
    }
    report_manifest = dict(manifest)
    report_manifest["quantiles"] = list(scientific["m1"]["quantiles"])
    report_manifest["scientific"] = scientific
    generate_report(run_dir, report_manifest)

    generated_roots = ("tables", "figures", "audits", "logs")
    publication_log = run_dir / "logs" / "publication.log"
    publication_log.write_text(
        "\n".join([
            f"run_id={manifest.get('run_id')}",
            f"config_hash={manifest.get('config_hash')}",
            f"scientific_status={manifest.get('scientific_status', 'STOP_AND_REVIEW')}",
            f"publication_implementation_hash={publication_implementation_hash}",
            "source_policy=frozen_artifacts_only",
            "scientific_values_modified=false",
            "publication_status=PASS",
            "",
        ]),
        encoding="utf-8",
    )
    output_hashes = {
        path.relative_to(run_dir).as_posix(): _sha256(path)
        for root_name in generated_roots
        for path in sorted((run_dir / root_name).rglob("*"))
        if path.is_file()
    }
    publication = {
        "status": "PASS",
        "run_id": manifest.get("run_id"),
        "mode": manifest.get("mode"),
        "config_hash": manifest.get("config_hash"),
        "scientific_implementation_hash": manifest.get("implementation_hash"),
        "publication_implementation_hash": publication_implementation_hash,
        "scientific_status": manifest.get("scientific_status", "STOP_AND_REVIEW"),
        "full_recommended": False,
        "source_policy": "FROZEN_ARTIFACTS_ONLY",
        "source_hashes": source_hashes,
        "output_hashes": output_hashes,
        "core_figure_stems": list(CORE_FIGURE_STEMS),
        "figure_formats": ["png", "pdf", "svg"],
        "m4_near_threshold_tolerance": 0.02,
        "scientific_values_modified": False,
    }
    (run_dir / "publication_manifest.json").write_text(
        json.dumps(publication, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return publication


def validate_publication(
    run_dir: Path,
    *,
    expected_run_id: str,
    expected_config_hash: str,
    expected_scientific_status: str,
    expected_publication_implementation_hash: str,
) -> dict[str, Any]:
    required_directories = (
        "metrics", "tables/core", "tables/optional", "figures/core",
        "figures/audit", "figures/optional", "audits", "logs",
    )
    missing_directories = [name for name in required_directories if not (run_dir / name).is_dir()]
    if missing_directories:
        raise ValueError("PUBLICATION_DIRECTORY_MISSING:" + ",".join(missing_directories))
    required_files = [
        "publication_manifest.json",
        "tables/core/table01_m1_distributional_validity.parquet",
        "tables/core/table03_m2_channel_cost_summary.parquet",
        "tables/core/table04_m3_response_library.parquet",
        "tables/core/table05_m4_screening_and_recommendation.parquet",
        "tables/core/figure_metadata.parquet",
        "figures/figure_metadata.json",
        "logs/publication.log",
        *[f"audits/{name}" for name in M4_AUDIT_FILES],
        *[
            f"figures/core/{stem}.{suffix}"
            for stem in CORE_FIGURE_STEMS
            for suffix in ("png", "pdf", "svg")
        ],
    ]
    missing_files = [name for name in required_files if not (run_dir / name).is_file()]
    if missing_files:
        raise ValueError("PUBLICATION_FILE_MISSING:" + ",".join(missing_files))
    if not any(path.stat().st_size > 0 for path in (run_dir / "logs").glob("*.log")):
        raise ValueError("PUBLICATION_LOG_MISSING_OR_EMPTY")

    publication = json.loads((run_dir / "publication_manifest.json").read_text(encoding="utf-8"))
    expected_metadata = {
        "run_id": expected_run_id,
        "config_hash": expected_config_hash,
        "scientific_status": expected_scientific_status,
        "publication_implementation_hash": expected_publication_implementation_hash,
        "scientific_values_modified": False,
    }
    for key, expected in expected_metadata.items():
        if publication.get(key) != expected:
            raise ValueError(f"PUBLICATION_{key.upper()}_MISMATCH")
    for relative, expected_hash in publication.get("source_hashes", {}).items():
        path = run_dir / relative
        if not path.is_file() or _sha256(path) != expected_hash:
            raise ValueError(f"PUBLICATION_SOURCE_HASH_MISMATCH:{relative}")
    for relative, expected_hash in publication.get("output_hashes", {}).items():
        path = run_dir / relative
        if not path.is_file() or _sha256(path) != expected_hash:
            raise ValueError(f"PUBLICATION_OUTPUT_HASH_MISMATCH:{relative}")

    registry_path = run_dir / "artifact_registry.json"
    if not registry_path.is_file():
        raise ValueError("PUBLICATION_REGISTRY_MISSING")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = {str(row.get("artifact_name")): row for row in registry.get("artifacts", [])}
    for relative in required_files:
        if relative not in entries:
            raise ValueError(f"PUBLICATION_ARTIFACT_NOT_REGISTERED:{relative}")
        if entries[relative].get("sha256") != _sha256(run_dir / relative):
            raise ValueError(f"PUBLICATION_ARTIFACT_HASH_MISMATCH:{relative}")
    return {
        "status": "PASS",
        "run_id": expected_run_id,
        "scientific_status": expected_scientific_status,
        "full_recommended": False,
        "core_figure_triplets": len(CORE_FIGURE_STEMS),
        "registered_artifact_count": len(entries),
        "table_file_count": len(list((run_dir / "tables").rglob("*.*"))),
        "audit_file_count": len(list((run_dir / "audits").rglob("*.*"))),
        "log_file_count": len(list((run_dir / "logs").glob("*.log"))),
    }


__all__ = [
    "CORE_FIGURE_STEMS",
    "M4_AUDIT_FILES",
    "PUBLICATION_SOURCE_PATHS",
    "build_m4_diagnostics",
    "generate_report",
    "publish_report",
    "validate_publication",
    "write_audit_report",
]
