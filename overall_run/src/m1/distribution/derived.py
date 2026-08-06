from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping

import numpy as np

from ..contracts import (
    EventProbabilityBounds,
    EventHorizonProbabilities,
    M1JointSample,
    M1MarginalDistribution,
    M1SnapshotNode,
    SupportedOperationalValue,
)
from .bins import DiscreteBins
from .sampling import fixed_uniform, sample_discrete
from .tail import EmpiricalTailArtifact


def _draw(
    distribution: M1MarginalDistribution,
    sample_id: int,
    base_seed: int,
    tail_artifact: EmpiricalTailArtifact | None,
) -> tuple[float | None, bool]:
    bins = DiscreteBins(
        distribution.bin_lower_minutes,
        distribution.bin_upper_minutes,
    )
    uniform = fixed_uniform(
        distribution.episode_id,
        sample_id,
        distribution.target_name,
        base_seed,
    )
    value, overflow = sample_discrete(
        np.asarray(distribution.probabilities),
        bins,
        uniform,
        episode_id=distribution.episode_id,
        sample_id=sample_id,
        target_name=distribution.target_name,
        base_seed=base_seed,
        overflow_tail_values=(
            tail_artifact.resolved_values if tail_artifact is not None else ()
        ),
    )
    return (None if not np.isfinite(value) else float(value)), overflow


def _datetime(reference: SupportedOperationalValue) -> datetime | None:
    value = reference.value
    return value if reference.active and isinstance(value, datetime) else None


def _number(reference: SupportedOperationalValue) -> float | None:
    if not reference.active or reference.value is None:
        return None
    return float(reference.value)


def derive_joint_samples(
    snapshot: M1SnapshotNode,
    distributions: Mapping[str, M1MarginalDistribution],
    *,
    sample_count: int,
    base_seed: int,
    tail_artifacts: Mapping[str, EmpiricalTailArtifact] | None = None,
) -> tuple[M1JointSample, ...]:
    references = snapshot.operational_references
    successor_sobt = _datetime(references.successor_sobt)
    turnaround_floor = _number(references.turnaround_floor_minutes)
    taxi_reference = _number(references.taxi_reference_minutes)
    samples: list[M1JointSample] = []
    for sample_id in range(sample_count):
        values: dict[str, float | None] = {}
        overflow: dict[str, bool] = {}
        for target in ("R_IB", "R_OB", "T_TX"):
            if target in distributions:
                values[target], overflow[target] = _draw(
                    distributions[target],
                    sample_id,
                    base_seed,
                    (tail_artifacts or {}).get(target),
                )
            else:
                values[target], overflow[target] = None, False
        inblock = _datetime(references.predecessor_inblock_observed)
        if inblock is None and values["R_IB"] is not None:
            inblock = snapshot.query_time + timedelta(minutes=float(values["R_IB"]))
        earliest = None
        if inblock is not None and successor_sobt is not None and turnaround_floor is not None:
            earliest = max(
                successor_sobt,
                inblock + timedelta(minutes=turnaround_floor),
            )
        offblock = _datetime(references.successor_offblock_observed)
        if offblock is None and earliest is not None and values["R_OB"] is not None:
            offblock = earliest + timedelta(minutes=float(values["R_OB"]))
        takeoff = _datetime(references.successor_takeoff_observed)
        taxi = None
        if takeoff is not None and offblock is not None:
            taxi = max((takeoff - offblock).total_seconds() / 60.0, 0.0)
        elif offblock is not None and values["T_TX"] is not None:
            taxi = float(values["T_TX"])
            takeoff = offblock + timedelta(minutes=taxi)
        offblock_delay = None
        extra_taxi = None
        total_delay = None
        if successor_sobt is not None and offblock is not None:
            offblock_delay = max(
                (offblock - successor_sobt).total_seconds() / 60.0,
                0.0,
            )
        if taxi is not None and taxi_reference is not None:
            extra_taxi = max(taxi - taxi_reference, 0.0)
        if takeoff is not None and successor_sobt is not None and taxi_reference is not None:
            total_delay = max(
                (
                    takeoff
                    - (successor_sobt + timedelta(minutes=taxi_reference))
                ).total_seconds()
                / 60.0,
                0.0,
            )
        first_distribution = next(iter(distributions.values()), None)
        samples.append(
            M1JointSample(
                episode_id=snapshot.episode_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_version=snapshot.snapshot_version,
                sample_id=sample_id,
                query_time=snapshot.query_time,
                information_cutoff=snapshot.information_cutoff,
                pre_manifest_hash=snapshot.pre_bundle_identity.pre_manifest_hash,
                m1_contract_id=(
                    first_distribution.m1_contract_id if first_distribution else ""
                ),
                m1_model_version=(
                    first_distribution.model_version if first_distribution else ""
                ),
                temperature_version=(
                    first_distribution.temperature_version if first_distribution else ""
                ),
                target_support_level={
                    name: contract.m1_support_level
                    for name, contract in snapshot.target_contracts.items()
                },
                r_ib_minutes=values["R_IB"],
                r_ob_minutes=values["R_OB"],
                earliest_offblock_time=earliest,
                T_predecessor_inblock=inblock,
                AOBT_successor=offblock,
                ATOT_successor=takeoff,
                taxi_time=taxi,
                offblock_delay=offblock_delay,
                extra_taxi_delay=extra_taxi,
                total_takeoff_delay=total_delay,
                overflow_flags=overflow,
                observed_event_mask=snapshot.observed_event_mask,
                evidence_status=snapshot.evidence_status,
                fallback_status=snapshot.fallback_status,
            )
        )
    return tuple(samples)


def derive_horizon_probabilities(
    samples: tuple[M1JointSample, ...],
    query_time: datetime,
    horizons_minutes: tuple[int, ...],
) -> EventHorizonProbabilities:
    if not samples:
        raise ValueError("M1_HORIZON_SAMPLES_EMPTY")

    def probabilities(field: str) -> dict[int, EventProbabilityBounds]:
        result: dict[int, EventProbabilityBounds] = {}
        total = len(samples)
        for horizon in horizons_minutes:
            deadline = query_time + timedelta(minutes=int(horizon))
            resolved_values = [
                getattr(sample, field)
                for sample in samples
                if getattr(sample, field) is not None
            ]
            resolved_event_count = sum(value <= deadline for value in resolved_values)
            unresolved_count = total - len(resolved_values)
            lower = resolved_event_count / total
            upper = (resolved_event_count + unresolved_count) / total
            formal_available = unresolved_count == 0
            result[int(horizon)] = EventProbabilityBounds(
                resolved_probability=(
                    resolved_event_count / len(resolved_values)
                    if resolved_values
                    else None
                ),
                unresolved_probability_mass=unresolved_count / total,
                probability_lower_bound=lower,
                probability_upper_bound=upper,
                formal_probability_available=formal_available,
                formal_probability=lower if formal_available else None,
            )
        return result

    return EventHorizonProbabilities(
        horizons_minutes=horizons_minutes,
        predecessor_inblock=probabilities("T_predecessor_inblock"),
        successor_offblock=probabilities("AOBT_successor"),
        successor_takeoff=probabilities("ATOT_successor"),
    )


def physical_identity_holds(
    samples: tuple[M1JointSample, ...],
    tolerance: float = 1e-6,
) -> bool:
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
