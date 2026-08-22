"""Formal V2 episode-balanced objective invariance checks."""

from datetime import date

import pytest
import torch

from model.M1.contracts import HazardBinContract, HurdleQuantileContract
from model.M1.data import episode_normalized_weights, fast_features_from_sequence
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.loss import hazard_interval_nll, hurdle_quantile_loss
from model.M1.pipeline import M1Pipeline


LEVELS = (0.1, 0.3, 0.5, 0.7, 0.9)


def _hazard_loss(node_count: int) -> torch.Tensor:
    contract = HazardBinContract(
        target_name="T_IB_REMAINING_HAZARD", bin_width_minutes=5,
        max_finite_minutes=20,
    )
    logits = torch.zeros(node_count, contract.finite_class_count)
    weights = episode_normalized_weights(["episode"] * node_count)
    return hazard_interval_nll(
        logits, contract,
        lower=torch.full((node_count,), 5.0),
        upper=torch.full((node_count,), 5.0),
        active=torch.ones(node_count, dtype=torch.bool),
        weights=weights,
        denominator=1,
    )


def _hurdle_loss(target: str, node_count: int, *, positive: bool) -> torch.Tensor:
    contract = HurdleQuantileContract(
        target_name=target, bin_width_minutes=5, max_finite_minutes=20,
        quantile_levels=LEVELS,
    )
    weights = episode_normalized_weights(["episode"] * node_count)
    zero = torch.full((node_count,), not positive, dtype=torch.bool)
    value = torch.full((node_count,), 10.0 if positive else 0.0)
    return hurdle_quantile_loss(
        torch.zeros(node_count, 1), torch.zeros(node_count, len(LEVELS)), contract,
        zero=zero, value=value,
        active=torch.ones(node_count, dtype=torch.bool),
        zero_weights=weights if not positive else None,
        positive_weights=weights if positive else None,
        zero_denominator=1 if not positive else 0,
        positive_denominator=1 if positive else 0,
    )


def test_target_specific_episode_weights_sum_to_one_for_each_component():
    rows = [
        M1TrainingExample(
            episode_id="one", episode_date=date(2019, 6, 1),
            values=torch.zeros(1, 4),
            targets={"T_IB_REMAINING_HAZARD": 5.0, "D_OB": 0.0, "D_TX": 2.0},
            active={"T_IB_REMAINING_HAZARD": True, "D_OB": True, "D_TX": True},
        ),
        *[
            M1TrainingExample(
                episode_id="ten", episode_date=date(2019, 6, 2),
                values=torch.zeros(1, 4),
                targets={"T_IB_REMAINING_HAZARD": 5.0, "D_OB": 10.0, "D_TX": 0.0},
                active={"T_IB_REMAINING_HAZARD": True, "D_OB": True, "D_TX": True},
            )
            for _ in range(10)
        ],
    ]
    spec = M1Lifecycle._episode_balanced_loss_spec(rows)
    for name, weights in spec["weights"].items():
        for episode in ("one", "ten"):
            indices = [index for index, row in enumerate(rows) if row.episode_id == episode]
            eligible = float(weights[indices].sum())
            if name == "ob_positive":
                expected = 1.0 if episode == "ten" else 0.0
            elif name == "tx_positive":
                expected = 1.0 if episode == "one" else 0.0
            else:
                expected = 1.0
            assert eligible == pytest.approx(expected)
    assert spec["denominators"] == {
        "ib": 2, "ob_zero": 2, "ob_positive": 1,
        "tx_zero": 2, "tx_positive": 1,
    }


@pytest.mark.parametrize("component", ("hazard", "d_ob_zero", "d_ob_positive",
                                        "d_tx_zero", "d_tx_positive"))
def test_one_node_and_ten_identical_nodes_have_equal_component_contribution(component):
    if component == "hazard":
        one, ten = _hazard_loss(1), _hazard_loss(10)
    elif component == "d_ob_zero":
        one, ten = _hurdle_loss("D_OB", 1, positive=False), _hurdle_loss("D_OB", 10, positive=False)
    elif component == "d_ob_positive":
        one, ten = _hurdle_loss("D_OB", 1, positive=True), _hurdle_loss("D_OB", 10, positive=True)
    elif component == "d_tx_zero":
        one, ten = _hurdle_loss("D_TX", 1, positive=False), _hurdle_loss("D_TX", 10, positive=False)
    else:
        one, ten = _hurdle_loss("D_TX", 1, positive=True), _hurdle_loss("D_TX", 10, positive=True)
    assert ten == pytest.approx(one.item(), rel=1e-6, abs=1e-7)


