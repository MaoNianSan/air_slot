from pathlib import Path

from validation.model.data2_fast_smoke import run


def test_fast_smoke_gate_is_read_only_and_accepts_frozen_h8_artifact(tmp_path):
    result = run(tmp_path)
    assert result["data_guard"]["data1_modified"] is False
    assert result["data_guard"]["data2_modified"] is False
    assert result["scenario_count"] == 64
    assert result["M3"]["template_count"] == 23
    assert result["M4"]["chi_sel"] == "UNIMPLEMENTED"
    assert result["status"] == "PASS"
    assert result["failures"] == []
    assert (tmp_path / "FAST_SMOKE_SUMMARY.json").is_file()
    assert (tmp_path / "FAST_SMOKE_MANIFEST.json").is_file()
