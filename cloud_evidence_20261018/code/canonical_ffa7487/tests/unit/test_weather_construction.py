from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from model.common.config import load_config_layers
from model.PRE.canonical.normalization import canonicalize_metar_row
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre
from model.common.enums import SupportState


UTC = timezone.utc
T0 = datetime(2019, 1, 1, 12, 0, tzinfo=UTC)


def metar_row(valid, **cloud):
    row = {"station": "LSZH", "valid": valid.isoformat(), "tmpf": "32", "dwpf": "23",
           "drct": "180", "sknt": "10", "gust": "M", "mslp": "M", "vsby": "10",
           "metar": "LSZH 010020Z 18010KT Q1013"}
    row.update(cloud)
    return row


def publish(records, cutoff):
    return publish_production_pre(ProductionPRERequest(episode_id="e", predecessor_id="p",
        successor_id="s", dataset_instance_id="data1_2019", decision_time=cutoff,
        information_cutoff=cutoff, records=tuple(records), config_hash="sha256:c",
        registry_hash="sha256:r"))


def test_weather_parameters_frozen_in_foundation_config():
    scientific = load_config_layers(Path("configs")).scientific
    max_age = scientific.parameters["weather_max_age_minutes"]
    encoding = scientific.parameters["cloud_encoding"]
    assert max_age.freeze_state.value == "FROZEN" and max_age.value == 60
    assert encoding.freeze_state.value == "FROZEN" and encoding.value == "both"


def test_ceiling_derived_as_min_base_over_bkn_ovc():
    row = metar_row(T0 - timedelta(minutes=5), skyc1="BKN", skyl1="12",
                    skyc2="OVC", skyl2="30", skyc3="FEW", skyl3="60")
    result = canonicalize_metar_row(row, replay_lag_minutes=0)
    assert result.ceiling_base_m == pytest.approx(12 * 100 * 0.3048)
    assert result.cloud_cover_codes == ("BKN", "OVC", "FEW")
    assert result.cloud_base_m == pytest.approx((365.76, 914.4, 1828.8))
    assert "CEILING_DERIVED_MIN_BKN_OVC" in result.quality_flags


def test_vertical_visibility_counts_as_ceiling_layer():
    row = metar_row(T0 - timedelta(minutes=5), skyc1="VV", skyl1="5")
    result = canonicalize_metar_row(row, replay_lag_minutes=0)
    assert result.ceiling_base_m == pytest.approx(5 * 100 * 0.3048)
    assert "CEILING_DERIVED_MIN_BKN_OVC" in result.quality_flags


def test_missing_base_on_ceiling_layer_is_masked_not_invented():
    row = metar_row(T0 - timedelta(minutes=5), skyc1="BKN", skyl1="M",
                    skyc2="OVC", skyl2="25")
    result = canonicalize_metar_row(row, replay_lag_minutes=0)
    assert result.ceiling_base_m is None
    assert "CEILING_BASE_MISSING_MASKED" in result.quality_flags
    assert result.cloud_cover_codes == ("BKN", "OVC")
    assert result.cloud_base_m == (None, 25 * 100 * 0.3048)


def test_no_ceiling_layer_is_unlimited_not_missing():
    row = metar_row(T0 - timedelta(minutes=5), skyc1="FEW", skyl1="10",
                    skyc2="SCT", skyl2="20")
    result = canonicalize_metar_row(row, replay_lag_minutes=0)
    assert result.ceiling_base_m is None
    assert "CEILING_UNLIMITED" in result.quality_flags
    assert "CEILING_BASE_MISSING_MASKED" not in result.quality_flags


def test_missing_cloud_elements_flagged_and_empty():
    row = metar_row(T0 - timedelta(minutes=5))
    result = canonicalize_metar_row(row, replay_lag_minutes=0)
    assert result.cloud_cover_codes == ()
    assert result.cloud_base_m == ()
    assert result.ceiling_base_m is None
    assert "CLOUD_LAYERS_MISSING" in result.quality_flags


def test_fresh_weather_within_max_age_is_selected():
    weather = canonicalize_metar_row(metar_row(T0 - timedelta(minutes=59)),
                                     replay_lag_minutes=0)
    state = publish((weather,), T0).pre_state
    value = state.current_state["current_weather"]
    assert value.support_state is SupportState.SUPPORTED
    assert value.value["ceiling_base_m"] is None
    assert value.value["temperature_c"] == 0


def test_boundary_exactly_max_age_is_still_legal():
    weather = canonicalize_metar_row(metar_row(T0 - timedelta(minutes=60)),
                                     replay_lag_minutes=0)
    state = publish((weather,), T0).pre_state
    assert state.current_state["current_weather"].support_state is SupportState.SUPPORTED


def test_stale_weather_abstains_with_explicit_reason():
    weather = canonicalize_metar_row(metar_row(T0 - timedelta(minutes=61)),
                                     replay_lag_minutes=0)
    state = publish((weather,), T0).pre_state
    value = state.current_state["current_weather"]
    assert value.support_state is SupportState.ABSTAIN
    assert value.value is None
    assert value.reason_code == "WEATHER_STALE_AT_CUTOFF"
    assert all(item.scientific_variable != "current_weather" for item in state.variable_lineage)


def test_latest_legal_weather_wins_within_window():
    older = canonicalize_metar_row(metar_row(T0 - timedelta(minutes=30)), replay_lag_minutes=0)
    newer = canonicalize_metar_row(metar_row(T0 - timedelta(minutes=5)), replay_lag_minutes=0)
    state = publish((older, newer), T0).pre_state
    lineage = next(item for item in state.variable_lineage
                   if item.scientific_variable == "current_weather")
    assert lineage.age_seconds == 5 * 60
    assert state.current_state["current_weather"].value["ceiling_base_m"] is None


def test_future_weather_never_published():
    future = canonicalize_metar_row(metar_row(T0 + timedelta(minutes=5)), replay_lag_minutes=0)
    state = publish((future,), T0).pre_state
    value = state.current_state["current_weather"]
    assert value.support_state is SupportState.ABSTAIN
    assert value.reason_code == "NO_LEGAL_RECORD_AT_DECISION_TIME"