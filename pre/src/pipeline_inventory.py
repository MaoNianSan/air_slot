from __future__ import annotations

from typing import Any

import pandas as pd

from .input import write_json, write_parquet
from .inventory import complete_state_dates, inventory, state_coverage_calendar
from .pipeline_config import _ensure_dirs
from .progress import stage_message


def run_inventory(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    progress_level = cfg["runtime"]["progress_level"]
    stage_message("Inventory", level=progress_level)
    output = cfg["output_root"]
    paths = _ensure_dirs(output)
    raw_inventory = inventory(cfg)
    coverage = state_coverage_calendar(raw_inventory, cfg)
    write_parquet(raw_inventory, paths["manifests"] / "raw_inventory.parquet")
    write_parquet(coverage, paths["manifests"] / "state_vector_coverage_calendar.parquet")
    write_json(
        {
            "files": len(raw_inventory),
            "state_vector_hours": len(coverage),
            "formal_complete_dates": sorted({str(pd.Timestamp(date).date()) for date in complete_state_dates(coverage, cfg)}),
        },
        paths["reports"] / "inventory_summary.json",
    )
    _inventory_summary(raw_inventory, coverage, cfg, progress_level)
    return raw_inventory, coverage


def _inventory_summary(
    raw_inventory: pd.DataFrame,
    coverage: pd.DataFrame,
    cfg: dict[str, Any],
    progress_level: str,
) -> None:
    missing_required = sum(
        1
        for source, spec in cfg["sources"].items()
        if spec.get("required", False)
        and (raw_inventory.empty or not (raw_inventory["source"] == source).any())
    )
    stage_message(
        "Inventory completed: "
        f"{len(raw_inventory)} files, {int((raw_inventory['source'] == 'state_vectors').sum()) if not raw_inventory.empty else 0} state-vector archives\n"
        f"Raw files: {len(raw_inventory)}\n"
        f"Readable files: {int(raw_inventory['readable'].sum()) if not raw_inventory.empty else 0}\n"
        f"Missing required sources: {missing_required}\n"
        f"State-vector hours expected: {len(coverage)}\n"
        f"State-vector hours available: {int(coverage['archive_readable'].sum()) if not coverage.empty else 0}\n"
        f"Formal eligible hours: {int(coverage['formal_eligible'].sum()) if not coverage.empty else 0}",
        level=progress_level,
    )


