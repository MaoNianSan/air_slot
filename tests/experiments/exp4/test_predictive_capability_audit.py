import json
from pathlib import Path

from exp.exp4.predictive_capability_audit import (
    _fitted_lightgbm_registered,
    _random_forest_artifact_found,
    audit,
)


ROOT = Path(__file__).resolve().parents[3]


def test_predictive_capability_audit_preserves_real_baseline_and_data1_gates(tmp_path):
    paths = audit(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))

    assert artifact["status"] == "EXP4_PREDICTIVE_ARTIFACTS_BLOCKED_CAPABILITIES_AUDITED"
    assert artifact["baseline_capabilities"]["LIGHTGBM_FAST"]["implementation_found"] is True
    lightgbm = artifact["baseline_capabilities"]["LIGHTGBM_FAST"]
    assert lightgbm["train_frozen_fitted_artifact_registered"] is _fitted_lightgbm_registered(ROOT)
    rf = artifact["baseline_capabilities"]["RANDOM_FOREST"]
    assert rf["implementation_or_fitted_artifact_found"] is _random_forest_artifact_found(ROOT)
    data1 = artifact["data_environment_capabilities"]["data1_2019"]
    assert data1["schedule"]["formal_input_support"] == "UNSUPPORTED"
    assert data1["pooling_with_data2"] == "FORBIDDEN"
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
