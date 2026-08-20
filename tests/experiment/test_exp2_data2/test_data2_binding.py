from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from exp.exp2.execution.data2_selector import (
    Data2CompatibilityChecker,
    Data2DecisionRecord,
    Data2EpisodeRecord,
    Data2EpisodeRegistry,
    Data2EpisodeSelector,
    Data2ScenarioConstructor,
    Data2SelectionStatus,
    M1ScenarioBinding,
    M2ConsequenceBinding,
)
from exp.exp2.execution.scientific_manifest import (
    ScientificManifestStatus,
    ScientificManifestValidator,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "configs" / "experiment" / "exp2_scientific_manifest.yaml"
PILOT_PATH = REPOSITORY_ROOT / "configs" / "experiment" / "exp2_data2_pilot.yaml"
UTC = timezone.utc


def _episode() -> Data2EpisodeRecord:
    decision_time = datetime(2019, 1, 15, 12, tzinfo=UTC)
    return Data2EpisodeRecord(
        episode_id="data2-episode-001",
        split_id="development",
        scenario_lineage=("pre:episode-001", "m1:scenario-seed-001"),
        decision_records=(
            Data2DecisionRecord(
                decision_node_id="node-001",
                decision_time=decision_time,
                information_cutoff=decision_time - timedelta(minutes=5),
                legal_record_ids=("weather:001", "schedule:001"),
                legal_record_availability_times=(
                    decision_time - timedelta(minutes=10),
                    decision_time - timedelta(minutes=5),
                ),
            ),
        ),
    )


def _registry() -> Data2EpisodeRegistry:
    return Data2EpisodeRegistry(
        dataset_version="DATA2-TEST-FREEZE-001",
        source_manifest_hash="sha256:" + "1" * 64,
        pre_schema_version="AIR_SLOT_PRE_STATE_V2",
        episodes=(_episode(),),
    )


def test_data2_manifest_and_pilot_config_are_loading_and_explicitly_blocked():
    manifest = ScientificManifestValidator().load(MANIFEST_PATH)
    result = ScientificManifestValidator().validate(manifest)
    pilot = yaml.safe_load(PILOT_PATH.read_text(encoding="utf-8"))

    assert manifest.dataset.dataset_id == "DATA2"
    assert manifest.dataset.source_dataset_id == "data2_2019"
    assert manifest.dataset.version == "DATA2_2019_DEVELOPMENT_AUG_SEP_V1"
    assert result.status is ScientificManifestStatus.BLOCKED_MISSING_ARTIFACT
    assert result.dataset_binding_valid is True
    assert result.lineage_valid is True
    assert "M1_ARTIFACT_REQUIRED" in result.reason_codes
    assert manifest.dataset.cohort_hash.startswith("sha256:")
    assert manifest.m3.artifact_id == "DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE_V1"
    assert manifest.m4.risk_policy_status.value == "FROZEN"
    assert pilot["dataset"]["dataset_id"] == "DATA2"
    assert pilot["dataset"]["maximum_episode_count"] == 5
    assert pilot["variants"] == {
        "exp2a": ["JOINT", "MARGINAL", "COLLAPSED"],
        "exp2b": ["COMPONENT", "CHANNEL", "SCALAR"],
    }
    assert pilot["scientific_run"] is False


def test_selector_preserves_requested_episode_order_lineage_and_timestamps():
    result = Data2EpisodeSelector().select(
        _registry(),
        episode_ids=("data2-episode-001",),
        expected_split="development",
    )

    assert result.status is Data2SelectionStatus.READY
    selected = result.selected_episodes[0]
    assert selected.episode_id == "data2-episode-001"
    assert selected.scenario_lineage == ("pre:episode-001", "m1:scenario-seed-001")
    assert selected.decision_node_ids == ("node-001",)
    assert selected.information_cutoffs[0] < selected.decision_timestamps[0]

    constructed = Data2ScenarioConstructor().construct(
        selected,
        decision_node_id="node-001",
        scenario_ids=(0, 1),
    )
    assert constructed.episode_id == selected.episode_id
    assert constructed.decision_time == selected.decision_timestamps[0]
    assert constructed.scenario_lineage == selected.scenario_lineage


def test_selector_rejects_unfrozen_or_missing_episode_request_without_fallback():
    result = Data2EpisodeSelector().select(
        _registry(),
        episode_ids=("not-in-frozen-registry",),
        expected_split="development",
    )

    assert result.status is Data2SelectionStatus.BLOCKED
    assert result.selected_episodes == ()
    assert result.reason_codes == (
        "DATA2_REQUESTED_EPISODE_NOT_IN_FROZEN_REGISTRY:not-in-frozen-registry",
    )


def test_selector_requires_the_frozen_data2_split():
    result = Data2EpisodeSelector().select(
        _registry(), episode_ids=("data2-episode-001",)
    )

    assert result.status is Data2SelectionStatus.BLOCKED
    assert result.selected_episodes == ()
    assert result.reason_codes == ("DATA2_FROZEN_SPLIT_REQUIRED",)


def test_cutoff_validation_rejects_future_information():
    decision_time = datetime(2019, 1, 15, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="DATA2_FUTURE_INFORMATION_LEAKAGE"):
        Data2DecisionRecord(
            decision_node_id="node-future",
            decision_time=decision_time,
            information_cutoff=decision_time,
            legal_record_ids=("future-weather",),
            legal_record_availability_times=(decision_time + timedelta(seconds=1),),
        )


def test_pre_m1_m2_compatibility_requires_identity_time_and_lineage_preservation():
    episode = _episode()
    node = episode.decision_records[0]
    m1 = M1ScenarioBinding(
        episode_id=episode.episode_id,
        decision_node_id=node.decision_node_id,
        decision_time=node.decision_time,
        information_cutoff=node.information_cutoff,
        scenario_lineage=episode.scenario_lineage,
        scenario_ids=(0, 1),
    )
    m2 = M2ConsequenceBinding(
        episode_id=episode.episode_id,
        decision_node_id=node.decision_node_id,
        scenario_ids=(0, 1),
        scenario_lineage=episode.scenario_lineage,
    )

    result = Data2CompatibilityChecker().validate(episode, node.decision_node_id, m1, m2)
    assert result.pre_compatible is True
    assert result.m1_compatible is True
    assert result.m2_compatible is True
    assert result.reason_codes == ("DATA2_PRE_M1_M2_COMPATIBLE",)

    incompatible = m2.model_copy(update={"scenario_ids": (1, 0)})
    result = Data2CompatibilityChecker().validate(
        episode, node.decision_node_id, m1, incompatible
    )
    assert result.m2_compatible is False
    assert "M2_SCENARIO_IDENTITY_NOT_PRESERVED" in result.reason_codes
