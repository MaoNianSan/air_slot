import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from model.PRE.episode.containment import evaluate_episode_containment
from model.PRE.streaming.containment import _iter_data2_episode_pairs


UTC = timezone.utc


def episode(start: datetime, end: datetime):
    return SimpleNamespace(
        episode_id="episode",
        predecessor_flight_id="P",
        successor_flight_id="S",
        episode_start_time=start,
        episode_end_time=end,
    )


def test_same_split_cross_month_episode_allowed():
    result = evaluate_episode_containment(
        episode(
            datetime(2019, 8, 31, 23, 55, tzinfo=UTC),
            datetime(2019, 9, 1, 0, 10, tzinfo=UTC),
        ),
        predecessor_service_date="2019-08-31",
        successor_service_date="2019-09-01",
    )
    assert result.allowed
    assert result.split == "development"


def test_train_to_calibration_episode_rejected():
    result = evaluate_episode_containment(
        episode(datetime(2019, 6, 30, 23, 55, tzinfo=UTC), datetime(2019, 7, 1, 0, 10, tzinfo=UTC)),
        predecessor_service_date="2019-06-30",
        successor_service_date="2019-07-01",
    )
    assert not result.allowed
    assert result.reason_code == "CROSS_V5_SPLIT_EXCLUDED"
    assert "TRAIN_TO_CALIBRATION" in result.transitions


def test_calibration_to_development_episode_rejected():
    result = evaluate_episode_containment(
        episode(datetime(2019, 7, 31, 23, 55, tzinfo=UTC), datetime(2019, 8, 1, 0, 10, tzinfo=UTC)),
        predecessor_service_date="2019-07-31",
        successor_service_date="2019-08-01",
    )
    assert not result.allowed
    assert "CALIBRATION_TO_DEVELOPMENT" in result.transitions


def test_development_to_final_test_episode_rejected_without_final_test_read():
    result = evaluate_episode_containment(
        episode(datetime(2019, 9, 30, 23, 55, tzinfo=UTC), datetime(2019, 10, 1, 0, 10, tzinfo=UTC)),
        predecessor_service_date="2019-09-30",
        successor_service_date="2019-10-01",
    )
    assert not result.allowed
    assert "DEVELOPMENT_TO_FINAL_TEST" in result.transitions


def test_all_decision_nodes_within_episode_split():
    result = evaluate_episode_containment(
        episode(datetime(2019, 8, 31, 23, 55, tzinfo=UTC), datetime(2019, 9, 1, 0, 10, tzinfo=UTC)),
        predecessor_service_date="2019-08-31",
        successor_service_date="2019-09-01",
    )
    assert result.support_splits == ("development",)
    assert result.transitions == ()


def test_historical_h_cohort_split_containment():
    audit = _split_audit()
    assert audit["historical_h_selection_episodes_total"] == 320
    assert audit["historical_h_selection_cross_split_episodes"] == 3
    assert len(audit["historical_cross_split_episodes"]) == 3


def test_historical_w_cohort_split_containment():
    audit = _split_audit()
    assert audit["historical_w_selection_episodes_total"] == 320
    assert audit["historical_w_selection_cross_split_episodes"] == 3
    assert len(audit["historical_cross_split_episodes"]) == 3


def _assert_h_w_artifact_sample_splits_are_not_final_test():
    path = Path("artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE.npz")
    if not path.is_file():
        return
    with np.load(path, allow_pickle=False) as arrays:
        splits = set(str(value) for value in arrays["sample_splits"])
    assert "test" not in splits


def _split_audit():
    path = Path(
        "artifacts/diagnostics/v5_development_freeze/PRE_SPLIT_CONTAINMENT_AUDIT.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_development_delta_manifest_matches_exact_boundary_removals():
    base = Path("artifacts/diagnostics/v5_development_freeze")
    audit = _split_audit()
    manifest = json.loads(
        (base / "PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json").read_text(encoding="utf-8")
    )
    assert manifest["new_pre_eligible_episodes"] == (
        manifest["old_pre_eligible_episodes"]
        - audit["DEVELOPMENT_CROSS_SPLIT_EPISODES"]
    )
    assert manifest["new_pre_eligible_nodes"] == (
        manifest["old_pre_eligible_nodes"]
        - audit["removed_nodes_by_pool"]["development"]
    )
    assert manifest["final_test_access_count"] == 0


def test_boundary_audit_matches_builder_inverted_schedule_exclusion():
    predecessor = {
        "dataset_instance_id": "data2_2019",
        "aircraft_id_namespace": "REGISTRATION",
        "aircraft_id": "N1",
        "flight_id": "P",
        "origin_airport_id": "A",
        "destination_airport_id": "B",
        "event_start_time": datetime(2019, 6, 30, 20, tzinfo=UTC),
        "event_end_time": datetime(2019, 7, 1, 2, tzinfo=UTC),
        "actual_departure_utc": datetime(2019, 6, 30, 20, tzinfo=UTC),
        "actual_arrival_utc": datetime(2019, 6, 30, 22, tzinfo=UTC),
        "service_date": "2019-06-30",
    }
    successor = {
        **predecessor,
        "flight_id": "S",
        "origin_airport_id": "B",
        "destination_airport_id": "C",
        "event_start_time": datetime(2019, 7, 1, 1, tzinfo=UTC),
        "event_end_time": datetime(2019, 7, 1, 4, tzinfo=UTC),
        "actual_departure_utc": datetime(2019, 7, 1, 1, tzinfo=UTC),
        "actual_arrival_utc": datetime(2019, 7, 1, 3, tzinfo=UTC),
    }
    assert list(_iter_data2_episode_pairs([predecessor, successor])) == []
