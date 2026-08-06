from __future__ import annotations

from overall_run.src.m1.adapter import M1FeatureSchema, build_episode_sequence


def test_episode_sequence_uses_five_minute_query_grid(published_bundle) -> None:
    schema = M1FeatureSchema.from_column_registry(published_bundle.column_registry)
    sequence = build_episode_sequence(
        published_bundle,
        "ep-1",
        schema,
        roll_minutes=5,
        up_to_query_time="2026-01-01T10:15:00Z",
    )
    assert len(sequence.snapshots) == 4
    assert [node.query_time.minute for node in sequence.snapshots] == [0, 5, 10, 15]
    assert all(node.feature_schema_hash == schema.schema_hash for node in sequence.snapshots)
    assert all(node.information_cutoff <= node.query_time for node in sequence.snapshots)
