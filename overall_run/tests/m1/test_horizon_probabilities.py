from __future__ import annotations

from dataclasses import replace

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
        estimates = list(channel.values())
        values = [estimate.formal_probability for estimate in estimates]
        assert all(estimate.formal_probability_available for estimate in estimates)
        assert all(value is not None and 0.0 <= value <= 1.0 for value in values)
        assert values == sorted(values)


def test_horizon_probabilities_bound_unresolved_mass(input_bundle_factory) -> None:
    snapshot = input_bundle_factory()
    distributions = {
        "R_IB": _distribution(snapshot, "R_IB", 5.0),
        "R_OB": _distribution(snapshot, "R_OB", 5.0),
        "T_TX": _distribution(snapshot, "T_TX", 5.0),
    }
    samples = list(
        derive_joint_samples(snapshot, distributions, sample_count=4, base_seed=9)
    )
    samples[0] = replace(samples[0], T_predecessor_inblock=None)
    result = derive_horizon_probabilities(
        tuple(samples), snapshot.query_time, (30,)
    ).predecessor_inblock[30]
    assert result.unresolved_probability_mass == 0.25
    assert result.formal_probability_available is False
    assert result.formal_probability is None
    assert result.probability_upper_bound - result.probability_lower_bound == 0.25
