from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import torch

from model.M1.data import FEATURE_NAMES_V2, fit_train_normalization
from model.M1.preparation import normalization_rows
from validation.m1_v2_data_gate_lineage import lineage_rows
from validation.m1_v2_data_gate_a import _json_serialized_payload
from validation.m1_v2_data_gate_statistics import numeric_statistics


def _state(*, decision_time, temperature, visibility=None):
    weather = SimpleNamespace(value={
        "temperature_c": temperature,
        "dewpoint_c": 3.0,
        "wind_direction_deg": 350.0,
        "wind_speed_mps": 4.0,
        "wind_gust_mps": None,
        "qnh_hpa": 1012.0,
        "visibility_m": visibility,
        "ceiling_base_m": 900.0,
    })
    schedule = SimpleNamespace(value={
        "scheduled_departure_utc": decision_time + timedelta(minutes=60),
    })
    lineage = SimpleNamespace(
        scientific_variable="current_weather",
        age_seconds=5 * 60,
    )
    return SimpleNamespace(
        successor_state={"schedule_reference": schedule},
        current_state={"current_weather": weather},
        variable_lineage=(lineage,),
        decision_node=SimpleNamespace(decision_time=decision_time),
    )


def test_normalization_rows_publish_observed_weather_without_inventing_missing():
    start = datetime(2019, 1, 1, tzinfo=timezone.utc)
    rows = normalization_rows([
        (
            _state(decision_time=start, temperature=10.0),
            _state(
                decision_time=start + timedelta(minutes=5),
                temperature=20.0,
                visibility=10000.0,
            ),
        )
    ])

    assert [row["weather.temperature_c"] for row in rows] == [10.0, 20.0]
    assert "weather.visibility_m" not in rows[0]
    assert rows[1]["weather.visibility_m"] == 10000.0
    assert all("weather.wind_direction_deg" not in row for row in rows)
    assert all("weather.wind_gust_mps" not in row for row in rows)

    artifact = fit_train_normalization(rows, split="train")
    temperature = artifact.values["weather.temperature_c"]
    assert temperature.mean == pytest.approx(15.0)
    assert temperature.std == pytest.approx(5.0)


def test_data_gate_outlier_bound_is_fit_on_train_observed_values_only():
    feature = "weather.temperature_c"
    index = FEATURE_NAMES_V2.index(feature)
    train = torch.zeros((5, len(FEATURE_NAMES_V2)))
    calibration = torch.zeros((1, len(FEATURE_NAMES_V2)))
    development = torch.zeros((1, len(FEATURE_NAMES_V2)))
    train[:, index] = torch.tensor([0.0, 1.0, 2.0, 3.0, 4.0])
    calibration[:, index] = 100.0
    development[:, index] = 2.0

    stats = numeric_statistics(
        {"train": train, "calibration": calibration, "development": development}
    )
    calibration_row = next(
        row for row in stats["calibration"] if row["feature"] == feature
    )

    assert calibration_row["outlier_rule"] == "TRAIN_OBSERVED_3_IQR"
    assert calibration_row["extreme_outlier_fraction"] == pytest.approx(1.0)


def test_data_gate_lineage_marks_known_semantic_risks_without_guessing():
    train_stats = [
        {"feature": name, "constant": False, "near_constant": False}
        for name in FEATURE_NAMES_V2
    ]
    rows = {row["M1_FIELD"]: row for row in lineage_rows(train_stats)}

    assert rows["state.ib_realized"]["FEATURE_DECISION"] == "REMOVE_LEAKAGE"
    assert rows["delta.weather.wind_direction_deg"]["FEATURE_DECISION"] == "REMOVE_UNSTABLE"
    assert rows["weather.wind_gust_mps"]["FEATURE_DECISION"] == "REMOVE_NO_INFORMATION"


def test_data_gate_hash_payload_matches_json_roundtrip():
    payload = {"timestamp": datetime(2019, 1, 1, tzinfo=timezone.utc)}

    assert _json_serialized_payload(payload) == {
        "timestamp": "2019-01-01 00:00:00+00:00"
    }