def _example(episode: str, offset: float) -> M1TrainingExample:
    return M1TrainingExample(
        episode_id=episode,
        episode_date=date(2019, 6, 1),
        values=torch.full((3, 4), offset),
        targets={
            "T_IB_REMAINING_HAZARD": 5.0,
            "D_OB": 0.0 if int(offset) % 2 == 0 else 10.0,
            "D_TX": 0.0 if int(offset) % 3 == 0 else 5.0,
        },
        active={
            "T_IB_REMAINING_HAZARD": True,
            "D_OB": True,
            "D_TX": True,
        },
    )


def _objective_and_gradients(lifecycle: M1Lifecycle, examples, batch_size):
    lifecycle.pipeline.model.zero_grad(set_to_none=True)
    spec = lifecycle._episode_balanced_loss_spec(examples)
    total = torch.zeros(())
    for indices in lifecycle._batch_indices(examples, batch_size, bucketed=False):
        batch = [examples[index] for index in indices]
        values, lengths, encoded, static_values = lifecycle._batch(
            batch, lifecycle.pipeline.contracts, device=lifecycle.device,
        )
        teacher = {
            "T_IB_REMAINING_HAZARD": encoded["ib_bin"],
            "D_OB": encoded["d_ob_bin"],
            "D_TX": encoded["d_tx_bin"],
            "_active": {
                "T_IB_REMAINING_HAZARD": encoded["ib_bin"] >= 0,
                "D_OB": encoded["d_ob_bin"] >= 0,
                "D_TX": encoded["d_tx_bin"] >= 0,
            },
        }
        logits = lifecycle.pipeline.model(
            values, lengths, teacher=teacher,
            fast_features=fast_features_from_sequence(values, lengths),
            static_features=static_values,
        )
        batch_indices = torch.tensor(indices, dtype=torch.long)
        batch_weights = {
            name: component[batch_indices].to(lifecycle.device)
            for name, component in spec["weights"].items()
        }
        total = total + lifecycle._loss(
            logits, encoded, lifecycle.pipeline.contracts,
            spec["denominators"], batch_weights,
        )
    total.backward()
    gradients = {
        name: parameter.grad.detach().clone()
        for name, parameter in lifecycle.pipeline.model.named_parameters()
        if parameter.grad is not None
    }
    return total.detach(), gradients


def test_episode_balanced_full_batch_and_microbatch_have_equal_loss_and_gradients():
    examples = tuple(
        [_example("one", 0.0)]
        + [_example("ten", float(index + 1)) for index in range(10)]
        + [_example("other", 20.0)]
    )
    full = M1Pipeline.smoke(4)
    micro = M1Pipeline.smoke(4)
    state = {name: value.clone() for name, value in full.model.state_dict().items()}
    micro.model.load_state_dict(state)
    full_loss, full_gradients = _objective_and_gradients(M1Lifecycle(full), examples, None)
    micro_loss, micro_gradients = _objective_and_gradients(M1Lifecycle(micro), examples, 3)
    assert micro_loss == pytest.approx(full_loss.item(), rel=1e-6, abs=1e-6)
    assert full_gradients.keys() == micro_gradients.keys()
    for name in full_gradients:
        assert torch.allclose(full_gradients[name], micro_gradients[name], rtol=1e-5, atol=1e-6)


def test_development_objective_reports_joint_and_primitive_microbatch_invariance():
    examples = tuple(
        [_example("one", 0.0)]
        + [_example("ten", float(index + 1)) for index in range(10)]
        + [_example("other", 20.0)]
    )
    lifecycle = M1Lifecycle(M1Pipeline.smoke(4))
    full = lifecycle.episode_balanced_objective(
        examples, batch_size=None, bucketed=False,
    )
    micro = lifecycle.episode_balanced_objective(
        examples, batch_size=3, bucketed=False,
    )
    primitive_names = (
        "T_IB_HAZARD_NLL", "D_OB_ZERO_BCE", "D_OB_POSITIVE_PINBALL",
        "D_TX_ZERO_BCE", "D_TX_POSITIVE_PINBALL",
    )
    for name in primitive_names:
        assert micro[name] == pytest.approx(full[name], rel=1e-6, abs=1e-6)
    assert full["EPISODE_BALANCED_JOINT_VALIDATION_LOSS"] == pytest.approx(
        sum(full[name] for name in primitive_names), rel=1e-7,
    )
    assert micro["EPISODE_BALANCED_JOINT_VALIDATION_LOSS"] == pytest.approx(
        full["EPISODE_BALANCED_JOINT_VALIDATION_LOSS"], rel=1e-6, abs=1e-6,
    )
