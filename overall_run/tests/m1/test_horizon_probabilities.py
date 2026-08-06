from __future__ import annotations

from overall_run.src.m1.distribution import (
    derive_horizon_probabilities,
    derive_joint_samples,
)

from .test_derived_outputs import _distribution


def test_horizon_probabilities_are_bounded_and_monotone(input_bundle_factory) -> None:
    snapshot = input_bundle_factory()
    distributions = {
        "R_IB": _distribution(snapshot, "R_IB", 5.0),
        "R_OB": _distribution(snapshot, "R_OB", 5.0),
        "T_TX": _distribution(snapshot, "T_TX", 5.0),
    }
    samples = derive_joint_samples(snapshot, distributions, sample_count=32, base_seed=9)
    result = derive_horizon_probabilities(
        samples,
        snapshot.query_time,
        (0, 30, 60, 120, 180),
    )
    for channel in (
        result.predecessor_inblock,
        result.successor_offblock,
        result.successor_takeoff,
    ):
        values = list(channel.values())
        assert all(0.0 <= value <= 1.0 for value in values)
        assert values == sorted(values)
