from __future__ import annotations

from datetime import timezone

import pandas as pd

from overall_run.src.m1 import M1Pipeline, M1Settings, TriggerType
from overall_run.src.m1.distribution import physical_identity_holds


def test_synthetic_published_bundle_to_joint_samples(published_bundle) -> None:
    settings = M1Settings(sample_count=8, base_seed=17)
    pipeline = M1Pipeline.engineering(
        published_bundle,
        settings,
        ("wind_speed", "visibility"),
        {"R_OB": [0.0, 5.0, 10.0], "T_TX": [10.0, 15.0, 20.0]},
    )
    result = pipeline.update_and_predict(
        "ep-1",
        "2026-01-01T10:40:00Z",
        TriggerType.DIRECT,
        False,
        successor_sobt=pd.Timestamp("2026-01-01 11:00", tz="UTC").to_pydatetime(),
        turnaround_floor_minutes=30.0,
        taxi_reference_minutes=15.0,
    )
    assert set(result.prediction.distributions) == {"R_IB", "R_OB", "T_TX"}
    assert len(result.joint_samples) == 8
    assert physical_identity_holds(result.joint_samples)
    assert all(sample.query_time.tzinfo == timezone.utc for sample in result.joint_samples)
    manifest = pipeline.manifest(result.prediction.target_support_level)
    assert manifest.engineering_status == "PASS"
    assert manifest.m2_interface_status == "M2_CONTRACT_MISMATCH"
