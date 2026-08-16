from datetime import date
from pathlib import Path

import torch

from model.M1.lifecycle import M1Lifecycle, M1TrainingExample, chronological_split
from model.M1.pipeline import M1Pipeline
from model.PRE.foundation import PREBuildRequest, build_pre_state
from datetime import datetime, timezone


def _example(episode, day, offset):
    return M1TrainingExample(episode_id=episode, episode_date=day,
        values=torch.full((3, 4), float(offset)), labels={"R_IB": offset % 6,
        "R_OB": (offset + 1) % 6, "T_TX": (offset + 2) % 6},
        active={"R_IB": True, "R_OB": episode != "data1", "T_TX": True})


def test_chronological_episode_safe_lifecycle_train_calibrate_load_infer(tmp_path: Path):
    examples=[_example("train",date(2019,6,1),0),_example("cal",date(2019,7,1),1),
              _example("dev",date(2019,8,1),2),_example("test",date(2019,10,1),3)]
    split=chronological_split(examples)
    assert {name:[x.episode_id for x in rows] for name,rows in split.items()} == {
        "train":["train"],"calibration":["cal"],"development":["dev"],"test":["test"]}
    lifecycle=M1Lifecycle(M1Pipeline.smoke(4))
    history=lifecycle.train(split["train"],epochs=2,learning_rate=.01)
    temperatures=lifecycle.calibrate(split["calibration"])
    assert history and set(temperatures)=={"R_IB","R_OB","T_TX"}
    artifact=tmp_path/"m1.pt"; lifecycle.save(artifact)
    loaded=M1Lifecycle.load(artifact)
    distributions=loaded.infer(torch.zeros(1,3,4),torch.tensor([3]))
    assert all(value.shape==(1,6) for value in distributions.values())


def test_support_mask_excludes_partial_target_from_training_loss():
    pre=build_pre_state(PREBuildRequest(episode_id="data1",predecessor_id="P",successor_id="S",
        decision_time=datetime(2019,1,1,12,tzinfo=timezone.utc),information_cutoff=datetime(2019,1,1,11,55,tzinfo=timezone.utc),
        config_hash="sha256:c",registry_hash="sha256:r",dataset_instance_id="data1_2019")).pre_state
    example=M1TrainingExample.from_pre_support(episode_id="data1",episode_date=date(2019,6,1),
        values=torch.zeros(3,4),labels={"R_IB":0,"R_OB":1,"T_TX":2},target_support=pre.target_support)
    lifecycle=M1Lifecycle(M1Pipeline.smoke(4)); history=lifecycle.train([example],epochs=1,learning_rate=.01)
    assert history[0]["active_counts"]["R_OB"] == 0
