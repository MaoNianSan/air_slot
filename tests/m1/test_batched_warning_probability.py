import pytest
import torch

from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample
from model.M1.warning import batched_warning_probability, warning_probability


def test_batched_warning_matches_object_reference_categories_and_probability():
    pipeline = M1Pipeline.smoke(input_size=4)
    pipeline.temperatures = {"R_IB": 1.3, "DELTA_OB": 0.8, "T_TX": 1.1}
    values = torch.tensor([
        [[0.1, 0.2, 0.3, 0.4]],
        [[0.4, 0.3, 0.2, 0.1]],
        [[0.2, 0.1, 0.4, 0.3]],
    ])
    lengths = torch.ones(3, dtype=torch.long)
    with torch.no_grad():
        histories = pipeline.model.encode_history(values, lengths)
    episodes = ("episode-a", "episode-b", "episode-c")
    observed_r_ib = (None, 0.0, 0.0)
    observed_delta = (None, None, 10.0)
    observed_tx = (None, None, None)
    result = batched_warning_probability(
        pipeline,
        histories,
        episode_ids=episodes,
        observed_r_ib=observed_r_ib,
        observed_delta_ob=observed_delta,
        observed_t_tx=observed_tx,
        taxi_reference_minutes=(12.0, 12.0, 12.0),
        count=32,
        seed=17,
        return_indices=True,
    )
    assert result.probability.dtype == torch.float64

    stages = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")
    for index, stage in enumerate(stages):
        observed = {}
        if observed_r_ib[index] is not None:
            observed["R_IB"] = observed_r_ib[index]
        if observed_delta[index] is not None:
            observed["DELTA_OB"] = observed_delta[index]
        if observed_tx[index] is not None:
            observed["T_TX"] = observed_tx[index]
        scenarios = ancestral_sample(
            pipeline.model,
            histories[index:index + 1],
            pipeline.bins,
            episode_id=episodes[index],
            decision_node_id=f"node-{index}",
            stage=stage,
            observed=observed,
            count=32,
            seed=17,
            target_support={name: "SUPPORTED" for name in pipeline.bins},
            tx_reference_minutes=12.0,
            taxi_reference_id="reference",
            taxi_reference_hash="freeze",
            taxi_reference_support_state="SUPPORTED",
            temperatures=pipeline.temperatures,
        )
        reference = warning_probability(scenarios)
        assert result.probability[index].item() == pytest.approx(reference.probability, abs=0.0)
        for target, attribute in (
            ("R_IB", "r_ib_minutes"),
            ("DELTA_OB", "delta_ob_minutes"),
            ("T_TX", "t_tx_minutes"),
        ):
            expected = torch.tensor([
                pipeline.bins[target].encode(getattr(row, attribute))
                for row in scenarios
            ])
            assert torch.equal(result.sampled_indices[target][index].cpu(), expected)
        assert result.tail_representative_used[index].item() == reference.tail_representative_used


def test_batched_warning_abstains_when_reference_is_missing():
    pipeline = M1Pipeline.smoke(input_size=4)
    values = torch.zeros((1, 1, 4))
    with torch.no_grad():
        history = pipeline.model.encode_history(values, torch.ones(1, dtype=torch.long))
    result = batched_warning_probability(
        pipeline,
        history,
        episode_ids=("episode",),
        observed_r_ib=(None,),
        observed_delta_ob=(None,),
        observed_t_tx=(None,),
        taxi_reference_minutes=(None,),
        count=8,
        seed=7,
    )
    assert not result.support[0]
    assert torch.isnan(result.probability[0])
