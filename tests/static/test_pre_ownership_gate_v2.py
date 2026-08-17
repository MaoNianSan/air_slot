from pathlib import Path

from validation.ownership_gate_v2 import build_gate_result


def test_pre_ownership_gate_v2_passes():
    result = build_gate_result(Path("."))
    assert result["PRE_OWNERSHIP_GATE"] == "PASS", result["findings"]
    assert result["STATIC_VOLUME_GATE"] == "PASS", result["volume_failures"]
    assert result["PRE_DATA_CONSTRUCTION_OUTSIDE_PRE"] == 0
    assert result["MODEL_LOGIC_OUTSIDE_MODEL"] == 0
    assert result["EXP_LOGIC_OUTSIDE_EXP"] == 0
