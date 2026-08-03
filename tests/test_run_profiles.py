"""Three-scale profile contract tests — RUN_SCALES_V1_20260801."""
from __future__ import annotations

from pathlib import Path

import pytest

from run_profiles import (
    FAST_ANCHOR_DAY_COUNT, FULL_ANCHOR_DAY_COUNT, FULL_ROLE_COUNTS, FULL_REQUIRED_HOURS,
    MIDDLE_ANCHOR_DAY_COUNT, MIDDLE_EXPECTED_HOURS, MIDDLE_SPLIT,
    FORMAL_SCALES, LEGACY_READ_ONLY, OVERLAY_ONLY, RUN_SCALE_CONTRACT_VERSION,
    full_data_readiness, resolve_profile,
)

ROOT = Path(__file__).resolve().parents[1]

# ============================================================
# Three formal scales
# ============================================================
def test_only_three_formal_scales() -> None:
    assert FORMAL_SCALES == {"fast", "middle", "full"}
    assert len(FORMAL_SCALES) == 3


def test_run_scale_contract_version() -> None:
    assert RUN_SCALE_CONTRACT_VERSION == "RUN_SCALES_V1_20260801"


def test_fast_is_5_days() -> None:
    p = resolve_profile("fast")
    assert p.profile_id == "fast"
    assert p.contract_id == "FAST_5D_V1"
    assert p.is_formal_scale is True
    assert p.output_id == "fast"


def test_fast_is_only_engineering_gate() -> None:
    p = resolve_profile("fast")
    assert p.run_profile == "fast"
    assert p.compute_profile == "fast"


def test_middle_is_23_days() -> None:
    p = resolve_profile("middle")
    assert p.profile_id == "middle"
    assert p.contract_id == "CURRENT_DATA_MIDDLE_23D_V1"
    assert p.is_formal_scale is True
    assert p.output_id == "middle"


def test_middle_split_is_14_5_4() -> None:
    assert MIDDLE_SPLIT == {"train": 14, "validation": 5, "test": 4}
    assert MIDDLE_ANCHOR_DAY_COUNT == 23


def test_middle_expected_hours_is_552() -> None:
    assert MIDDLE_EXPECTED_HOURS == 552


def test_middle_smoke_is_explicit_and_isolated() -> None:
    p = resolve_profile("middle", smoke_subset=True)
    assert p.run_profile == "middle"
    assert p.smoke_subset is True
    assert p.output_id == "middle_smoke"


def test_full_is_72_days() -> None:
    assert FULL_ANCHOR_DAY_COUNT == 72


def test_full_role_counts_are_40_20_12() -> None:
    assert FULL_ROLE_COUNTS == {"model": 40, "audit": 20, "final_test": 12}


def test_full_required_hours_is_3024() -> None:
    assert FULL_REQUIRED_HOURS == 3024


def test_full_not_ready_does_not_fallback() -> None:
    p = resolve_profile("full")
    assert p.profile_id == "full"
    assert p.is_formal_scale is True


def test_adapt_full_is_read_only_legacy_alias() -> None:
    with pytest.raises(ValueError, match="LEGACY_PROFILE_NEW_RUN_NOT_ALLOWED"):
        resolve_profile("adapt_full")
    assert "adapt_full" in LEGACY_READ_ONLY


def test_legacy_not_in_formal_scales() -> None:
    assert not (LEGACY_READ_ONLY & FORMAL_SCALES)
    assert not (OVERLAY_ONLY & FORMAL_SCALES)


def test_no_automatic_profile_fallback() -> None:
    with pytest.raises(ValueError):
        resolve_profile("nonexistent")


def test_only_fast_middle_full_output_paths() -> None:
    for token in FORMAL_SCALES:
        p = resolve_profile(token)
        assert p.output_id == token
        assert p.output_id in FORMAL_SCALES


def test_fast_profile_contract_is_unchanged() -> None:
    p = resolve_profile("fast")
    assert p.run_profile == "fast"
    assert p.acceptance_profile is None
    assert p.compute_profile == "fast"
    assert p.output_id == "fast"
    assert p.contract_id == "FAST_5D_V1"


def test_middle_profile_contract() -> None:
    p = resolve_profile("middle")
    assert p.run_profile == "middle"
    assert p.compute_profile == "full"
    assert p.output_id == "middle"
    assert p.contract_id == "CURRENT_DATA_MIDDLE_23D_V1"


def test_local_full_data_is_not_ready() -> None:
    result = full_data_readiness(
        ROOT / "data" / "manifests" / "current_data_adapt_full_manifest.csv"
    )
    assert result["status"] == "NOT_READY"
