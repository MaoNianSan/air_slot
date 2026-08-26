"""Final Test calibrated scenario contract tests (V3 D6, 2026-08-26).

Fast tests only: no M1 inference, no parquet streaming.  Verifies the frozen
seeds, the shared-artifact application mapping for both model ids, and the
DEVELOPMENT-cohort safety contract of the Final Test scenario materialization.
"""

from __future__ import annotations

import json
from pathlib import Path

from exp.reporting.calibration_artifact import apply_calibration_artifact
from exp.reporting.final_test_scenarios import (
    CURRENT_ONLY_MODEL_ID,
    SAFETY,
    SCENARIO_COUNT,
    SCENARIO_SEED,
    STATE_AWARE_MODEL_ID,
    _content_hash,
)
from exp.workflows.m1_v2_current_stage_scenario_envelope import SCENARIO_COUNT as ENV_COUNT
from exp.workflows.m1_v2_current_stage_scenario_envelope import SCENARIO_SEED as ENV_SEED


def test_frozen_seeds_and_counts():
    assert SCENARIO_COUNT == ENV_COUNT == 250
    assert SCENARIO_SEED == ENV_SEED == 20260813


def test_safety_contract():
    assert SAFETY["FINAL_TEST_ACCESS_COUNT"] == 0
    assert SAFETY["PAPER_FULL_RUN"] is False
    assert SAFETY["MODEL_RETRAINED"] is False


def _artifact_payload():
    return json.loads(
        Path(
            "artifacts/calibration/m1_v2_calibration_20260826/"
            "M1_V2_CALIBRATION_ARTIFACT.json"
        ).read_text(encoding="utf-8")
    )


def test_artifact_has_both_model_records():
    artifact = _artifact_payload()
    model_ids = {record["model_id"] for record in artifact["models"].values()}
    assert model_ids == {STATE_AWARE_MODEL_ID, CURRENT_ONLY_MODEL_ID}
    for record in artifact["models"].values():
        temps = record["temperatures"]
        assert set(temps) == {"hazard", "d_ob_zero", "d_tx_zero"}
        assert temps["hazard"] != 1.0  # fitted, not identity


class _FakePipeline:
    def __init__(self):
        self.temperatures = {"hazard": 1.0, "d_ob_zero": 1.0, "d_tx_zero": 1.0}


def test_apply_calibration_maps_both_models():
    from model.M1.contracts import (
        M1_TEMPERATURE_D_OB_ZERO,
        M1_TEMPERATURE_D_TX_ZERO,
        M1_TEMPERATURE_HAZARD,
    )

    artifact = _artifact_payload()
    pipeline = _FakePipeline()
    applied = apply_calibration_artifact(pipeline, artifact, STATE_AWARE_MODEL_ID)
    expected = artifact["models"]["STATE_AWARE_H32"]["temperatures"]
    assert applied[M1_TEMPERATURE_HAZARD] == expected["hazard"]
    assert pipeline.temperatures[M1_TEMPERATURE_HAZARD] == applied[M1_TEMPERATURE_HAZARD]
    assert pipeline.temperatures[M1_TEMPERATURE_D_OB_ZERO] == expected["d_ob_zero"]
    assert pipeline.temperatures[M1_TEMPERATURE_D_TX_ZERO] == expected["d_tx_zero"]
    pipeline2 = _FakePipeline()
    applied2 = apply_calibration_artifact(pipeline2, artifact, CURRENT_ONLY_MODEL_ID)
    expected2 = artifact["models"]["CURRENT_ONLY"]["temperatures"]
    assert applied2[M1_TEMPERATURE_HAZARD] == expected2["hazard"]


def test_content_hash_deterministic():
    payload = {"a": [1, 2], "b": {"c": None}}
    assert _content_hash(payload) == _content_hash(payload)
    assert _content_hash(payload) != _content_hash({"a": [1, 2], "b": {"c": 1}})
