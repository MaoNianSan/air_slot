from datetime import datetime, timezone

import torch

from model.M1.pipeline import M1Pipeline
from model.PRE.foundation import PREBuildRequest, build_pre_state


def _pre(dataset: str):
    return build_pre_state(PREBuildRequest(
        episode_id="episode-z", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=timezone.utc),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=timezone.utc),
        config_hash="sha256:c", registry_hash="sha256:r",
        dataset_instance_id=dataset,
    )).pre_state


def test_true_ancestral_heads_receive_sampled_parent_categories(monkeypatch):
    pipe = M1Pipeline.smoke(input_size=4)
    calls = []

    def conditioned(history, target, ib_index=None, ob_index=None):
        calls.append((target, ib_index, ob_index))
        size = pipe.bins[target].class_count
        logits = torch.full((1, size), -100.0)
        if target == "R_IB":
            index = 1
        elif target == "R_OB":
            index = (ib_index + 1) % size
        else:
            index = (ib_index + ob_index + 1) % size
        logits[0, index] = 100.0
        return logits

    monkeypatch.setattr(pipe.model, "conditioned_logits", conditioned)
    rows = pipe.sample_from_pre(
        _pre("data2_2019"), torch.zeros(1, 2, 4), torch.tensor([2]),
        observed={}, count=3, seed=9,
    )
    assert all(row.r_ib_minutes == 7.5 for row in rows)
    assert all(row.r_ob_minutes == 12.5 for row in rows)
    assert all(row.t_tx_minutes == 22.5 for row in rows)
    assert ("R_OB", 1, None) in calls
    assert ("T_TX", 1, 2) in calls


def test_pre_support_automatically_suppresses_data1_r_ob_and_is_reproducible():
    pipe = M1Pipeline.smoke(input_size=4)
    args = (_pre("data1_2019"), torch.zeros(1, 2, 4), torch.tensor([2]))
    first = pipe.sample_from_pre(*args, observed={}, count=8, seed=17)
    second = pipe.sample_from_pre(*args, observed={}, count=8, seed=17)
    assert [row.model_dump() for row in first] == [row.model_dump() for row in second]
    assert all(row.r_ob_minutes is None and row.ob_support == "ABSTAIN" for row in first)
    assert all(row.t_tx_minutes is not None for row in first)
    assert [row.scenario_id for row in first] == list(range(8))


def test_row_order_and_decision_node_updates_do_not_change_scenario_identity():
    pipe=M1Pipeline.smoke(input_size=4);pre=_pre("data2_2019")
    values=torch.zeros(1,2,4);lengths=torch.tensor([2])
    first=pipe.sample_from_pre(pre,values,lengths,observed={},count=6,seed=5)
    later=pre.model_copy(update={"decision_node":pre.decision_node.model_copy(
        update={"decision_node_id":"later-node"})})
    second=pipe.sample_from_pre(later,values,lengths,observed={},count=6,seed=5)
    assert {row.scenario_id:row.scenario_seed_key for row in reversed(first)} == {
        row.scenario_id:row.scenario_seed_key for row in second}
