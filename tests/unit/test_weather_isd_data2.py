import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.base import SourceValidationRequest
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.canonical.normalization import (
    _normalize_isd_station_id,
    canonicalize_isd_row,
)
from model.PRE.contracts.canonical import WeatherObservation
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.mapping import RegistryPREMapper
from model.PRE.adapters.registry import SourceAdapterRegistry
from model.common.errors import ContractError

UTC = timezone.utc

STATION_MAP = {"72206013889": "JAX", "72565003017": "DEN", "72259003927": "DFW"}


def isd_row(**overrides):
    row = {
        "STATION": "72206013889",
        "DATE": "2019-01-01T00:56:00",
        "REPORT_TYPE": "FM-15",
        "WND": "220,1,N,0015,1",
        "CIG": "22000,5,9,N",
        "VIS": "016093,5,N,5",
        "TMP": "+0200,5",
        "DEW": "+0183,5",
        "SLP": "10201,5",
        "REM": "MET09312/31/18 19:56:01 METAR KJAX 010056Z 22015KT 10SM FEW050 20/18 A3012 RMK AO2 SLP201 T02000183",
    }
    row.update(overrides)
    return row


def build(replay_lag=5, **overrides):
    return canonicalize_isd_row(isd_row(**overrides), station_map=STATION_MAP,
                                replay_lag_minutes=replay_lag)


def test_normalize_station_id_zero_pads_wban():
    assert _normalize_isd_station_id("7256503017") == "72565003017"
    assert _normalize_isd_station_id("7225903927") == "72259003927"
    assert _normalize_isd_station_id("7231203870") == "72312003870"
    assert _normalize_isd_station_id("7220703822") == "72207003822"
    assert _normalize_isd_station_id("9999993928") == "99999903928"
    assert _normalize_isd_station_id("13874") == "99999913874"
    assert _normalize_isd_station_id("72206013889") == "72206013889"


def test_core_fields_and_provenance():
    obs = build()
    assert isinstance(obs, WeatherObservation)
    assert obs.dataset_instance_id == "data2_2019"
    assert obs.airport_id == "JAX"
    assert obs.event_time == datetime(2019, 1, 1, 0, 56, tzinfo=UTC)
    assert obs.temperature_c == 20.0
    assert obs.dewpoint_c == 18.3
    assert obs.wind_direction_deg == 220.0
    assert obs.wind_speed_mps == 1.5
    assert obs.visibility_m == 16093.0
    assert obs.provenance_rule_id == "D2-NOAA-ISD"
    assert obs.decision_time_role == "INFERENCE_EVIDENCE"
    assert obs.availability_basis == "REPLAY_EVENT_TIME"
    assert obs.availability_time == obs.event_time + timedelta(minutes=5)
    assert obs.source_path is None  # set by the adapter layer


def test_qnh_from_metar_text_is_true_hpa():
    obs = build()
    # A3012 = 30.12 inHg -> 1020.0 hPa; the data1 code stores inHg*100 (3012)
    # mislabeled as hPa; data2 stores the true pressure value.
    assert obs.qnh_hpa == 1020.0
    assert obs.qnh_hpa != 3012
    assert "QNH_DERIVED_FROM_METAR" in obs.quality_flags
    no_qnh = build(REM="METAR KJAX 010056Z 00000KT 10SM FEW050 20/18 RMK")
    assert no_qnh.qnh_hpa is None
    assert "QNH_ABSENT" in no_qnh.quality_flags


def test_ceiling_from_isd_cig_field():
    obs = build(CIG="00457,5,9,N")
    assert obs.ceiling_base_m == 45.7
    assert "CEILING_FROM_ISD_CIG" in obs.quality_flags
    unlimited = build(CIG="22000,5,9,N")
    assert unlimited.ceiling_base_m is None
    assert "CEILING_UNLIMITED" in unlimited.quality_flags
    missing_cig = build(CIG="99999,9,9,N")
    assert missing_cig.ceiling_base_m is None
    assert "CEILING_MISSING" in missing_cig.quality_flags


