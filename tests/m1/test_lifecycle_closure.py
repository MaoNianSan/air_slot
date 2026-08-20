"""M1 V2 lifecycle closure over hazard + hurdle-quantile heads."""

from datetime import date, datetime, timezone
from pathlib import Path

import torch

from model.M1.contracts import (
    M1_TEMPERATURE_D_OB_ZERO,
    M1_TEMPERATURE_D_TX_ZERO,
    M1_TEMPERATURE_HAZARD,
)
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample, chronological_split
from model.M1.pipeline import M1Pipeline
from model.PRE.foundation import PREBuildRequest, build_pre_state

V2_TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")


def _example(episode, day, offset):
    return M1TrainingExample(
        episode_id=episode,
        episode_date=day,
        values=torch.full((3, 4), float(offset)),
        targets={"T_IB_REMAINING_HAZARD": offset % 6,
                 "D_OB": (offset + 1) % 11,
                 "D_TX": (offset + 2) % 6},
        active={"T_IB_REMAINING_HAZARD": True, "D_OB": episode != "data1", "D_TX": True},
    )


def test_chronological_episode_safe_lifecycle_train_calibrate_load_infer(tmp_path: Path):
    examples = [_example("train", date(2019, 6, 1), 0),
                _example("cal", date(2019, 7, 1), 1),
                _example("dev", date(2019, 8, 1), 2),
                _example("test", date(2019, 10, 1), 3)]
    split = chronological_split(examples)
    assert {name: [x.episode_id for x in rows] for name, rows in split.items()} == {
        "train": ["train"], "calibration": ["cal"],
        "development": ["dev"], "test": ["test"]}
    lifecycle = M1Lifecycle(M1Pipeline.smoke(4))
    history = lifecycle.train(split["train"], epochs=2, learning_rate=.01)
    temperatures = lifecycle.calibrate(split["calibration"])
    assert history and set(temperatures) == {
        M1_TEMPERATURE_HAZARD, M1_TEMPERATURE_D_OB_ZERO, M1_TEMPERATURE_D_TX_ZERO}
    artifact = tmp_path / "m1.pt"
    lifecycle.save(artifact)
    loaded = M1Lifecycle.load(artifact)
    distributions = loaded.infer(torch.zeros(1, 3, 4), torch.tensor([3]))
    hazard = loaded.pipeline.contracts["T_IB_REMAINING_HAZARD"]
    assert distributions["T_IB_A00"].shape == (1, hazard.class_count)
    assert distributions["D_OB"]["zero_probability"].shape == (1,)
    assert distributions["D_OB"]["positive_quantiles_minutes"].shape == (1, 5)
    assert distributions["D_TX"]["positive_quantiles_minutes"].shape == (1, 5)


def test_support_mask_excludes_partial_target_from_training_loss():
    pre = build_pre_state(PREBuildRequest(
        episode_id="data1", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=timezone.utc),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=timezone.utc),
        config_hash="sha256:c", registry_hash="sha256:r",
        dataset_instance_id="data1_2019")).pre_state
    example = M1TrainingExample.from_pre_support(
        episode_id="data1", episode_date=date(2019, 6, 1),
        values=torch.zeros(3, 4),
        targets={"T_IB_REMAINING_HAZARD": 0, "D_OB": 1, "D_TX": 2},
        target_support=pre.target_support)
    assert example.active == {"T_IB_REMAINING_HAZARD": True, "D_OB": False, "D_TX": True}
    lifecycle = M1Lifecycle(M1Pipeline.smoke(4))
    history = lifecycle.train([example], epochs=1, learning_rate=.01)
    assert history[0]["active_counts"]["D_OB"] == 0
    assert torch.isfinite(torch.tensor(history[0]["loss"]))
