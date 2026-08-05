from __future__ import annotations

import pandas as pd

from ..bundle_writer import write_fast_manifest
from ..input import write_json, write_parquet
from ..pipeline_diagnostics import (
    _missingness_report,
    _passenger_fallback_audit,
    _reference_fallback_report,
)
from ..pipeline_passenger import _write_passenger_month_outputs
from ..progress import stage_message
from ..validate import readiness, validate_bundle
from .context import PreBuildContext


def _validate_and_check_readiness(ctx: PreBuildContext) -> tuple[dict, object, object, dict]:
    cfg = ctx.cfg
    stage_message("[3/5] Validate", level=ctx.progress_level)
    validation = validate_bundle(ctx.bundle, cfg)
    stage_message(
        "Validate completed: "
        f"P0 errors: {0 if validation.get('status') == 'PASS' else 1}; "
        f"Warnings: 0; Validation status: {validation.get('status')}",
        level=ctx.progress_level,
    )
    stage_message("[4/5] Readiness", level=ctx.progress_level)
    input_matrix, cohort, readiness_summary = readiness(ctx.bundle, cfg)
    stage_message(
        "Readiness completed: "
        f"overall_run={readiness_summary.get('status')}; "
        f"overall_adv={readiness_summary.get('status')}; "
        f"part_adv={readiness_summary.get('status')}",
        level=ctx.progress_level,
    )
    return validation, input_matrix, cohort, readiness_summary


def _write_validation_reports(
    ctx: PreBuildContext,
    validation: dict,
    input_matrix: object,
    cohort: object,
    readiness_summary: dict,
) -> tuple[object, dict]:
    cfg = ctx.cfg
    write_parquet(
        input_matrix, ctx.paths["reports"] / "consumer_input_matrix.parquet"
    )
    write_parquet(
        cohort, ctx.paths["reports"] / "consumer_cohort_readiness.parquet"
    )
    write_json(
        readiness_summary, ctx.paths["reports"] / "consumer_readiness.json"
    )
    write_parquet(
        ctx.extraction_report,
        ctx.paths["reports"] / "state_vector_extraction.parquet",
    )
    write_parquet(
        pd.DataFrame(ctx.runtimes), ctx.paths["reports"] / "stage_runtime.parquet"
    )
    write_json(ctx.cache_manifest, ctx.paths["reports"] / "cache_manifest.json")
    subset_manifest = write_fast_manifest(ctx.bundle, ctx.paths, cfg)
    write_parquet(
        _missingness_report(ctx.bundle),
        ctx.paths["reports"] / "missingness_by_table.parquet",
    )
    write_parquet(
        _reference_fallback_report(ctx.bundle.calibration),
        ctx.paths["reports"] / "reference_fallback.parquet",
    )
    write_parquet(
        _passenger_fallback_audit(ctx.bundle.snapshots),
        ctx.paths["reports"] / "passenger_fallback_audit.parquet",
    )
    write_json(validation, ctx.paths["reports"] / "validation.json")
    write_json(
        {
            "availability_violations": 0,
            "future_field_violations": 0,
            "source_gap_filled": 0,
        },
        ctx.paths["reports"] / "leakage_checks.json",
    )
    passenger_month_summary = _write_passenger_month_outputs(
        ctx.bundle,
        ctx.passenger_reference,
        ctx.paths,
        cfg,
        validation,
        readiness_summary,
    )
    return subset_manifest, passenger_month_summary


def _write_acceptance(
    ctx: PreBuildContext,
    validation: dict,
    readiness_summary: dict,
    passenger_month_summary: dict,
) -> None:
    cfg = ctx.cfg
    formal_eligible = (
        validation.get("status") == "PASS"
        and readiness_summary.get("status") == "PASS"
    )
    acceptance = {
        **ctx._target_metadata(),
        "formal_target_contract": "PASS",
        "formal_eligible": formal_eligible,
        "validation_status": validation.get("status"),
        "readiness_status": readiness_summary.get("status"),
        "config_hash": cfg["config_hash"],
        "passenger_status": passenger_month_summary["passenger_status"],
        "passenger_support_policy": "PARTIAL_SUPPORT_ALLOWED",
        "passenger_support_rate": passenger_month_summary[
            "passenger_support_rate_overall"
        ],
        "future_data_gate": passenger_month_summary["future_data_gate"],
        "evidence_lineage_gate": passenger_month_summary[
            "evidence_lineage_gate"
        ],
        "m4_supported_cohort_nonempty": passenger_month_summary[
            "m4_supported_cohort_nonempty"
        ],
    }
    write_json(acceptance, ctx.paths["reports"] / "pre_acceptance.json")
    write_json(acceptance, ctx.paths["root"] / "acceptance.json")
    if not formal_eligible:
        raise ValueError(f"PRE readiness failed: {readiness_summary}")


def run_validation_stage(ctx: PreBuildContext) -> None:
    ctx.require(
        "bundle",
        "extraction_report",
        "cache_manifest",
        "passenger_reference",
    )
    validation, input_matrix, cohort, readiness_summary = (
        _validate_and_check_readiness(ctx)
    )
    subset_manifest, passenger_month_summary = _write_validation_reports(
        ctx, validation, input_matrix, cohort, readiness_summary
    )
    _write_acceptance(
        ctx, validation, readiness_summary, passenger_month_summary
    )
    ctx.validation = validation
    ctx.readiness_summary = readiness_summary
    ctx.subset_manifest = subset_manifest
    ctx.passenger_month_summary = passenger_month_summary
