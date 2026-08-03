from __future__ import annotations

from pathlib import Path

from analysis.p1_event_reconstruction.run_profiles import build_profiles


def test_profile_contract_separates_scale_from_target() -> None:
    root = Path(__file__).resolve().parents[2]
    profiles, mapping = build_profiles(root)
    assert profiles["fast"].source_semantics == "existing fast selection unchanged"
    assert profiles["middle"].data_design_id == "FORMAL_72_V1_20260724"
    assert profiles["full"].full_scope_type == "all_available"
    assert not profiles["full"].allow_partial_day
    assert mapping["legacy_full72"] == "middle"
