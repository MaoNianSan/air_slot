from __future__ import annotations

from datetime import datetime, timezone

from overall_run.src.m1.contracts import M1MarginalDistribution
from overall_run.src.m1.distribution import derive_joint_samples, physical_identity_holds


UTC = timezone.utc


def _distribution(bundle, target: str, value: float) -> M1MarginalDistribution:
    return M1MarginalDistribution(
        episode_id=bundle.episode_id,
        snapshot_id=bundle.snapshot_id,
        snapshot_version=bundle.snapshot_version,
        query_time=bundle.query_time,
        information_cutoff=bundle.information_cutoff,
        pre_manifest_hash=bundle.pre_bundle_identity.pre_manifest_hash,
        m1_contract_id="M1_CHAIN_DYNAMIC_DISTRIBUTION_V1",
        model_version="model-1",
        temperature_version="temperature-1",
        target_name=target,
        target_support_level="OFFICIAL_OPERATIONAL",
        evidence_status={},
        bin_lower_minutes=(value, value + 5.0),
        bin_upper_minutes=(value + 5.0, None),
        probabilities=(1.0, 0.0),
    )


def test_joint_samples_obey_physical_identity_and_nonadditive_delay(input_bundle_factory) -> None:
    bundle = input_bundle_factory()
    distributions = {
        "R_IB": _distribution(bundle, "R_IB", 50.0),
        "R_OB": _distribution(bundle, "R_OB", 0.0),
        "T_TX": _distribution(bundle, "T_TX", 5.0),
    }
    samples = derive_joint_samples(
        bundle,
        distributions,
        sample_count=3,
        base_seed=7,
        successor_sobt=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
        turnaround_floor_minutes=30.0,
        taxi_reference_minutes=15.0,
    )
    assert physical_identity_holds(samples)
    sample = samples[0]
    assert sample.ATOT_successor == sample.AOBT_successor.replace(minute=25)
    assert sample.offblock_delay == 20.0
    assert sample.extra_taxi_delay == 0.0
    assert sample.total_takeoff_delay == 10.0
    assert sample.total_takeoff_delay != sample.offblock_delay + sample.extra_taxi_delay


def test_observed_events_replace_random_variables(input_bundle_factory) -> None:
    bundle = input_bundle_factory()
    distributions = {
        target: _distribution(bundle, target, 5.0)
        for target in ("R_IB", "R_OB", "T_TX")
    }
    observed = {
        "AIBT_MINUS": datetime(2026, 1, 1, 10, 45, tzinfo=UTC),
        "AOBT_PLUS": datetime(2026, 1, 1, 11, 5, tzinfo=UTC),
        "ATOT_PLUS": datetime(2026, 1, 1, 11, 22, tzinfo=UTC),
    }
    sample = derive_joint_samples(
        bundle,
        distributions,
        sample_count=1,
        base_seed=7,
        successor_sobt=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
        turnaround_floor_minutes=30.0,
        taxi_reference_minutes=15.0,
        observed_event_times=observed,
    )[0]
    assert sample.T_predecessor_inblock == observed["AIBT_MINUS"]
    assert sample.AOBT_successor == observed["AOBT_PLUS"]
    assert sample.ATOT_successor == observed["ATOT_PLUS"]
    assert sample.taxi_time == 17.0
