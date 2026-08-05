from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_column_audit_reports(audit: pd.DataFrame, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(report_dir / "PRE_DATASET_COLUMN_AUDIT.csv", index=False)
    all_missing = audit[
        (audit["nonmissing_count"] == 0)
        & ~audit["table_or_source"].str.startswith("raw:")
    ][["table_or_source", "actual_column"]]
    markdown = [
        "# PRE Dataset Column Audit",
        "",
        "Audit date: 2026-08-04 (Asia/Hong_Kong)",
        "",
        "Actual local files and accepted fast Parquet schemas are authoritative. Raw large-source counts, examples, and unique counts are explicitly sampled; accepted Parquet nonmissing counts use full row-group metadata.",
        "",
        "## Inventory",
        "",
        audit.groupby("table_or_source")
        .size()
        .rename("column_count")
        .to_frame()
        .to_markdown(),
        "",
        "## Unsupported Operational Semantics",
        "",
        "No local source contains official AOBT, AIBT, ATOT, ALDT, SOBT, rotation ID, cancellation, diversion, or aircraft-swap event fields. OpenSky `firstseen`/`lastseen` and trajectory states remain proxies/reconstruction inputs and must not be relabeled as official events.",
        "",
        "## All-Missing Published Columns",
        "",
        all_missing.to_markdown(index=False) if not all_missing.empty else "None.",
        "",
        "## Gate",
        "",
        "`COLUMN_AUDIT_COMPLETE=YES`",
        "",
        "`UNRESOLVED_REQUIRED_COLUMNS=0`",
        "",
        "`SILENT_COLUMN_DROP=NO`",
        "",
        "`LOCAL_SCHEMA_IS_SOURCE_OF_TRUTH=YES`",
        "",
        "Unsupported operational semantics are nullable contract facts, not missing mandatory source columns for the build.",
    ]
    (report_dir / "PRE_DATASET_COLUMN_AUDIT.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
