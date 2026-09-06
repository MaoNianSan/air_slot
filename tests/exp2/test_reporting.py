import json

import pandas as pd

from exp.exp2 import run
from exp.exp2.protocol import COMPONENTS
from exp.exp2.reporting import write_frame, write_json


def test_reporting_writes_json_csv_and_parquet(tmp_path):
    payload = {"status": "NON_PAPER_FAST_DIAGNOSTIC", "final_test_access_count": 0}
    frame = pd.DataFrame([{"a": 1}, {"a": 2}])
    write_json(tmp_path / "report.json", payload)
    write_frame(tmp_path / "report.csv", frame)
    write_frame(tmp_path / "report.parquet", frame)
    assert json.loads((tmp_path / "report.json").read_text()) == payload
    assert pd.read_csv(tmp_path / "report.csv")["a"].tolist() == [1, 2]
    assert pd.read_parquet(tmp_path / "report.parquet")["a"].tolist() == [1, 2]


def test_fast_materialization_writes_non_paper_artifacts(tmp_path, monkeypatch):
    rows = []
    for episode_index in range(4):
        for node_index in range(2):
            value = float(episode_index * 2 + node_index)
            rows.append(
                {
                    "episode_id": f"e{episode_index}",
                    "decision_node_id": f"e{episode_index}-n{node_index}",
                    "decision_time": "2019-08-15T10:00:00+00:00",
                    "information_cutoff": "2019-08-15T10:00:00+00:00",
                    "operational_stage": "PRE_IB",
                    "common_support_mass": 1.0,
                    "common_support_scenario_count": 64,
                    "scenario_count_total": 64,
                    "support_primary": True,
                    "support_sensitivity": True,
                    "support_full": True,
                    "conditional_aggregate_complete": True,
                    "formal_full_support": True,
                    "delay_to_mean": value,
                    **{f"{component}_native": value for component in COMPONENTS},
                    **{f"Z_{component}": value for component in COMPONENTS},
                    **{f"{component}_status": "SUPPORTED" for component in COMPONENTS},
                    **{
                        f"unsupported_scenario_count_{reason}": 0
                        for reason in ("D_TO", *COMPONENTS)
                    },
                }
            )
    monkeypatch.setattr(run, "OUTPUT", tmp_path / "development")
    monkeypatch.setattr(run, "_head", lambda: "test-head")
    result = run.execute_node_materialization(pd.DataFrame(rows), fast=True)
    assert result["manifest"]["status"] == "NON_PAPER_FAST_DIAGNOSTIC"
    assert result["manifest"]["bootstrap_replicates"] == 20
    assert result["manifest"]["final_test_access_count"] == 0
    assert (tmp_path / "development/data/EXP2_PRIORITY_BASE.parquet").is_file()
    assert (tmp_path / "development/results/EXP2_DEVELOPMENT_SUMMARY.json").is_file()
