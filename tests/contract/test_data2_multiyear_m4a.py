"""M4a contract tests for the multi-year Data2 instance.

Every test here is synthetic/fixture-based and passes without any local raw
data. The real-data production-semantic equivalence audit (>=1000 episodes
per year, boundary enrichment) lives in
data2/scripts/cohort_audit_data2_multiyear.py ::
production_semantic_equivalence_audit and gates the PRE-split cohort totals.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from model.PRE.adapters.base import AdapterDescription
from model.PRE.adapters.registry import (
    MULTIYEAR_ALLOWED_YEARS,
    RawReadRequest,
    SourceAdapterDefinition,
)

ROOT = Path(__file__).resolve().parents[2]


def _load_audit_module():
    script = ROOT / "data2" / "scripts" / "cohort_audit_data2_multiyear.py"
    spec = importlib.util.spec_from_file_location(
        "cohort_audit_data2_multiyear", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(tmp_path, instance, year=None):
    return RawReadRequest(
        dataset_instance_id=instance,
        source_family="bts_ontime",
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "out",
        year=year,
    )


def _definition() -> SourceAdapterDefinition:
    return SourceAdapterDefinition(
        adapter_id="D2-ONTIME",
        version="1.1.0",
        dataset_instance_id="data2_2019",
        source_family="bts_ontime",
        relative_globs=["raw/bts/ontime/{year}/month=*/*.csv"],
        format="csv",
        canonical_object="FlightRecord",
        canonical_objects=["FlightRecord", "OperationalEventRecord"],
        required_columns=["FlightDate"],
        projected_columns=["FlightDate"],
        rule_ids=["D2-BTS-SCHEDULE"],
        decision_time_role="EPISODE_CONSTRUCTION",
        availability_basis="SCHEDULE_REFERENCE_ASSUMPTION",
    )


# 1 - legacy backward compatibility ------------------------------------------------


def test_legacy_data2_2019_request_keeps_yearless_wildcard(tmp_path):
    request = _request(tmp_path, "data2_2019", year=None)
    assert request.year is None


def test_legacy_adapter_defaults_to_data2_2019():
    from model.PRE.adapters.data2 import Data2Adapter
    assert Data2Adapter().describe().dataset_instance_id == "data2_2019"
    assert Data2Adapter().describe().dataset_instance_id != "data2_2017_2022"


def test_multiyear_identity_is_accepted_everywhere():
    description = AdapterDescription(
        dataset_instance_id="data2_2017_2022",
        source_families=("bts_ontime",))
    assert description.dataset_instance_id == "data2_2017_2022"
    with pytest.raises(ValidationError):
        AdapterDescription(dataset_instance_id="data2_2019+data2_2017_2022",
                           source_families=("bts_ontime",))


# 2/3/4 - explicit-year gate --------------------------------------------------------


def test_multiyear_year_none_fails_closed_with_required_code(tmp_path):
    with pytest.raises(ValidationError) as error:
        _request(tmp_path, "data2_2017_2022", year=None)
    assert "MULTIYEAR_YEAR_REQUIRED" in str(error.value)


@pytest.mark.parametrize("year", MULTIYEAR_ALLOWED_YEARS)
def test_multiyear_accepts_exactly_the_six_allowed_years(tmp_path, year):
    request = _request(tmp_path, "data2_2017_2022", year=year)
    assert request.year == year


@pytest.mark.parametrize("year", (2016, 2023, 2015, 2024))
def test_multiyear_rejects_out_of_range_years(tmp_path, year):
    with pytest.raises(ValidationError) as error:
        _request(tmp_path, "data2_2017_2022", year=year)
    assert "MULTIYEAR_YEAR_NOT_ALLOWED" in str(error.value)


# 5 - no implicit wildcard pooling --------------------------------------------------


def test_multiyear_read_globs_only_the_requested_year(tmp_path):
    from model.PRE.adapters.readers import source_files
    # production layout: raw_root=data2 with globs beginning "raw/..."
    data2_root = tmp_path / "data2root"
    for year in (2019, 2020):
        month_dir = (data2_root / "raw" / "bts" / "ontime" / str(year)
                     / "month=01")
        month_dir.mkdir(parents=True)
        (month_dir / f"file_{year}.csv").write_text("FlightDate\n", "utf-8")
    request = RawReadRequest(
        dataset_instance_id="data2_2017_2022",
        source_family="bts_ontime",
        raw_root=data2_root,
        output_root=tmp_path / "outside",
        year=2020,
    )
    files = source_files(request, _definition())
    assert [path.name for path in files] == ["file_2020.csv"]


def test_wildcard_pooled_multiyear_request_cannot_be_constructed(tmp_path):
    with pytest.raises(ValidationError):
        RawReadRequest(
            dataset_instance_id="data2_2017_2022",
            source_family="bts_ontime",
            raw_root=tmp_path,
            output_root=tmp_path / "out",
            year=None,
        )


# 6/7 - silent 2019 filters: parameterized, legacy default unchanged ----------------


def test_weather_index_stamp_year_branch(tmp_path, monkeypatch):
    import model.PRE.streaming.data2 as streaming

    refs = tmp_path / "refs"
    refs.mkdir(parents=True)
    (refs / "weather_station_map.csv").write_text(
        "airport,station,distance_km,weather_source_type,station_lat,"
        "station_lon\nATL,99999913874,1.0,DIRECT_STATION,33.6,-84.4\n",
        "utf-8")
    for year in (2019, 2020):
        year_dir = tmp_path / "raw" / "weather" / "noaa" / str(year)
        year_dir.mkdir(parents=True)
        (year_dir / "99999913874.csv").write_text(
            f'STATION,DATE\n"99999913874","{year}-01-01T00:00:00"\n'
            f'"99999913874","{year}-06-01T00:00:00"\n',
            "utf-8")

    class _Obs:
        def __init__(self, stamp):
            self.event_time = datetime.fromisoformat(stamp).replace(
                tzinfo=timezone.utc)
            self.availability_time = self.event_time + timedelta(minutes=5)
            self.airport_id = "ATL"

    def _stub(row, *, station_map, replay_lag_minutes):
        assert replay_lag_minutes == 5
        return _Obs(str(row["DATE"]))

    monkeypatch.setattr(streaming, "canonicalize_isd_row", _stub)
    legacy_index, legacy_stats = streaming.weather_index(tmp_path, 5)
    assert legacy_stats["accepted_train_calibration_development_observations"] == 2
    assert set(legacy_index) == {"ATL"}
    multi_index, multi_stats = streaming.weather_index(
        tmp_path, 5, stamp_year="2020", end_exclusive=__import__(
            "datetime").date(2021, 1, 1))
    assert multi_stats["accepted_train_calibration_development_observations"] == 2
    assert set(multi_index) == {"ATL"}
    mixed_index, _ = streaming.weather_index(
        tmp_path, 5, stamp_year="2020", end_exclusive=date(2021, 1, 1))
    for packed in mixed_index.values():
        _times, observations = packed
        assert all(observation.event_time.year == 2020
                   for observation in observations)


def test_weather_index_and_stats_instance_year_plumbing(tmp_path, monkeypatch):
    import model.PRE.streaming.data2 as streaming

    captured = {}

    def _fake_iter(request, *, replay_lag_minutes=None):
        captured["instance"] = request.dataset_instance_id
        captured["year"] = request.year
        return iter(())

    monkeypatch.setattr(streaming.Data2Adapter, "iter_canonical",
                        staticmethod(_fake_iter))
    data2_root = tmp_path / "data2root"
    data2_root.mkdir()
    output = tmp_path / "outside"
    streaming.weather_index_and_stats(
        data2_root, output, 5, period=None,
        instance_id="data2_2017_2022", year=2020)
    assert captured == {"instance": "data2_2017_2022", "year": 2020}
    streaming.weather_index_and_stats(data2_root, output, 5, period=None)
    assert captured == {"instance": "data2_2019", "year": 2019}


# 8 - CLI dispatch ------------------------------------------------------------------


def test_cli_dispatch_is_instance_aware():
    from model.PRE.cli import _adapter
    from model.PRE.adapters.data2 import Data2Adapter
    legacy = _adapter("data2_2019")
    assert isinstance(legacy, Data2Adapter)
    assert legacy._dataset_instance_id == "data2_2019"
    multi = _adapter("data2_2017_2022")
    assert isinstance(multi, Data2Adapter)
    assert type(multi) is type(legacy)
    assert multi._dataset_instance_id == "data2_2017_2022"
    from model.common.errors import ContractError
    with pytest.raises(ContractError):
        _adapter("data2_2017")
    with pytest.raises(ContractError):
        _adapter("data2_2018")


# 9 - raw roots identical -----------------------------------------------------------


def test_raw_roots_are_identical_for_both_instances():
    from model.common.paths import data_root, project_path
    from model.PRE.instances import DATA2_2017_2022, LEGACY_DATA2_2019
    assert data_root("data2_2019") == project_path("data2")
    assert LEGACY_DATA2_2019.raw_root_name == "data2"
    assert DATA2_2017_2022.raw_root_name == "data2"
    assert LEGACY_DATA2_2019.raw_root_name == DATA2_2017_2022.raw_root_name


# 10 - no split assignment for the multi-year instance ------------------------------


def test_multiyear_instance_defines_no_split_and_audit_chain_is_clean():
    from model.PRE.instances import DATA2_2017_2022
    assert DATA2_2017_2022.split_rule_id is None
    assert DATA2_2017_2022.fit_window is None
    module = _load_audit_module()
    audit = module.static_reuse_audit()
    assert audit["status"] == "PASS", audit["violations"]
    assert audit["clean_functions"], "audit reuse list is empty"


# production-semantic equivalence on synthetic boundary cases -----------------------


def test_optimized_masks_match_production_functions_on_synthetic_boundaries():
    module = _load_audit_module()
    start = datetime(2020, 6, 1, 10, 7, tzinfo=timezone.utc)
    end = start + timedelta(minutes=73)
    cases = [
        # (pred_arrival, successor_departure, wheels_off) with boundary hits:
        # event exactly on a grid point, exactly at cutoff, just after cutoff
        (start + timedelta(minutes=13), start + timedelta(minutes=40),
         start + timedelta(minutes=40)),          # wheels exactly on grid
        (start + timedelta(minutes=15), start + timedelta(minutes=45),
         start + timedelta(minutes=45, seconds=1)),  # just after a grid point
        (start + timedelta(minutes=1), start + timedelta(minutes=2),
         start + timedelta(minutes=72, seconds=59)),
        (start, start, start + timedelta(minutes=30)),  # all boundaries at t0
        (start + timedelta(minutes=80), start + timedelta(minutes=81),
         start + timedelta(minutes=82)),          # thresholds beyond the grid
        (start + timedelta(minutes=10), start + timedelta(minutes=20), None),
    ]
    for pred_arrival, dep, wheels in cases:
        episode = type("Episode", (), {
            "episode_start_time": start, "episode_end_time": end})()
        optimized = module.label_support_counts(start, end, pred_arrival,
                                                dep, wheels)
        grid, times = [], start
        while times <= end:
            grid.append(times)
            times += timedelta(minutes=5)
        for index, decision_time in enumerate(grid):
            stage = module.stage_at(
                decision_time,
                predecessor_in_block=pred_arrival,
                successor_off_block=dep,
                successor_takeoff=wheels)
            # count_at_or_after is a TAIL count: nodes at-or-after the
            # threshold occupy the last `count` grid positions.
            assert (stage.value != "PRE_IB") == (
                index >= len(grid) - optimized["R_IB"])
            assert (stage.value in ("POST_OB_PRE_TO", "COMPLETED")) == (
                index >= len(grid) - optimized["D_OB"])
            assert (stage.value == "COMPLETED") == (
                index >= len(grid) - optimized["D_TX"])
            joint = all(threshold is not None and decision_time >= threshold
                        for threshold in (pred_arrival, dep, wheels))
            assert joint == (
                index >= len(grid) - optimized["JOINT_RIB_DOB_DTX"])
            nodes = module.episode_node_count(
                episode_start_time=start, episode_end_time=end)
            assert len(grid) == nodes


def test_weather_mask_matches_production_latest_weather_semantics():
    module = _load_audit_module()
    import model.PRE.streaming.data2 as streaming
    start = datetime(2020, 6, 1, 10, 7, tzinfo=timezone.utc)
    end = start + timedelta(minutes=60)
    availability = (start + timedelta(minutes=2)
                    + np.arange(0, 5) * timedelta(minutes=17))
    availability = np.array([int(t.timestamp()) for t in
                             (availability - timedelta(minutes=5))],
                            dtype=np.int64)
    times = [datetime.fromtimestamp(int(s), timezone.utc)
             for s in availability]

    class _Obs:
        __slots__ = ("availability_time",)

        def __init__(self, value):
            self.availability_time = value

    packed = {"ATL": (tuple(times), tuple(_Obs(t) for t in times))}
    grid, cursor = [], start
    while cursor <= end:
        grid.append(cursor)
        cursor += timedelta(minutes=5)
    optimized_total = module.weather_support_count(start, end, availability)
    production_total = 0
    for decision_time in grid:
        observation = streaming.latest_weather(packed, "ATL", decision_time,
                                               60)
        stamp_s = int(decision_time.timestamp())
        idx = int(np.searchsorted(availability, stamp_s, side="right")) - 1
        optimized_flag = bool(
            idx >= 0 and (stamp_s - int(availability[idx])) <= 60 * 60)
        assert (observation is not None) == optimized_flag
        production_total += 1 if observation is not None else 0
    assert optimized_total == production_total


def test_missing_weather_yields_zero_support():
    module = _load_audit_module()
    start = datetime(2020, 6, 1, 10, 7, tzinfo=timezone.utc)
    assert module.weather_support_count(
        start, start + timedelta(minutes=30), None) == 0
    assert module.weather_support_count(
        start, start + timedelta(minutes=30), np.empty(0, dtype=np.int64)) == 0


import numpy as np  # noqa: E402  (used by the synthetic weather tests)
