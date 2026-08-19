"""V2 ancestral-closure tests for the M1 state estimator.

Verifies the formal order T_IB_A00 -> D_OB -> D_TX: each successor head
receives the sampled/observed parent bin, support abstention propagates from
formal parents to children, and scenario identity is seed-stable.
"""

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


def _as_index(value):
    if isinstance(value, torch.Tensor):
        return int(value.reshape(-1)[0])
    return int(value)


def test_true_ancestral_heads_receive_sampled_parent_categories(monkeypatch):
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    hazard = pipe.contracts["T_IB_A00"]
    d_ob = pipe.contracts["D_OB"]
    d_tx = pipe.contracts["D_TX"]
    calls = []

    def hazard_logits(history):
        logits = torch.full((history.shape[0], hazard.finite_class_count), -100.0)
        logits[:, 1] = 100.0  # all PMF mass on remaining-time bin 1
        return logits

    def d_ob_heads(history, ib_index):
        calls.append(("D_OB", _as_index(ib_index)))
        zero = torch.full((history.shape[0], 1), 100.0)  # P(D_OB == 0) ~ 1
        quant = torch.zeros(history.shape[0], d_ob.quantile_count)
        return zero, quant

    def d_tx_heads(history, ib_index, d_ob_index):
        calls.append(("D_TX", _as_index(ib_index), _as_index(d_ob_index)))
        zero = torch.full((history.shape[0], 1), 100.0)  # P(D_TX == 0) ~ 1
        quant = torch.zeros(history.shape[0], d_tx.quantile_count)
        return zero, quant

    monkeypatch.setattr(model, "hazard_logits", hazard_logits)
    monkeypatch.setattr(model, "d_ob_heads", d_ob_heads)
    monkeypatch.setattr(model, "d_tx_heads", d_tx_heads)

    rows = pipe.sample_from_pre(
        _pre("data2_2019"), torch.zeros(1, 2, 4), torch.tensor([2]),
        observed={}, count=3, seed=9,
    )
    # Bin 1 representative is 7.5 minutes; D_OB/D_TX sample exactly zero.
    assert all(row.r_ib_minutes == 7.5 for row in rows)
    assert all(row.d_ob_minutes == 0.0 and row.d_tx_minutes == 0.0 for row in rows)
    assert all(row.d_to_minutes == 0.0 for row in rows)
    assert ("D_OB", 1) in calls
    assert ("D_TX", 1, 0) in calls
    assert len(calls) == 6  # 3 scenarios x (D_OB + D_TX)


def test_pre_support_automatically_suppresses_data1_d_ob_and_is_reproducible():
    pipe = M1Pipeline.smoke(input_size=4)
    args = (_pre("data1_2019"), torch.zeros(1, 2, 4), torch.tensor([2]))
    first = pipe.sample_from_pre(*args, observed={}, count=8, seed=17)
    second = pipe.sample_from_pre(*args, observed={}, count=8, seed=17)
    assert [row.model_dump() for row in first] == [row.model_dump() for row in second]
    assert all(row.d_ob_minutes is None and row.d_ob_support == "ABSTAIN" for row in first)
    # Formal parent abstention propagates to the D_TX child.
    assert all(row.d_tx_minutes is None and row.d_tx_support == "ABSTAIN" for row in first)
    assert all(row.t_ib_a00_utc is not None for row in first)
    assert [row.scenario_id for row in first] == list(range(8))


def test_row_order_and_decision_node_updates_do_not_change_scenario_identity():
    pipe = M1Pipeline.smoke(input_size=4)
    pre = _pre("data2_2019")
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    first = pipe.sample_from_pre(pre, values, lengths, observed={}, count=6, seed=5)
    later = pre.model_copy(update={"decision_node": pre.decision_node.model_copy(
        update={"decision_node_id": "later-node"})})
    second = pipe.sample_from_pre(later, values, lengths, observed={}, count=6, seed=5)
    assert {row.scenario_id: row.scenario_seed_key for row in reversed(first)} == {
        row.scenario_id: row.scenario_seed_key for row in second}
