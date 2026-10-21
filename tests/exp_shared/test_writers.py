"""Non-paper writers preserved from the retired Exp2 driver."""

from __future__ import annotations

import json

import pandas as pd

from exp.inputs.writers import write_frame, write_json


def test_reporting_writes_json_csv_and_parquet(tmp_path):
    payload = {"status": "NON_PAPER_FAST_DIAGNOSTIC", "final_test_access_count": 0}
    frame = pd.DataFrame([{"a": 1}, {"a": 2}])
    write_json(tmp_path / "report.json", payload)
    write_frame(tmp_path / "report.csv", frame)
    write_frame(tmp_path / "report.parquet", frame)
    assert json.loads((tmp_path / "report.json").read_text()) == payload
    assert pd.read_csv(tmp_path / "report.csv")["a"].tolist() == [1, 2]
    assert pd.read_parquet(tmp_path / "report.parquet")["a"].tolist() == [1, 2]
