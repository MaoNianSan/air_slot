from __future__ import annotations

from datetime import timedelta

import pytest

from overall_run.src.m1.contracts import M1ContractError, M1MarginalDistribution


def test_information_cutoff_cannot_exceed_query(input_bundle_factory) -> None:
    base = input_bundle_factory()
    with pytest.raises(M1ContractError, match="M1_INFORMATION_CUTOFF_AFTER_QUERY_TIME"):
        input_bundle_factory(information_cutoff=base.query_time + timedelta(seconds=1))


def test_distribution_probability_contract(input_bundle_factory) -> None:
    bundle = input_bundle_factory()
    with pytest.raises(M1ContractError, match="M1_PROBABILITY_SUM_INVALID"):
        M1MarginalDistribution(
            episode_id=bundle.episode_id,
            snapshot_id=bundle.snapshot_id,
            snapshot_version=1,
            query_time=bundle.query_time,
            information_cutoff=bundle.information_cutoff,
            pre_manifest_hash=bundle.pre_bundle_identity.pre_manifest_hash,
            m1_contract_id="M1_CHAIN_DYNAMIC_DISTRIBUTION_V1",
            model_version="model",
            temperature_version="temperature",
            target_name="R_IB",
            target_support_level="OFFICIAL_OPERATIONAL",
            evidence_status={},
            bin_lower_minutes=(0.0, 5.0),
            bin_upper_minutes=(5.0, None),
            probabilities=(0.3, 0.3),
        )
