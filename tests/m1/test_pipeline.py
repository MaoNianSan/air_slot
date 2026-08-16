from pathlib import Path
import torch
from model.M1.pipeline import M1Pipeline
from model.common.errors import ContractError
import pytest

def test_save_load_and_stable_stage_aware_scenarios(tmp_path: Path):
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.zeros(1,3,4); lengths=torch.tensor([3])
    dist = pipe.predict_distributions(values, lengths)
    scenarios1 = pipe.sample_aligned(dist, episode_id="e", decision_node_id="n", stage="POST_IB_PRE_OB", observed={"R_IB":0}, count=8, seed=7)
    scenarios2 = pipe.sample_aligned(dist, episode_id="e", decision_node_id="later", stage="POST_IB_PRE_OB", observed={"R_IB":0}, count=8, seed=7)
    assert [x.r_ib_minutes for x in scenarios1] == [0]*8
    assert [x.scenario_seed_key for x in scenarios1] == [x.scenario_seed_key for x in scenarios2]
    path=tmp_path/"m1.pt"; pipe.save(path); loaded=M1Pipeline.load(path)
    assert torch.allclose(pipe.predict_distributions(values,lengths)["R_IB"], loaded.predict_distributions(values,lengths)["R_IB"])


def test_abstained_target_is_not_sampled_and_stage_requires_observed_events():
    pipe=M1Pipeline.smoke(input_size=4);values=torch.zeros(1,2,4);lengths=torch.tensor([2])
    dist=pipe.predict_distributions(values,lengths)
    rows=pipe.sample_aligned(dist,episode_id="e",decision_node_id="n",stage="PRE_IB",observed={},
        target_support={"R_IB":"SUPPORTED","R_OB":"ABSTAIN","T_TX":"SUPPORTED"},count=2,seed=7)
    assert all(row.r_ob_minutes is None and row.ob_support=="ABSTAIN" for row in rows)
    with pytest.raises(ContractError,match="M1_STAGE_OBSERVATION_MISSING"):
        pipe.sample_aligned(dist,episode_id="e",decision_node_id="n",stage="POST_OB_PRE_TO",observed={"R_IB":1},count=2,seed=7)
