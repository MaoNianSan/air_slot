from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from overall_run.src.m1.adapter import load_published_bundle
from overall_run.src.m1.contracts import (
    M1JointSample,
    M1ScenarioBundle,
    OperationalReferences,
    SupportedOperationalValue,
)
from overall_run.src.m2 import build_m2_context
from overall_run.tests.m1.conftest import build_published_bundle


UTC = timezone.utc


def _value(value, field, support="OFFICIAL_OPERATIONAL"):
    return SupportedOperationalValue(
        value=value, active=True, support_level=support, source_field=field,
        source_event_id=None, availability_time=None, reference_version="PRE_V2",
        inactive_reason=None,
    )


def _inactive(reason):
    return SupportedOperationalValue(
        value=None, active=False, support_level="UNSUPPORTED", source_field=None,
        source_event_id=None, availability_time=None, reference_version=None,
        inactive_reason=reason,
    )


@pytest.fixture
def m1_scenario_factory():
    def factory(*, tail_status="RESOLVED", overflow=False, sample_count=4):
        query = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        sobt = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
        refs = OperationalReferences(
            successor_sobt=_value(sobt, "successor_sobt"),
            turnaround_floor_minutes=_value(30.0, "turnaround_floor_minutes"),
            taxi_reference_minutes=_value(15.0, "taxi_reference_minutes"),
            predecessor_inblock_observed=_inactive("NOT_OBSERVED"),
            successor_offblock_observed=_inactive("NOT_OBSERVED"),
            successor_takeoff_observed=_inactive("NOT_OBSERVED"),
        )
        samples = []
        for sample_id in range(sample_count):
            sample_overflow = overflow and sample_id == 0
            r_ib = None if sample_overflow else 20.0 + sample_id
            r_ob = 10.0 + sample_id
            inblock = None if r_ib is None else query + timedelta(minutes=r_ib)
            earliest = None if inblock is None else max(sobt, inblock + timedelta(minutes=30))
            offblock = None if earliest is None else earliest + timedelta(minutes=r_ob)
            taxi = None if offblock is None else 20.0 + sample_id
            takeoff = None if offblock is None else offblock + timedelta(minutes=taxi)
            samples.append(M1JointSample(
                episode_id="ep-1", snapshot_id="snap-1", snapshot_version=1,
                sample_id=sample_id, query_time=query, information_cutoff=query,
                pre_manifest_hash="a" * 64, m1_contract_id="M1_CHAIN_DYNAMIC_DISTRIBUTION_V1",
                m1_model_version="model-v1", temperature_version="temp-v1",
                target_support_level={"R_IB": "OFFICIAL_OPERATIONAL", "R_OB": "OFFICIAL_OPERATIONAL", "T_TX": "OFFICIAL_OPERATIONAL"},
                r_ib_minutes=r_ib, r_ob_minutes=r_ob, earliest_offblock_time=earliest,
                T_predecessor_inblock=inblock, AOBT_successor=offblock,
                ATOT_successor=takeoff, taxi_time=taxi,
                offblock_delay=None if offblock is None else max((offblock - sobt).total_seconds() / 60.0, 0.0),
                extra_taxi_delay=None if taxi is None else taxi - 15.0,
                total_takeoff_delay=None if takeoff is None else max((takeoff - (sobt + timedelta(minutes=15))).total_seconds() / 60.0, 0.0),
                overflow_flags={"R_IB": sample_overflow, "R_OB": False, "T_TX": False},
                observed_event_mask={}, evidence_status={}, fallback_status={},
            ))
        return M1ScenarioBundle(
            metadata={
                "episode_id": "ep-1", "snapshot_id": "snap-1", "snapshot_version": 1,
                "query_time": query, "information_cutoff": query,
                "pre_bundle_id": "a" * 64, "m1_bundle_id": "snap-1",
                "model_version": "model-v1", "temperature_version": "temp-v1",
            },
            operational_references=refs,
            marginal_distributions={},
            sampling_metadata={
                "sample_count": sample_count, "sampling_version": "M1_SAMPLING_V2",
                "base_seed": 17, "dependence_mode": "CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING",
                "bin_representative_mode": "FIXED_WITHIN_BIN_UNIFORM",
                "overflow_mode": "TRAINING_EMPIRICAL_TAIL",
                "tail_resolution_status": tail_status,
            },
            joint_samples=tuple(samples),
            pre_context={
                "flight": {
                    "turnaround_reference_type": "OFFICIAL_FLOOR",
                    "continuity_exposure": 1.0, "downstream_leg_count": 1,
                    "execution_window_margin": 1.0,
                    "evidence_status": "OFFICIAL_OPERATIONAL",
                },
            },
        )
    return factory


@pytest.fixture
def m2_pre_bundle(tmp_path):
    return load_published_bundle(build_published_bundle(tmp_path))


@pytest.fixture
def m2_scenario_context_factory(m1_scenario_factory, m2_pre_bundle):
    def factory(**kwargs):
        scenario = m1_scenario_factory(**kwargs)
        metadata = dict(scenario.metadata)
        metadata["pre_bundle_id"] = m2_pre_bundle.identity.pre_manifest_hash
        scenario = replace(scenario, metadata=metadata, pre_context={})
        return scenario, build_m2_context(m2_pre_bundle, scenario)

    return factory
