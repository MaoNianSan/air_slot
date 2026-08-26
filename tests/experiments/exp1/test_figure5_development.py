"""Contract tests for the Exp1 Figure 5 Development figures module."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from exp.reporting.figure5_exp1_development import (
    DEFAULT_OUTPUT_ROOT,
    ROOT,
    run,
    history_current_deltas_frame,
    lead_time_delta_frame,
    load_summary,
    sorting_summary_frame,
    stage_strata_frame,
)


@pytest.fixture(scope="module")
def output_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("exp1_figures")
    run(output_root=root)
    return root


@pytest.fixture(scope="module")
def summary() -> dict:
    return load_summary()


def test_figure_files_generated(output_root: Path) -> None:
    for extension in ("pdf", "svg", "png"):
        path = output_root / "figures" / f"figure_5_exp1_direct_information.{extension}"
        assert path.is_file() and path.stat().st_size > 1000, path


def test_data_frames_written(output_root: Path) -> None:
    for name in (
        "figure_5a_sorting_summary.csv",
        "figure_5b_stage_strata.csv",
        "figure_5c_history_current_deltas.csv",
        "figure_5c_lead_time_delta_mae.csv",
    ):
        path = output_root / "data" / name
        assert path.is_file() and path.stat().st_size > 0, path


def test_caption_wording(output_root: Path) -> None:
    caption = (output_root / "figure_5_caption.txt").read_text(encoding="utf-8")
    assert "separate checkpoints" in caption
    assert "same checkpoint" not in caption.replace("same architecture", "").replace(
        "same architecture", ""
    ) or caption.count("same checkpoint") == 0
    assert "DEVELOPMENT_ONLY" in caption


def test_manifest_safety_and_hashes(output_root: Path) -> None:
    manifest = json.loads(
        (output_root / "EXP1_FIGURES_MANIFEST_DEVELOPMENT_ONLY.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["paper_result"] is False
    assert manifest["final_test_access_count"] == 0
    assert manifest["safety"]["EXP1_RERUNS"] == 0
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["safety"]["PAPER_FULL_RUN"] is False
    assert manifest["input_summary_hash"].startswith("sha256:")
    assert manifest["closure_artifact_hash"].startswith("sha256:")
    assert manifest["bootstrap"] == {
        "resampling_unit": "EPISODE",
        "replicates": 2000,
        "seed": 20260825,
        "ci_method": "PERCENTILE_95",
    }


def test_sorting_frame_consistent(summary: dict) -> None:
    frame = sorting_summary_frame(summary)
    diag = summary["exp1a"]["sorting_diagnostic"]
    assert len(frame) == 3
    assert list(frame["specification"]) == [
        "Main (support>=0.90)",
        "Sensitivity (support>=0.50)",
        "p90 D_TO sensitivity",
    ]
    assert frame.iloc[0]["n_nodes"] == diag["included_main_nodes"] == 1420
    assert frame.iloc[0]["spearman_rho"] == diag["main"]["spearman_rho"]
    assert frame.iloc[0]["decile_divergence_ci_lower"] == pytest.approx(
        diag["main"]["decile_divergence_bootstrap"]["ci_95"][0]
    )


def test_stage_strata_consistent(summary: dict) -> None:
    frame = stage_strata_frame(summary)
    strata = summary["exp1a"]["sorting_diagnostic"]["secondary"][
        "operational_stage_strata"
    ]
    assert list(frame["operational_stage"]) == ["PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO"]
    for stage in frame["operational_stage"]:
        assert frame.loc[frame["operational_stage"] == stage, "n_nodes"].iloc[0] == (
            strata[stage]["n_nodes"]
        )


def test_deltas_frame_consistent(summary: dict) -> None:
    frame = history_current_deltas_frame(summary)
    targets = summary["exp1b"]["paired"]["targets"]
    assert set(frame["target"]) == {"T_IB_A00", "D_OB", "D_TX"}
    for target in frame["target"]:
        block = targets[target]
        row = frame.loc[frame["target"] == target].iloc[0]
        assert row["delta_mae_minutes"] == block["delta_mae_minutes"]["estimate"]
        assert row["delta_crps_minutes"] == block["delta_crps_minutes"]["estimate"]


def test_lead_time_delta_uses_supported_bins_only(summary: dict) -> None:
    frame = lead_time_delta_frame(summary)
    targets = summary["exp1b"]["paired"]["targets"]
    d_tx_bins = (targets["D_TX"].get("delta_mae_by_bin_minutes") or {})
    assert "D_TX" not in set(frame["target"])
    assert all(
        frame["n_episodes"] > 0
    )
    for target in ("T_IB_A00", "D_OB"):
        for _, row in frame.loc[frame["target"] == target].iterrows():
            block = targets[target]["delta_mae_by_bin_minutes"][
                str(row["lead_time_bin_minutes"])
            ]
            assert row["delta_mae_minutes"] == block["estimate"]
