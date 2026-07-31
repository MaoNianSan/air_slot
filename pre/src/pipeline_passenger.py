from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .input import write_json, write_parquet
from .pipeline_diagnostics import _passenger_supported
from .validate import PreBundle


def _write_passenger_month_outputs(
    bundle: PreBundle,
    passenger_reference: Any,
    paths: dict[str, Path],
    cfg: dict[str, Any],
    validation: dict[str, Any],
    readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    snapshots = bundle.snapshots.copy()
    scope = snapshots[
        snapshots["snapshot_valid"].fillna(False)
        & snapshots["formal_eligible"].fillna(False)
    ].copy()
    scope["_passenger_supported"] = _passenger_supported(scope)

    by_split = (
        scope.groupby("split", dropna=False)
        .agg(
            rows=("snapshot_id", "size"),
            supported_rows=("_passenger_supported", "sum"),
            support_rate=("_passenger_supported", "mean"),
            supported_recovery_cases=("episode_id", lambda values: 0),
        )
        .reset_index()
    )
    split_case_counts = (
        scope.loc[scope["_passenger_supported"]]
        .groupby("split")["episode_id"]
        .nunique()
    )
    by_split["supported_recovery_cases"] = (
        by_split["split"].map(split_case_counts).fillna(0).astype(int)
    )
    by_airport = (
        scope.groupby("airport", dropna=False)
        .agg(
            rows=("snapshot_id", "size"),
            supported_rows=("_passenger_supported", "sum"),
            support_rate=("_passenger_supported", "mean"),
            unsupported_rows=("_passenger_supported", lambda values: int((~values).sum())),
        )
        .reset_index()
    )
    by_source_period = (
        scope.assign(
            passenger_source_period=scope["passenger_source_period"].replace(
                "", "UNSUPPORTED"
            )
        )
        .groupby("passenger_source_period", dropna=False)
        .agg(
            rows=("snapshot_id", "size"),
            supported_rows=("_passenger_supported", "sum"),
            support_rate=("_passenger_supported", "mean"),
        )
        .reset_index()
    )
    fallback_distribution = (
        scope.groupby(
            [
                "passenger_used_level",
                "passenger_evidence_status",
                "passenger_missing_reason",
                "passenger_lag_months",
            ],
            dropna=False,
        )
        .size()
        .rename("rows")
        .reset_index()
    )
    for name, frame in [
        ("passenger_support_by_split.parquet", by_split),
        ("passenger_support_by_airport.parquet", by_airport),
        ("passenger_support_by_source_period.parquet", by_source_period),
        ("passenger_fallback_distribution.parquet", fallback_distribution),
    ]:
        write_parquet(frame, paths["root"] / name)
        write_parquet(frame, paths["reports"] / name)

    selection_source = (
        cfg["project_root"].parent
        / "data"
        / "manifests"
        / "fast_month_selection_audit.csv"
    )
    if not selection_source.exists():
        raise FileNotFoundError(
            f"missing deterministic Fast month audit: {selection_source}"
        )
    shutil.copy2(selection_source, paths["root"] / "fast_month_selection_audit.csv")

    future_count = int(
        scope["passenger_future_data_used"].fillna(False).astype(bool).sum()
    )
    unsupported = ~scope["_passenger_supported"]
    unsupported_zero_count = int(
        sum(
            (
                unsupported
                & pd.to_numeric(scope[field], errors="coerce").eq(0)
            ).sum()
            for field in [
                "estimated_passenger_load",
                "connection_pressure_proxy",
                "rebooking_scarcity_proxy",
            ]
        )
    )
    supported_rows = int(scope["_passenger_supported"].sum())
    supported_cases = int(
        scope.loc[scope["_passenger_supported"], "episode_id"].nunique()
    )
    total_cases = int(scope["episode_id"].nunique())
    split_support_nonempty = bool(
        set(by_split["split"].astype(str)) == {"train", "validation", "test"}
        and by_split["supported_rows"].gt(0).all()
    )
    evidence_lineage = bool(
        (
            ~scope["_passenger_supported"]
            | (
                scope["passenger_source_period"].astype(str).ne("")
                & pd.to_numeric(
                    scope["passenger_lag_months"], errors="coerce"
                ).between(
                    1,
                    int(
                        cfg["references"]["passenger"].get(
                            "maximum_lag_months", 3
                        )
                    ),
                    inclusive="both",
                )
            )
        ).all()
        and (
            scope["_passenger_supported"]
            | scope["passenger_missing_reason"].astype(str).ne("")
        ).all()
    )
    contract_gate = bool(
        validation.get("status") == "PASS"
        and readiness_summary.get("status") == "PASS"
    )
    m4_nonempty = supported_cases > 0
    if (
        not contract_gate
        or future_count > 0
        or unsupported_zero_count > 0
        or not evidence_lineage
        or supported_rows == 0
        or not m4_nonempty
    ):
        passenger_status = "FAIL"
    elif not split_support_nonempty or supported_cases < 8:
        passenger_status = "STOP_AND_REVIEW"
    elif supported_rows == len(scope):
        passenger_status = "PASS"
    else:
        passenger_status = "PARTIAL_SUPPORT_ACCEPTED"

    anchors = (
        bundle.episodes[
            bundle.episodes["formal_eligible"].fillna(False)
        ][["anchor_date", "split"]]
        .drop_duplicates()
        .sort_values("anchor_date")
    )
    source_period_counts = (
        scope["passenger_source_period"]
        .replace("", "UNSUPPORTED")
        .value_counts()
        .to_dict()
    )
    lag_counts = (
        scope["passenger_lag_months"]
        .astype("string")
        .fillna("UNSUPPORTED")
        .value_counts()
        .to_dict()
    )
    fallback_rows = int(
        scope["passenger_evidence_status"].eq("FALLBACK_PROXY").sum()
    )
    summary = {
        "selected_fast_month": str(
            pd.Period(
                pd.to_datetime(anchors["anchor_date"]).min(), freq="M"
            )
        ),
        "selected_anchor_dates": anchors["anchor_date"].astype(str).tolist(),
        "train_dates": anchors.loc[
            anchors["split"].eq("train"), "anchor_date"
        ].astype(str).tolist(),
        "validation_dates": anchors.loc[
            anchors["split"].eq("validation"), "anchor_date"
        ].astype(str).tolist(),
        "test_dates": anchors.loc[
            anchors["split"].eq("test"), "anchor_date"
        ].astype(str).tolist(),
        "engineering_status": (
            "PASS" if contract_gate else "FAIL"
        ),
        "passenger_status": passenger_status,
        "passenger_support_policy": "PARTIAL_SUPPORT_ALLOWED",
        "passenger_support_rate_overall": (
            float(supported_rows / len(scope)) if len(scope) else 0.0
        ),
        "passenger_support_rate_by_split": {
            str(row.split): float(row.support_rate)
            for row in by_split.itertuples(index=False)
        },
        "passenger_support_rate_by_airport": {
            str(row.airport): float(row.support_rate)
            for row in by_airport.itertuples(index=False)
        },
        "passenger_source_period_distribution": source_period_counts,
        "lag_month_distribution": lag_counts,
        "fallback_rate": (
            float(fallback_rows / len(scope)) if len(scope) else 0.0
        ),
        "unsupported_rate": (
            float(unsupported.sum() / len(scope)) if len(scope) else 0.0
        ),
        "unsupported_zero_count": unsupported_zero_count,
        "future_data_used_count": future_count,
        "evidence_lineage_gate": "PASS" if evidence_lineage else "FAIL",
        "contract_gate": "PASS" if contract_gate else "FAIL",
        "future_data_gate": "PASS" if future_count == 0 else "FAIL",
        "total_recovery_cases": total_cases,
        "passenger_supported_cases": supported_cases,
        "passenger_unsupported_cases": total_cases - supported_cases,
        "supported_recovery_cases": supported_cases,
        "m4_supported_cohort_nonempty": m4_nonempty,
        "m4_supported_cohort_rate": (
            float(supported_cases / total_cases) if total_cases else 0.0
        ),
        "actual_highest_supported_level": passenger_reference.metadata.get(
            "actual_highest_supported_level"
        ),
        "reference_cutoff": passenger_reference.metadata,
    }
    write_json(summary, paths["root"] / "PASSENGER_MONTH_FAST_SUMMARY.json")
    write_json(summary, paths["reports"] / "PASSENGER_MONTH_FAST_SUMMARY.json")
    report = f"""# Passenger Month Fast Report

- selected_fast_month: `{summary['selected_fast_month']}`
- selected_anchor_dates: `{summary['selected_anchor_dates']}`
- train_dates: `{summary['train_dates']}`
- validation_dates: `{summary['validation_dates']}`
- test_dates: `{summary['test_dates']}`
- engineering_status: `{summary['engineering_status']}`
- passenger_status: `{passenger_status}`
- passenger_support_policy: `PARTIAL_SUPPORT_ALLOWED`
- passenger_support_rate_overall: `{summary['passenger_support_rate_overall']:.6f}`
- passenger_source_period_distribution: `{source_period_counts}`
- lag_month_distribution: `{lag_counts}`
- fallback_rate: `{summary['fallback_rate']:.6f}`
- unsupported_rate: `{summary['unsupported_rate']:.6f}`
- unsupported_zero_count: `{unsupported_zero_count}`
- future_data_used_count: `{future_count}`
- supported_recovery_cases: `{supported_cases}`
- m4_supported_cohort_rate: `{summary['m4_supported_cohort_rate']:.6f}`

The only active passenger level is `DESTINATION_LAGGED_MONTH`; OD levels are
source-unavailable audit entries. Monthly values are selected from the most
recent actually present period ending before the snapshot month, with a
maximum three-month lookback. Missing source months remain unsupported and are
never interpolated, set to zero, or filled from the target month.
"""
    (paths["root"] / "PASSENGER_MONTH_FAST_REPORT.md").write_text(
        report, encoding="utf-8"
    )
    (paths["reports"] / "PASSENGER_MONTH_FAST_REPORT.md").write_text(
        report, encoding="utf-8"
    )
    return summary


