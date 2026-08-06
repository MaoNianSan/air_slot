from __future__ import annotations

import pandas as pd

from overall_run.src.m1.adapter import M1FeatureSchema, build_snapshot_node
from overall_run.src.m1.adapter.availability import available_observations


def test_future_availability_is_excluded_even_when_event_time_is_old(published_bundle) -> None:
    frame = available_observations(
        published_bundle.observations,
        published_bundle.observation_membership,
        "ep-1",
        pd.Timestamp("2026-01-01 10:40", tz="UTC"),
    )
    assert frame["observation_id"].tolist() == ["obs-available"]
    schema = M1FeatureSchema.from_column_registry(published_bundle.column_registry)
    node = build_snapshot_node(
        published_bundle,
        "ep-1",
        pd.Timestamp("2026-01-01 10:40", tz="UTC"),
        schema,
    )
    encoded = dict(zip(schema.final_feature_order, node.feature_vector))
    assert encoded["wind_speed"] == 10.0
    assert encoded["visibility"] == 0.0
    assert encoded["mask__visibility"] == 0.0
    assert node.evidence_status["visibility"] == "MISSING_EVIDENCE_AUDIT"
    assert node.source_observation_ids == ("obs-available",)
    assert node.information_cutoff <= node.query_time


def test_membership_many_to_many_join_is_episode_scoped(published_bundle) -> None:
    first = available_observations(
        published_bundle.observations,
        published_bundle.observation_membership,
        "ep-1",
        "2026-01-01T10:40:00Z",
    )
    second = available_observations(
        published_bundle.observations,
        published_bundle.observation_membership,
        "ep-2",
        "2026-01-01T10:40:00Z",
    )
    assert first["observation_id"].tolist() == second["observation_id"].tolist()
    assert len(first) == 1