def test_ceiling_falls_back_to_metar_text_when_cig_unlimited():
    obs = build(CIG="22000,5,9,N", REM="METAR KJAX 010056Z 22015KT 10SM BKN015 20/18 A3012")
    assert obs.ceiling_base_m == pytest.approx(457.2)
    assert "CEILING_FROM_METAR_TEXT" in obs.quality_flags


def test_cloud_layers_from_metar_text():
    obs = build(REM="METAR KJAX 010056Z 22015KT 10SM FEW050 SCT100 20/18 A3012")
    assert obs.cloud_cover_codes == ("FEW", "SCT")
    assert obs.cloud_base_m == (pytest.approx(1524.0), pytest.approx(3048.0))
    no_rem = build(REM="")
    assert no_rem.cloud_cover_codes == ()
    assert no_rem.cloud_base_m == ()
    assert "METAR_TEXT_ABSENT" in no_rem.quality_flags


def test_present_weather_tokens_from_metar_text():
    obs = build(REM="METAR KJAX 010056Z 22015KT 3SM -RA BR FEW050 20/18 A3012")
    assert obs.present_weather_codes == "-RA BR"
    assert "PRESENT_WEATHER_FROM_METAR_TEXT" in obs.quality_flags
    clear = build(REM="METAR KJAX 010056Z 22015KT 10SM FEW050 20/18 A3012")
    assert clear.present_weather_codes is None


def test_wind_calm_and_missing():
    calm = build(WND="999,9,C,0000,5")
    assert calm.wind_direction_deg is None
    assert calm.wind_speed_mps == 0.0
    missing_wnd = build(WND="990,1,N,9999,1")
    assert missing_wnd.wind_direction_deg is None
    assert missing_wnd.wind_speed_mps is None


def test_missing_temperature_is_none():
    obs = build(TMP="+9999,9")
    assert obs.temperature_c is None


def test_station_unmapped_rejected():
    with pytest.raises(ContractError, match="WEATHER_STATION_UNMAPPED"):
        canonicalize_isd_row(isd_row(STATION="00000000000"), station_map=STATION_MAP,
                             replay_lag_minutes=5)


def test_replay_lag_required():
    with pytest.raises(ContractError, match="REPLAY_LAG_NOT_FROZEN"):
        canonicalize_isd_row(isd_row(), station_map=STATION_MAP, replay_lag_minutes=None)


def test_missing_date_or_station_rejected():
    with pytest.raises(ContractError, match="WEATHER_ROW_MISSING:DATE_OR_STATION"):
        canonicalize_isd_row(isd_row(DATE=""), station_map=STATION_MAP, replay_lag_minutes=5)
    with pytest.raises(ContractError, match="WEATHER_ROW_MISSING:DATE_OR_STATION"):
        canonicalize_isd_row(isd_row(STATION=""), station_map=STATION_MAP, replay_lag_minutes=5)


def test_canonical_record_id_deterministic():
    first = build()
    second = build()
    assert first.canonical_record_id == second.canonical_record_id
    assert first.canonical_record_id.startswith("weather:")


def test_adapter_validates_noaa_isd_family():
    report = Data2Adapter().validate_source(SourceValidationRequest(source_family="noaa_isd"))
    assert report.status == "DECLARED"
    assert report.dataset_instance_id == "data2_2019"
    unsupported = Data2Adapter().validate_source(SourceValidationRequest(source_family="bogus"))
    assert unsupported.status == "UNSUPPORTED"


