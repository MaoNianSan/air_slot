from __future__ import annotations

from overall_run.src.m1.adapter import M1FeatureSchema, build_snapshot_node


def test_operational_references_are_built_by_adapter(published_bundle) -> None:
    schema = M1FeatureSchema.from_column_registry(published_bundle.column_registry)
    node = build_snapshot_node(
        published_bundle, "ep-1", "2026-01-01T10:40:00Z", schema
    )
    references = node.operational_references
    assert references.successor_sobt.active
    assert references.turnaround_floor_minutes.active
    assert references.turnaround_floor_minutes.source_field == "turnaround_floor_minutes"
    assert references.taxi_reference_minutes.active


def test_empirical_turnaround_is_not_a_hard_floor(published_bundle) -> None:
    published_bundle.episodes.loc[0, "turnaround_reference_type"] = "EMPIRICAL_REFERENCE"
    schema = M1FeatureSchema.from_column_registry(published_bundle.column_registry)
    node = build_snapshot_node(
        published_bundle, "ep-1", "2026-01-01T10:40:00Z", schema
    )
    assert not node.operational_references.turnaround_floor_minutes.active
    assert "OFFICIAL_FLOOR" in node.operational_references.turnaround_floor_minutes.inactive_reason
