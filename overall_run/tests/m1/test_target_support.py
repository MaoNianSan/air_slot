from __future__ import annotations

from dataclasses import replace

from overall_run.src.m1.adapter import M1FeatureSchema, build_snapshot_node
from overall_run.src.m1.adapter.target_builder import build_target_contracts, target_values
from overall_run.src.m1.contracts import SupportedOperationalValue


def test_target_support_and_preserved_event_evidence(published_bundle) -> None:
    schema = M1FeatureSchema.from_column_registry(published_bundle.column_registry)
    node = build_snapshot_node(
        published_bundle, "ep-1", "2026-01-01T12:00:00Z", schema
    )
    episode = published_bundle.episodes.iloc[0]
    contracts = build_target_contracts(
        episode,
        published_bundle.events,
        node.operational_references,
    )
    assert set(contracts) == {"R_IB", "R_OB", "T_TX"}
    assert all(contract.active for contract in contracts.values())
    assert contracts["R_OB"].m1_support_level == "OFFICIAL_OPERATIONAL"
    assert "event_time" not in contracts["R_OB"].event_details["AIBT_MINUS"]
    values = target_values(
        episode,
        published_bundle.events,
        "2026-01-01T10:00:00Z",
        node.operational_references,
    )
    assert values == {"R_IB": 30.0, "R_OB": 10.0, "T_TX": 20.0}


def test_missing_schedule_reference_deactivates_target(published_bundle) -> None:
    schema = M1FeatureSchema.from_column_registry(published_bundle.column_registry)
    node = build_snapshot_node(
        published_bundle, "ep-1", "2026-01-01T12:00:00Z", schema
    )
    missing = SupportedOperationalValue(
        None, False, "UNSUPPORTED", None, None, None, None, "SCHEDULE_FIELD_MISSING"
    )
    references = replace(node.operational_references, successor_sobt=missing)
    contract = build_target_contracts(
        published_bundle.episodes.iloc[0],
        published_bundle.events,
        references,
    )["R_OB"]
    assert contract.active is False
    assert contract.m1_support_level == "UNSUPPORTED"
