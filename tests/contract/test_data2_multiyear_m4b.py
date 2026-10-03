"""M4b contract tests: per-year replication of the 2019 PRE preprocessing flow.

All tests are synthetic/fixture-based and pass without local raw data. The
real six-year runs and the 2019 reproduction gate live in
data2/scripts/run_multiyear_pre.py.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from model.common.enums import SupportState
from model.PRE.cohort import (
    CALIBRATION_END,
    DEVELOPMENT_END,
    MULTIYEAR_RULE_VERSION,
    RULE_ID,
    RULE_VERSION,
    TRAIN_END,
    split_for_date,
    split_for_date_multiyear,
)
from model.PRE.transform import current_transformation_registry

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------ split rule --

def test_both_split_rule_versions_are_registered_and_frozen():
    registry = current_transformation_registry()
    legacy = registry.get(RULE_ID, RULE_VERSION)
    multiyear = registry.get(RULE_ID, MULTIYEAR_RULE_VERSION)
    assert legacy.version == "1.0.0"
    assert multiyear.version == "2.0.0"
    from model.PRE.transform.contracts import TransformationStatus
    assert legacy.status is TransformationStatus.FROZEN
    assert multiyear.status is TransformationStatus.FROZEN
    # the legacy rule text must remain byte-identical
    assert "train<=2019-06-30" in legacy.formula_or_algorithm
    assert "let Y = year(service_date)" in multiyear.formula_or_algorithm


def test_legacy_split_is_unchanged():
    assert TRAIN_END == date(2019, 6, 30)
    assert CALIBRATION_END == date(2019, 7, 31)
    assert DEVELOPMENT_END == date(2019, 9, 30)
    assert split_for_date(date(2019, 6, 30)) == "train"
    assert split_for_date(date(2019, 7, 1)) == "calibration"
    assert split_for_date(date(2019, 8, 1)) == "development"
    assert split_for_date(date(2019, 10, 1)) == "test"
    # legacy still swallows every non-2019 date into test
    assert split_for_date(date(2020, 3, 1)) == "test"
    assert split_for_date(date(2022, 8, 15)) == "test"


@pytest.mark.parametrize("year", (2017, 2018, 2019, 2020, 2021, 2022))
def test_multiyear_split_repeats_the_within_year_month_window(year):
    assert split_for_date_multiyear(date(year, 1, 1)) == "train"
    assert split_for_date_multiyear(date(year, 6, 30)) == "train"
    assert split_for_date_multiyear(date(year, 7, 1)) == "calibration"
    assert split_for_date_multiyear(date(year, 7, 31)) == "calibration"
    assert split_for_date_multiyear(date(year, 8, 1)) == "development"
    assert split_for_date_multiyear(date(year, 9, 30)) == "development"
    assert split_for_date_multiyear(date(year, 10, 1)) == "test"
    assert split_for_date_multiyear(date(year, 12, 31)) == "test"


def test_multiyear_split_matches_legacy_exactly_for_2019():
    for month in range(1, 13):
        for day in (1, 15, 28):
            stamp = date(2019, month, day)
            assert split_for_date_multiyear(stamp) == split_for_date(stamp)


# --------------------------------------------------- year-parameterized IO --

def test_ontime_paths_defaults_to_2019_and_honours_year(tmp_path):
    from model.PRE.streaming.data2 import ontime_paths
    root = tmp_path
    for year in (2019, 2020):
        for month in (1, 8):
            month_dir = (root / "data2" / "raw" / "bts" / "ontime" /
                         str(year) / f"month={month:02d}")
            month_dir.mkdir(parents=True)
            (month_dir / "f.csv").write_text("x\n", "utf-8")
    legacy = ontime_paths(root, months=(1, 8))
    assert legacy and all("2019" in str(path) for path in legacy)
    multi = ontime_paths(root, months=(1, 8), year=2020)
    assert multi and all("2020" in str(path) for path in multi)
    # create a Q4 partition so the final-test month guard has a path to see
    q4 = (root / "data2" / "raw" / "bts" / "ontime" / "2020" / "month=10")
    q4.mkdir(parents=True)
    (q4 / "f.csv").write_text("x\n", "utf-8")
    with pytest.raises(RuntimeError, match="FINAL_TEST_ONTIME_PATH_SELECTED"):
        ontime_paths(root, months=(10, 11, 12), year=2020)
    allowed = ontime_paths(root, months=(10,), year=2020, allow_final_test=True)
    assert allowed and "month=10" in str(allowed[0])


def test_source_hashes_honour_year(tmp_path):
    from model.PRE.streaming.development import source_hashes
    root = tmp_path
    for month in (7, 8, 9):
        month_dir = (root / "data2" / "raw" / "bts" / "ontime" / "2020" /
                     f"month={month:02d}")
        month_dir.mkdir(parents=True)
        (month_dir / "f.csv").write_text("x\n", "utf-8")
    weather = root / "data2" / "raw" / "weather" / "noaa" / "2020"
    weather.mkdir(parents=True)
    (weather / "s.csv").write_text("x\n", "utf-8")
    refs = root / "data2" / "refs"
    refs.mkdir(parents=True)
    (refs / "weather_station_map.csv").write_text("x\n", "utf-8")
    (refs / "us_airport_timezones.csv").write_text("x\n", "utf-8")
    hashes = source_hashes(root, year=2020)
    assert any("2020" in key for key in hashes), sorted(hashes)


def test_fast_split_default_matches_legacy_and_follows_resolver():
    from model.PRE.streaming.containment import _fast_split
    assert _fast_split(date(2019, 6, 30)) == "train"
    assert _fast_split(date(2019, 10, 1)) == "test"
    assert _fast_split(date(2020, 3, 1)) == "test"          # legacy collapse
    assert _fast_split(date(2020, 3, 1), year=2020) == "train"
    assert _fast_split(date(2020, 3, 1),
                       split_resolver=split_for_date_multiyear) == "train"


def test_containment_resolver_is_honoured_for_cross_year_episodes():
    from model.PRE.episode.containment import evaluate_episode_containment
    from model.PRE.contracts.pre_state import EpisodeRecord

    episode = EpisodeRecord(
        episode_id="e1",
        dataset_instance_id="data2_2017_2022",
        predecessor_flight_id="p1",
        successor_flight_id="s1",
        aircraft_id="N1",
        aircraft_id_namespace="REGISTRATION",
        connection_airport_id="ATL",
        episode_start_time=datetime(2020, 8, 15, 20, 0, tzinfo=timezone.utc),
        episode_end_time=datetime(2020, 8, 16, 1, 0, tzinfo=timezone.utc),
        chain_rule_id="SAME_AIRCRAFT_AIRPORT_GAP",
        chain_rule_version="1.0.0",
        chain_rule_parameters=("max_gap_minutes=360",),
        relation_type="SAME_AIRCRAFT_PREDECESSOR_SUCCESSOR",
        join_keys=("dataset_instance_id", "aircraft_id"),
        ordering_rule="ORDER_BY(event_start_time,flight_id)",
        continuity_rule="AIRPORT_CONTINUITY_AND_POSITIVE_BOUNDED_GAP",
        source_record_ids=("p1", "s1"),
        construction_provenance=("p1", "s1", "SAME_AIRCRAFT_AIRPORT_GAP@1.0.0"),
        lineage_support=SupportState.SUPPORTED,
        formal_eligible=True,
    )
    # the episode spans a within-year split boundary -> excluded under @2.0.0
    result = evaluate_episode_containment(
        episode,
        predecessor_service_date=date(2020, 6, 30),
        successor_service_date=date(2020, 7, 1),
        split_resolver=split_for_date_multiyear,
    )
    assert result.allowed is False
    assert result.reason_code == "CROSS_V5_SPLIT_EXCLUDED"
    # both endpoints in the same within-year window -> allowed
    ok = evaluate_episode_containment(
        episode,
        predecessor_service_date=date(2020, 8, 15),
        successor_service_date=date(2020, 8, 16),
        split_resolver=split_for_date_multiyear,
    )
    assert ok.allowed is True
    assert ok.split == "development"


# ------------------------------------------------------------ support map --

def test_target_support_falls_back_for_the_multiyear_instance():
    from model.PRE.feature_registry.loader import load_registry_bundle
    from model.PRE.pipeline import _target_support
    bundle = load_registry_bundle(ROOT / "registries")
    legacy = _target_support("data2_2019", bundle)
    multi = _target_support("data2_2017_2022", bundle)
    assert [t.model_dump() for t in multi] == [t.model_dump() for t in legacy]
    with pytest.raises(KeyError):
        _target_support("data2_2016", bundle)


def test_repository_registries_still_validate():
    from model.PRE.feature_registry.loader import load_registry_bundle
    bundle = load_registry_bundle(ROOT / "registries")
    assert bundle.manifest.combined_sha256.startswith("sha256:")

# ------------------------------------- 2019 input identity (M4b gate proof) --

def test_2019_parameterized_inputs_are_value_identical_to_legacy():
    """The M4b 2019 reproduction gate asserts the frozen cohort pool sizes and
    the content-addressed preparation state key. This test proves the stronger
    structural fact: every parameterized input the flow passes for year=2019 is
    value-identical to what the legacy path passes, so the legacy output is
    reproduced exactly rather than coincidentally."""
    from model.PRE.streaming import development as dev
    from model.PRE.streaming.data2 import ontime_paths, preparation_state_key

    root = Path(".").resolve()
    import os
    if not (root / "data2" / "raw" / "bts" / "ontime" / "2019").is_dir():
        import pytest
        pytest.skip("local 2019 raw not available")

    # partition selection
    assert ontime_paths(root, (7, 8, 9)) == ontime_paths(root, (7, 8, 9), year=2019)
    assert ontime_paths(root, range(1, 10)) == ontime_paths(
        root, range(1, 10), year=2019)
    # development window + final-test boundary
    assert date(2019, 8, 1) == dev.DEVELOPMENT_START
    assert date(2019, 9, 30) == dev.DEVELOPMENT_END
    assert date(2019, 10, 1) == dev.FINAL_TEST_START
    # source identity (the state key / run key basis)
    assert dev.source_hashes(root) == dev.source_hashes(root, year=2019)
    counts = {"train": 128, "calibration": 64, "development": 128, "test": 0}
    assert preparation_state_key(root, ontime_paths(root, range(1, 10)),
                                 counts, 20260813) == preparation_state_key(
        root, ontime_paths(root, range(1, 10), year=2019), counts, 20260813)
    # split resolution over the whole year
    for month in range(1, 13):
        for day in (1, 15, 28):
            stamp = date(2019, month, day)
            assert split_for_date_multiyear(stamp) == split_for_date(stamp)
    # target support for the instance equals the legacy support
    from model.PRE.feature_registry.loader import load_registry_bundle
    from model.PRE.pipeline import _target_support
    bundle = load_registry_bundle(ROOT / "registries")
    assert [t.model_dump() for t in _target_support("data2_2017_2022", bundle)]         == [t.model_dump() for t in _target_support("data2_2019", bundle)]
