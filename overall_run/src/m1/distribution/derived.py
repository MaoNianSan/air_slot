from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping

import numpy as np

from ..contracts import M1InputBundle, M1JointSample, M1MarginalDistribution
from .bins import DiscreteBins
from .sampling import fixed_uniform, sample_discrete


def _draw(
    distribution: M1MarginalDistribution,
    sample_id: int,
    base_seed: int,
) -> tuple[float, bool]:
    bins = DiscreteBins(distribution.bin_lower_minutes, distribution.bin_upper_minutes)
    uniform = fixed_uniform(
        distribution.episode_id,
        sample_id,
        distribution.target_name,
        base_seed,
    )
    return sample_discrete(np.asarray(distribution.probabilities), bins, uniform)


def derive_joint_samples(
    input_bundle: M1InputBundle,
    distributions: Mapping[str, M1MarginalDistribution],
    *,
    sample_count: int,
    base_seed: int,
    successor_sobt: datetime | None,
    turnaround_floor_minutes: float | None,
    taxi_reference_minutes: float | None,
    observed_event_times: Mapping[str, datetime] | None = None,
) -> tuple[M1JointSample, ...]:
    observed = dict(observed_event_times or {})
    samples: list[M1JointSample] = []
    for sample_id in range(sample_count):
        values: dict[str, float] = {}
        overflow: dict[str, bool] = {}
        for target in ("R_IB", "R_OB", "T_TX"):
            if target in distributions:
                values[target], overflow[target] = _draw(distributions[target], sample_id, base_seed)
            else:
                values[target], overflow[target] = 0.0, False
        inblock = observed.get("AIBT_MINUS")
        if inblock is None and input_bundle.target_contracts["R_IB"].active:
            inblock = input_bundle.query_time + timedelta(minutes=values["R_IB"])
        earliest = None
        if inblock is not None and successor_sobt is not None and turnaround_floor_minutes is not None:
            earliest = max(
                successor_sobt,
                inblock + timedelta(minutes=float(turnaround_floor_minutes)),
            )
        offblock = observed.get("AOBT_PLUS")
        if offblock is None and earliest is not None and input_bundle.target_contracts["R_OB"].active:
            offblock = earliest + timedelta(minutes=values["R_OB"])
        takeoff = observed.get("ATOT_PLUS")
        taxi = None
        if takeoff is not None and offblock is not None:
            taxi = max((takeoff - offblock).total_seconds() / 60.0, 0.0)
        elif offblock is not None and input_bundle.target_contracts["T_TX"].active:
            taxi = values["T_TX"]
            takeoff = offblock + timedelta(minutes=taxi)
        offblock_delay = None
        total_delay = None
        extra_taxi = None
        if successor_sobt is not None and offblock is not None:
            offblock_delay = max((offblock - successor_sobt).total_seconds() / 60.0, 0.0)
        if taxi is not None and taxi_reference_minutes is not None:
            extra_taxi = max(taxi - taxi_reference_minutes, 0.0)
        if takeoff is not None and successor_sobt is not None and taxi_reference_minutes is not None:
            reference_takeoff = successor_sobt + timedelta(minutes=taxi_reference_minutes)
            total_delay = max((takeoff - reference_takeoff).total_seconds() / 60.0, 0.0)
        samples.append(
            M1JointSample(
                episode_id=input_bundle.episode_id,
                snapshot_id=input_bundle.snapshot_id,
                snapshot_version=input_bundle.snapshot_version,
                sample_id=sample_id,
                query_time=input_bundle.query_time,
                information_cutoff=input_bundle.information_cutoff,
                pre_manifest_hash=input_bundle.pre_bundle_identity.pre_manifest_hash,
                m1_contract_id=next(iter(distributions.values())).m1_contract_id if distributions else "",
                m1_model_version=next(iter(distributions.values())).model_version if distributions else "",
                temperature_version=next(iter(distributions.values())).temperature_version if distributions else "",
                target_support_level={
                    name: contract.m1_support_level
                    for name, contract in input_bundle.target_contracts.items()
                },
                T_predecessor_inblock=inblock,
                AOBT_successor=offblock,
                ATOT_successor=takeoff,
                taxi_time=taxi,
                offblock_delay=offblock_delay,
                extra_taxi_delay=extra_taxi,
                total_takeoff_delay=total_delay,
                overflow_flags=overflow,
                observed_event_mask=input_bundle.observed_event_mask,
                evidence_status=input_bundle.evidence_status,
                fallback_status=input_bundle.fallback_status,
            )
        )
    return tuple(samples)


def physical_identity_holds(samples: tuple[M1JointSample, ...], tolerance: float = 1e-9) -> bool:
    for sample in samples:
        if sample.AOBT_successor is None or sample.ATOT_successor is None:
            continue
        if sample.taxi_time is None:
            return False
        delta = (
            sample.ATOT_successor - sample.AOBT_successor
        ).total_seconds() / 60.0
        if abs(delta - sample.taxi_time) > tolerance:
            return False
    return True
