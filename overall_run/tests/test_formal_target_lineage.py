from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.failures import FormalRunBlocked
from src.input import resolve_m1_target_column
from src.m1 import prepare_model_frame


CONFIG = {
    "formal_target": "y_movement_raw",
    "sensitivity_target": "y_movement_model",
}


def test_formal_mode_selects_raw_when_both_labels_exist() -> None:
    frame = pd.DataFrame({"y_movement_raw": [1.0], "y_movement_model": [2.0]})
    assert resolve_m1_target_column(frame, CONFIG) == "y_movement_raw"


def test_formal_mode_does_not_fallback_to_sensitivity_label() -> None:
    frame = pd.DataFrame({"y_movement_model": [2.0]})
    with pytest.raises(FormalRunBlocked, match="FORMAL_TARGET_MISSING"):
        resolve_m1_target_column(frame, CONFIG)


def test_sensitivity_label_requires_explicit_mode() -> None:
    frame = pd.DataFrame({"y_movement_raw": [1.0], "y_movement_model": [2.0]})
    assert resolve_m1_target_column(frame, CONFIG, sensitivity=True) == "y_movement_model"


def test_candidate_fallback_config_is_rejected() -> None:
    frame = pd.DataFrame({"y_movement_raw": [1.0], "y_movement_model": [2.0]})
    with pytest.raises(FormalRunBlocked, match="target_candidates is prohibited"):
        resolve_m1_target_column(frame, {**CONFIG, "target_candidates": ["y_movement_model"]})


def test_model_frame_aliases_raw_even_when_twelve_sensitivity_rows_differ() -> None:
    episodes = pd.DataFrame({
        "episode_id": [f"e{i}" for i in range(20)],
        "y_movement_raw": range(20),
        "y_movement_model": [value + (100 if value < 12 else 0) for value in range(20)],
        "target": range(20),
    })
    snapshots = pd.DataFrame({
        "episode_id": episodes["episode_id"],
        "feature": range(20),
        "decision_time": pd.to_datetime(["2022-05-01T00:00:00Z"] * 20),
    })
    scientific = {"m1": {"formal_target": "y_movement_raw", "feature_allowlist": ["feature"], "prohibited_patterns": []}}
    model_frame, *_ = prepare_model_frame(snapshots, episodes, scientific)
    assert model_frame["target"].equals(pd.to_numeric(model_frame["y_movement_raw"]))
    assert int((episodes["y_movement_raw"] != episodes["y_movement_model"]).sum()) == 12
