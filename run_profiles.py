from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# ============================================================
# RUN_SCALES_V1_20260801 — Three formal run scales
# ============================================================
RUN_SCALE_CONTRACT_VERSION = "RUN_SCALES_V1_20260801"

# Fast: engineering gate, 5 fixed anchor days
FAST_CONTRACT_ID = "FAST_5D_V1"
FAST_ANCHOR_DAY_COUNT = 5

# Middle: current-data source-bounded, 23 days (14/5/4)
MIDDLE_CONTRACT_ID = "CURRENT_DATA_MIDDLE_23D_V1"
MIDDLE_ANCHOR_DAY_COUNT = 23
MIDDLE_SPLIT = {"train": 14, "validation": 5, "test": 4}
MIDDLE_EXPECTED_HOURS = 552

# Full: FORMAL_72 design, 72 days (40/20/12)
FULL_CONTRACT_ID = "FORMAL_72_FULL_V1_20260724"
FULL_ANCHOR_DAY_COUNT = 72
FULL_ROLE_COUNTS = {"model": 40, "audit": 20, "final_test": 12}
FULL_REQUIRED_HOURS = 3024

THREAD_DEFAULTS = {"pre": 1, "downstream": 14}

# Legacy: adapt_full is a read-only alias to middle source
PROFILE_ALIASES = {"adapt_full": "middle"}
KNOWN_PROFILES = {
    "fast", "middle", "full",
    "diagnostic",           # diagnostic overlay, not a scale
    "precision",            # precision overlay, not a scale
    "acceptance_23d",       # legacy historical compatibility
}
FORMAL_SCALES = {"fast", "middle", "full"}
LEGACY_READ_ONLY = {"adapt_full", "acceptance_23d"}
OVERLAY_ONLY = {"diagnostic", "precision"}


@dataclass(frozen=True)
class ProfileContract:
    requested_token: str
    profile_id: str
    run_profile: str | None
    acceptance_profile: str | None
    compute_profile: str
    legacy_token: str | None
    smoke_subset: bool
    output_id: str
    contract_id: str
    is_formal_scale: bool
    is_legacy_read_only: bool


def resolve_profile(token: str, *, smoke_subset: bool = False, new_run: bool = True) -> ProfileContract:
    profile_id = PROFILE_ALIASES.get(token, token)
    if profile_id not in KNOWN_PROFILES:
        raise ValueError(f"UNKNOWN_PROFILE:{token}")
    if new_run and token in LEGACY_READ_ONLY and token != profile_id:
        raise ValueError(f"LEGACY_PROFILE_NEW_RUN_NOT_ALLOWED:{token} — use '{profile_id}' instead")
    if smoke_subset and profile_id != "middle":
        raise ValueError("SMOKE_SUBSET_ONLY_SUPPORTED_FOR_MIDDLE")

    is_formal = profile_id in FORMAL_SCALES
    is_legacy = token in LEGACY_READ_ONLY
    legacy = "adapt_full" if token == "adapt_full" else ("acceptance_23d" if token == "acceptance_23d" else None)

    if profile_id == "fast":
        contract_id = FAST_CONTRACT_ID
    elif profile_id == "middle":
        contract_id = MIDDLE_CONTRACT_ID
    elif profile_id == "full":
        contract_id = FULL_CONTRACT_ID
    else:
        contract_id = "LEGACY_OR_OVERLAY"

    acceptance = "acceptance_23d" if profile_id == "acceptance_23d" else None
    run_profile = None if acceptance else profile_id
    compute_profile = "full" if profile_id in {"middle", "full", "acceptance_23d"} else profile_id

    return ProfileContract(
        requested_token=token,
        profile_id=profile_id,
        run_profile=run_profile,
        acceptance_profile=acceptance,
        compute_profile=compute_profile,
        legacy_token=legacy,
        smoke_subset=smoke_subset,
        output_id=f"{profile_id}_smoke" if smoke_subset else profile_id,
        contract_id=contract_id,
        is_formal_scale=is_formal,
        is_legacy_read_only=is_legacy,
    )


def profile_metadata(token: str, *, smoke_subset: bool = False) -> dict[str, Any]:
    return asdict(resolve_profile(token, smoke_subset=smoke_subset))


def full_data_readiness(manifest_path: Path) -> dict[str, Any]:
    frame = pd.read_csv(manifest_path)
    dates = pd.Series(pd.to_datetime(frame["anchor_date"], errors="raise").dt.normalize().unique()).sort_values()
    complete = set(dates.tolist())
    months = sorted({(value.year, value.month) for value in dates})
    ready_months: list[str] = []
    for year, month in months:
        start = pd.Timestamp(year=year, month=month, day=1)
        end = start + pd.offsets.MonthEnd(0)
        expected = set(pd.date_range(start, end, freq="D").tolist())
        if expected.issubset(complete):
            ready_months.append(start.strftime("%Y-%m"))
    return {
        "status": "READY" if ready_months else "NOT_READY",
        "manifest_path": str(manifest_path.resolve()),
        "complete_anchor_day_count": len(complete),
        "continuous_complete_months": ready_months,
        "criterion": "AT_LEAST_ONE_CONTINUOUS_COMPLETE_CALENDAR_MONTH_OR_ALL_QUALIFIED_DATA",
    }
