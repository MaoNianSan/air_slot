from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from overall_run.src.m1.contracts import M1MarginalDistribution, SupportedOperationalValue
from overall_run.src.m1.distribution import derive_joint_samples, physical_identity_holds


UTC = timezone.utc


def _distribution(snapshot, target: str, value: float) -> M1MarginalDistribution:
    return M1MarginalDistribution(
        episode_id=snapshot.episode_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_version=snapshot.snapshot_version,
        query_time=snapshot.query_time,
        information_cutoff=snapshot.information_cutoff,
        pre_manifest_hash=snapshot.pre_bundle_identity.pre_manifest_hash,
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


def _observed(value: datetime, event_id: str) -> SupportedOperationalValue:
    return SupportedOperationalValue(
        value, True, "OFFICIAL_OBSERVED", event_id, event_id, value, "event-v1", None
    )


def test_joint_samples_obey_physical_identity(input_bundle_factory) -> None:
    snapshot = input_bundle_factory()
    distributions = {
        "R_IB": _distribution(snapshot, "R_IB", 50.0),
        "R_OB": _distribution(snapshot, "R_OB", 0.0),
        "T_TX": _distribution(snapshot, "T_TX", 5.0),
    }
    samples = derive_joint_samples(snapshot, distributions, sample_count=3, base_seed=7)
    assert physical_identity_holds(samples)
    assert all(sample.r_ib_minutes is not None for sample in samples)
    assert all(sample.earliest_offblock_time is not None for sample in samples)
    assert all(sample.total_takeoff_delay is not None for sample in samples)


def test_observed_events_replace_random_variables(input_bundle_factory) -> None:
    snapshot = input_bundle_factory()
    observed = {
        "ib": datetime(2026, 1, 1, 10, 45, tzinfo=UTC),
        "ob": datetime(2026, 1, 1, 11, 5, tzinfo=UTC),
        "to": datetime(2026, 1, 1, 11, 22, tzinfo=UTC),
    }
    references = replace(
        snapshot.operational_references,
        predecessor_inblock_observed=_observed(observed["ib"], "AIBT_MINUS"),
        successor_offblock_observed=_observed(observed["ob"], "AOBT_PLUS"),
        successor_takeoff_observed=_observed(observed["to"], "ATOT_PLUS"),
    )
    snapshot = replace(snapshot, operational_references=references)
    distributions = {
        target: _distribution(snapshot, target, 5.0)
        for target in ("R_IB", "R_OB", "T_TX")
    }
    sample = derive_joint_samples(snapshot, distributions, sample_count=1, base_seed=7)[0]
    assert sample.T_predecessor_inblock == observed["ib"]
    assert sample.AOBT_successor == observed["ob"]
    assert sample.ATOT_successor == observed["to"]
    assert sample.taxi_time == 17.0
