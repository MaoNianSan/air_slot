"""V2 batched warning closure: vectorized path equals the object path.

The batched sampler must agree with ``ancestral_sample_v2`` +
``warning_probability`` on every sampled index and on the derived D_TO
probability, and it must abstain when formal inputs are missing.
"""

import pytest
import torch

from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample_v2
from model.M1.warning import batched_warning_probability, warning_probability


def _object_scenarios(pipeline, history, *, episode, node, stage, decision_time_utc,
                      observed, count, seed):
    return ancestral_sample_v2(
        pipeline.model,
        history,
        pipeline.contracts,
        episode_id=episode,
        decision_node_id=node,
        stage=stage,
        observed=observed,
        count=count,
        seed=seed,
        target_support={name: "SUPPORTED" for name in ("T_IB_A00", "D_OB", "D_TX")},
        decision_time_utc=decision_time_utc,
        temperatures=pipeline.temperatures,
    )


def test_batched_warning_matches_object_reference_categories_and_probability():
    pipeline = M1Pipeline.smoke(input_size=4)
    pipeline.temperatures = {"T_IB_REMAINING_HAZARD": 1.3, "D_OB": 0.8, "D_TX": 1.1}
    values = torch.tensor([
        [[0.1, 0.2, 0.3, 0.4]],
        [[0.4, 0.3, 0.2, 0.1]],
        [[0.2, 0.1, 0.4, 0.3]],
    ])
    lengths = torch.ones(3, dtype=torch.long)
    with torch.no_grad():
        histories = pipeline.model.encode_history(values, lengths)
    episodes = ("episode-a", "episode-b", "episode-c")
    decision_times = ("2019-01-01T12:00:00+00:00",) * 3
    observed_t_ib = (None, "2019-01-01T12:07:30+00:00", "2019-01-01T12:07:30+00:00")
    observed_d_ob = (None, None, 10.0)
    observed_d_tx = (None, None, None)
    stages = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")
    result = batched_warning_probability(
        pipeline,
        histories,
        episode_ids=episodes,
        stages=stages,
        decision_times_utc=decision_times,
        observed_t_ib=observed_t_ib,
        observed_d_ob=observed_d_ob,
        observed_d_tx=observed_d_tx,
        count=32,
        seed=17,
        return_indices=True,
    )
    assert result.probability.dtype == torch.float64

    hazard = pipeline.contracts["T_IB_REMAINING_HAZARD"]
    d_ob = pipeline.contracts["D_OB"]
    d_tx = pipeline.contracts["D_TX"]
    for index, stage in enumerate(stages):
        observed = {}
        if observed_t_ib[index] is not None:
            observed["T_IB_A00"] = observed_t_ib[index]
        if observed_d_ob[index] is not None:
            observed["D_OB"] = observed_d_ob[index]
        if observed_d_tx[index] is not None:
            observed["D_TX"] = observed_d_tx[index]
        scenarios = _object_scenarios(
            pipeline, histories[index:index + 1],
            episode=episodes[index], node=f"node-{index}", stage=stage,
            decision_time_utc=decision_times[index],
            observed=observed, count=32, seed=17,
        )
        reference = warning_probability(scenarios)
        assert result.probability[index].item() == pytest.approx(reference.probability, abs=0.0)
        for target, attribute, contract in (
            ("T_IB_A00", "r_ib_minutes", hazard),
            ("D_OB", "d_ob_minutes", d_ob),
            ("D_TX", "d_tx_minutes", d_tx),
        ):
            expected = torch.tensor([
                contract.encode(getattr(row, attribute))
                for row in scenarios
            ])
            assert torch.equal(result.sampled_indices[target][index].cpu(), expected)
        assert result.tail_representative_used[index].item() == reference.tail_representative_used


def test_batched_warning_abstains_when_formal_input_is_missing():
    pipeline = M1Pipeline.smoke(input_size=4)
    values = torch.zeros((1, 1, 4))
    with torch.no_grad():
        history = pipeline.model.encode_history(values, torch.ones(1, dtype=torch.long))
    result = batched_warning_probability(
        pipeline,
        history,
        episode_ids=("episode",),
        stages=("PRE_IB",),
        decision_times_utc=(None,),
        observed_t_ib=(None,),
        observed_d_ob=(None,),
        observed_d_tx=(None,),
        count=8,
        seed=7,
    )
    assert not result.support[0]
    assert torch.isnan(result.probability[0])