def test_adapter_iter_canonical_weather(tmp_path):
    raw_root = tmp_path / "raw"
    out_root = tmp_path / "out"
    (raw_root / "refs").mkdir(parents=True)
    (raw_root / "raw" / "weather" / "noaa" / "2019").mkdir(parents=True)
    (raw_root / "refs" / "weather_station_map.csv").write_text(
        "airport,station\nJAX,72206013889\n", encoding="utf-8")
    header = ["STATION", "DATE", "REPORT_TYPE", "WND", "CIG", "VIS", "TMP", "DEW", "SLP", "REM"]
    row = ["72206013889", "2019-01-01T00:56:00", "FM-15", "220,1,N,0015,1", "22000,5,9,N",
           "016093,5,N,5", "+0200,5", "+0183,5", "10201,5",
           "METAR KJAX 010056Z 22015KT 10SM FEW050 20/18 A3012"]
    with (raw_root / "raw" / "weather" / "noaa" / "2019" / "72206013889.csv").open(
            "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerow(row)
    request = RawReadRequest(dataset_instance_id="data2_2019", source_family="noaa_isd",
                             raw_root=raw_root, output_root=out_root, year=2019)
    records = list(Data2Adapter().iter_canonical(request, replay_lag_minutes=5))
    assert len(records) == 1
    obs = records[0]
    assert obs.airport_id == "JAX"
    assert obs.source_path is not None
    assert obs.source_fingerprint is not None
    with pytest.raises(ContractError, match="REPLAY_LAG_NOT_FROZEN"):
        list(Data2Adapter().iter_canonical(request))


def test_registry_weather_rules_and_data1_untouched():
    bundle = load_registry_bundle(Path("registries"))
    rule_ids = {r.rule_id for r in bundle.data_usage_rules}
    assert "D2-NOAA-ISD" in rule_ids
    assert "D1-OPENSKY-FLIGHT" in rule_ids
    d2 = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-NOAA-ISD")
    assert d2.freeze_state.value == "FROZEN"
    assert d2.dataset_id == "data2_2019"
    assert d2.logical_source == "noaa_isd"
    assert d2.evidence_class.value == "DIRECT"
    assert d2.decision_time_role.value == "INFERENCE_EVIDENCE"
    assert "D2-AIRPORT-REFERENCE" in d2.external_evidence_rule_ids
    # D2-9 alignment (2026-08-14, user-approved option A): D2-NOAA-ISD must
    # map to the current_weather scientific variable, mirroring D1-METAR.
    assert d2.canonical_variable == "current_weather"
    assert d2.pre_family == "current_state"

    profile = next(p for p in bundle.capability_profiles if p.dataset_instance_id == "data2_2019")
    weather = next(c for c in profile.capabilities if c.scientific_object == "weather")
    assert weather.freeze_state.value == "FROZEN"
    assert weather.max_evidence_class.value == "DIRECT"
    assert weather.source_families == ("noaa_isd",)
    assert weather.reason_code is None
    data1_profile = next(p for p in bundle.capability_profiles if p.dataset_instance_id == "data1_2019")
    assert all(c.scientific_object != "weather" for c in data1_profile.capabilities)
    assert data1_profile.cross_dataset_reference_overlay is False

    adapters = SourceAdapterRegistry.load(Path("registries") / "source_adapter_registry.yaml")
    d2_isd = adapters.get("data2_2019", "noaa_isd")
    assert d2_isd.adapter_id == "D2-ISD"
    assert d2_isd.rule_ids == ("D2-NOAA-ISD",)
    d1_metar = adapters.get("data1_2019", "iem_metar")
    assert d1_metar.adapter_id == "D1-METAR"


def test_isd_observation_maps_to_current_weather():
    bundle = load_registry_bundle(Path("registries"))
    mapped = RegistryPREMapper(bundle).map_record(build(replay_lag=0))
    assert mapped is not None
    assert mapped.scientific_variable == "current_weather"
    assert mapped.pre_family == "current_state"
    assert mapped.rule_id == "D2-NOAA-ISD"
    assert mapped.value.evidence_class.value == "DIRECT"
    assert mapped.value.support_state.value == "SUPPORTED"

def test_data2_weather_replay_lag_frozen_at_5_data1_unchanged():
    # D2-6 replay-lag new decision (2026-08-16, user approved): data2 weather
    # availability lag = 5 min via the data2-scoped FROZEN parameter;
    # data1 replay_lag_minutes stays 0 (shared foundation must not drift).
    cfg = yaml.safe_load(Path("configs/scientific/foundation.yaml").read_text(encoding="utf-8"))
    params = cfg["parameters"]
    assert params["data2_weather_replay_lag_minutes"]["value"] == 5
    assert params["data2_weather_replay_lag_minutes"]["freeze_state"] == "FROZEN"
    assert params["replay_lag_minutes"]["value"] == 0
    assert params["replay_lag_minutes"]["freeze_state"] == "FROZEN"
