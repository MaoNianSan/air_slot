from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.input import FORMAL_TARGET_COLUMN, _target_outcome_feature_mask
from src.m1_training import make_transformer, prepare_model_frame


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshots = pd.DataFrame([
        {
            "episode_id": "e1", "flight_id": "f1", "snapshot_id": "s1",
            "elapsed_ratio": 0.2, "current_altitude": 10000.0,
            "current_velocity": 220.0, "vertical_rate": 1.0,
            "trajectory_coverage": 0.9, "wind_speed": 5.0,
            "airport_flow_pressure": 0.4, "turnaround_margin": 20.0,
            "execution_window_margin": 30.0, "lead_time_margin": 40.0,
            "aircraft_group": "narrow_body", "airport": "EDDF",
            "origin": "EHAM", "destination": "EDDF", "month": 5,
            "time_bin": "12_18", "snapshot_stage": "t1",
            "has_predecessor_candidate": True,
            "has_supported_predecessor": True,
            "predecessor_observed_duration": 60.0,
            "observed_ground_gap_minutes": 45.0,
            "predecessor_support_status": "SUPPORTED",
            "predecessor_evidence_tier": "R2_STRICT",
            "continuation_risk_proxy": 0.25,
            "future_successor_delay": 999.0,
        },
        {
            "episode_id": "e2", "flight_id": "f2", "snapshot_id": "s2",
            "elapsed_ratio": 0.5, "current_altitude": 15000.0,
            "current_velocity": 240.0, "vertical_rate": 0.0,
            "trajectory_coverage": 0.8, "wind_speed": 7.0,
            "airport_flow_pressure": 0.5, "turnaround_margin": 25.0,
            "execution_window_margin": 35.0, "lead_time_margin": 45.0,
            "aircraft_group": "narrow_body", "airport": "LEMD",
            "origin": "EDDF", "destination": "LEMD", "month": 5,
            "time_bin": "12_18", "snapshot_stage": "t2",
            "has_predecessor_candidate": False,
            "has_supported_predecessor": False,
            "predecessor_observed_duration": pd.NA,
            "observed_ground_gap_minutes": pd.NA,
            "predecessor_support_status": "UNSUPPORTED",
            "predecessor_evidence_tier": pd.NA,
            "continuation_risk_proxy": pd.NA,
            "future_successor_delay": 999.0,
        },
    ])
    episodes = pd.DataFrame([
        {"episode_id": "e1", FORMAL_TARGET_COLUMN: 12.0},
        {"episode_id": "e2", FORMAL_TARGET_COLUMN: 18.0},
    ])
    return snapshots, episodes


def test_predecessor_features_enter_training_and_inference_X() -> None:
    cfg = load_config(ROOT, mode="fast")
    snapshots, episodes = _frames()
    frame, features, numeric, categorical = prepare_model_frame(
        snapshots, episodes, cfg.scientific
    )
    expected_previous = {
        "has_supported_predecessor", "predecessor_observed_duration",
        "observed_ground_gap_minutes", "predecessor_support_status",
        "continuation_risk_proxy",
    }
    assert expected_previous.issubset(features)
    assert {"current_altitude", "current_velocity", "trajectory_coverage"}.issubset(features)
    assert "future_successor_delay" not in features
    transformer = make_transformer(numeric, categorical)
    training_x = transformer.fit_transform(frame[features])
    inference_x = transformer.transform(frame[features])
    assert training_x.shape == inference_x.shape
    assert training_x.shape[0] == 2


def test_current_features_remain_primary_dynamic_inputs() -> None:
    cfg = load_config(ROOT, mode="fast")
    snapshots, episodes = _frames()
    _, features, _, _ = prepare_model_frame(snapshots, episodes, cfg.scientific)
    current = {
        "elapsed_ratio", "current_altitude", "current_velocity", "vertical_rate",
        "trajectory_coverage", "wind_speed", "airport_flow_pressure",
        "execution_window_margin", "lead_time_margin", "snapshot_stage",
    }
    assert current.issubset(features)
    assert cfg.scientific["m1"]["formal_target"] == FORMAL_TARGET_COLUMN
    assert cfg.scientific["m1"]["feature_contract_version"] == "M1_PREVIOUS_LEG_V1"


def test_predecessor_lastseen_proxy_is_not_current_target_leakage() -> None:
    names = pd.Series([
        "predecessor_lastseen_proxy",
        "current_lastseen",
        "movement_outcome",
    ])
    assert _target_outcome_feature_mask(names).tolist() == [False, True, True]
