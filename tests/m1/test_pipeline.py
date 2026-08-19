"""M1 V2 pipeline closure: save/load, seed stability, and abstention rules."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import torch

from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample_v2
from model.common.errors import ContractError
from model.PRE.foundation import PREBuildRequest, build_pre_state


def _pre(dataset: str):
    return build_pre_state(PREBuildRequest(
        episode_id="episode-z", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=timezone.utc),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=timezone.utc),
        config_hash="sha256:c", registry_hash="sha256:r",
        dataset_instance_id=dataset,
    )).pre_state


def test_save_load_and_stable_stage_aware_scenarios(tmp_path: Path):
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.zeros(1, 3, 4)
    lengths = torch.tensor([3])
    dist = pipe.predict_distributions(values, lengths)
    scenarios1 = pipe.sample_from_pre(
        _pre("data2_2019"), values, lengths, observed={}, count=8, seed=7)
    later = _pre("data2_2019").model_copy(update={"decision_node":
        _pre("data2_2019").decision_node.model_copy(update={"decision_node_id": "later"})})
    scenarios2 = pipe.sample_from_pre(later, values, lengths, observed={}, count=8, seed=7)
    assert [x.scenario_seed_key for x in scenarios1] == [x.scenario_seed_key for x in scenarios2]
    path = tmp_path / "m1.pt"
    pipe.save(path)
    loaded = M1Pipeline.load(path)
    assert torch.allclose(
        pipe.predict_distributions(values, lengths)["T_IB_A00"],
        loaded.predict_distributions(values, lengths)["T_IB_A00"])


def test_abstained_target_is_not_sampled_and_stage_requires_observed_events():
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    # data1 suppresses the formal D_OB parent; D_TX inherits the abstention.
    rows = pipe.sample_from_pre(
        _pre("data1_2019"), values, lengths, observed={}, count=2, seed=7)
    assert all(row.d_ob_minutes is None and row.d_ob_support == "ABSTAIN" for row in rows)
    assert all(row.d_tx_minutes is None and row.d_tx_support == "ABSTAIN" for row in rows)
    with pytest.raises(ContractError, match="M1_STAGE_OBSERVATION_MISSING"):
        ancestral_sample_v2(
            pipe.model, pipe.model.encode_history(values, lengths), pipe.contracts,
            episode_id="e", decision_node_id="n", stage="POST_OB_PRE_TO",
            observed={"T_IB_A00": "2019-01-01T12:05:00+00:00"},
            count=2, seed=7,
            target_support={name: "SUPPORTED" for name in ("T_IB_A00", "D_OB", "D_TX")},
            decision_time_utc="2019-01-01T12:00:00+00:00",
        )
