import json
from pathlib import Path

import pytest
import torch

from model.M1.history import HistoryEncoderMode
from model.M1.pipeline import M1Pipeline
from model.M1.tuning_stage1 import (
    STAGE1_H_CANDIDATES,
    STAGE1_METRICS,
    exp1_interface_contract,
    run_fast_train_mode,
    stage1_development_metrics,
    stage1_manifest,
    stage1_parameter_count,
)


def test_stage1_manifest_matches_frozen_contract_and_is_not_run():
    manifest = stage1_manifest(Path("."))
    assert manifest["status"] == "M1_V2_TUNING_STAGE1_READY"
    assert manifest["execution_authorized"] is False
    assert manifest["candidate_list"] == ["NO_HISTORY", "H8", "H16", "H32"]
    assert [row["hidden_size"] for row in manifest["candidates"][:3]] == [8, 16, 32]
    assert manifest["fixed_contract"]["total_feature_count"] == 43
    assert manifest["fixed_contract"]["support"] == {
        "T_IB_REMAINING_HAZARD": 360,
        "D_OB": 210,
        "D_TX": 60,
        "bin_width_minutes": 5,
    }
    assert manifest["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    assert all(row["run_status"] == "NOT_RUN" for row in manifest["candidates"])


def test_stage1_manifest_file_matches_preparation_contract():
    path = Path(
        "artifacts/diagnostics/m1_v2_paper_model_closure/"
        "M1_V2_TUNING_STAGE1_MANIFEST.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["candidate_list"] == ["NO_HISTORY", "H8", "H16", "H32"]
    assert manifest["development_evaluation"]["principal"] == STAGE1_METRICS[0]
    assert manifest["development_evaluation"]["secondary"] == list(STAGE1_METRICS[1:])
    assert manifest["safety"]["M1_TRAINING_RUNS"] == 0
    assert manifest["safety"]["TUNING_RUNS"] == 0
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0


def test_no_history_disables_encoder_and_uses_only_last_admissible_row(tmp_path):
    pipeline = M1Pipeline.smoke(
        4, history_mode=HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION,
    )
    model = pipeline.model
    assert model.history_mode is HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION
    assert model.history_encoder_enabled is False
    assert model.gru is None
    first = torch.tensor([[[1., 2., 3., 4.], [5., 6., 7., 8.]]])
    changed_prefix = torch.tensor([[[90., 91., 92., 93.], [5., 6., 7., 8.]]])
    lengths = torch.tensor([2])
    assert torch.allclose(
        model.encode_history(first, lengths),
        model.encode_history(changed_prefix, lengths),
    )
    artifact = tmp_path / "no_history.pt"
    pipeline.save(artifact)
    loaded = M1Pipeline.load(artifact)
    assert loaded.history_mode is HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION
    assert loaded.model.gru is None


def test_stage1_metric_projection_reuses_existing_episode_balanced_objective():
    class FakeLifecycle:
        def episode_balanced_objective(self, examples, *, batch_size, teacher_forcing):
            assert examples == ("development",)
            assert batch_size == 4
            assert teacher_forcing is True
            return {
                "EPISODE_BALANCED_JOINT_VALIDATION_LOSS": 10.0,
                "T_IB_HAZARD_NLL": 1.0,
                "D_OB_ZERO_BCE": 2.0,
                "D_OB_POSITIVE_PINBALL": 3.0,
                "D_TX_ZERO_BCE": 4.0,
                "D_TX_POSITIVE_PINBALL": 5.0,
            }

    assert stage1_development_metrics(
        FakeLifecycle(), ("development",), batch_size=4,
    ) == {
        "EPISODE_BALANCED_JOINT_VALIDATION_LOSS": 10.0,
        "T_IB_HAZARD_NLL": 1.0,
        "D_OB_ZERO_BCE": 2.0,
        "D_OB_POSITIVE_QUANTILE_LOSS": 3.0,
        "D_TX_ZERO_BCE": 4.0,
        "D_TX_POSITIVE_QUANTILE_LOSS": 5.0,
    }


def test_fast_train_mode_requires_explicit_authorization():
    with pytest.raises(RuntimeError, match="EXPLICIT_AUTHORIZATION"):
        run_fast_train_mode(
            object(), (), (), output_dir=Path("artifacts/tmp"),
        )


def test_exp1_interface_contract_is_read_only_and_horizon_complete():
    interface = exp1_interface_contract()
    assert interface["exp1_mutation"] is False
    assert interface["forecast_horizons_minutes"] == [
        0, 30, 60, 120, 180, 240, 300, 360, 420, 480,
    ]
    assert interface["joint_state_distribution_artifact"]["status"] == "READY"
    assert interface["marginal_distribution_artifact"]["status"] == "READY"


def test_stage1_parameter_counts_are_deterministic_and_ordered():
    counts = [stage1_parameter_count(size) for size in STAGE1_H_CANDIDATES]
    assert counts == [4708, 9716, 20884]
    assert stage1_parameter_count(
        16, history_mode=HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION,
    ) == 7620
