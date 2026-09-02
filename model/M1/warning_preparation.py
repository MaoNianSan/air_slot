"""Compact M1 feature rows for Development warning inference.

The regular PRE publisher intentionally returns typed ``PREState`` objects for
audits and bounded cohorts.  Full Development keeps the same field semantics
but retains only the M1 feature row and the small set of evaluation metadata
needed by model-level warning evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import cos, radians, sin
from typing import Iterable

import torch

from model.M1.data import (
    EVIDENCE_LEVELS,
    FEATURE_NAMES,
    MOTION_FIELDS,
    NORMALIZED_NAMES,
    STAGE_LEVELS,
    SUPPORT_LEVELS,
    WEATHER_FIELDS,
)
from model.PRE.episode.node_builder import stage_at
from model.PRE.episode.containment import episode_node_count
from model.PRE.streaming.data2 import latest_weather
from model.common.enums import EvidenceClass, OperationalStage, SupportState
from model.common.identity import content_id


@dataclass(frozen=True)
class CompactWarningEpisode:
    episode_id: str
    episode_date: str
    decision_times: tuple[datetime, ...]
    decision_node_ids: tuple[str, ...]
    features: torch.Tensor
    stages: tuple[str, ...]
    observed_r_ib: tuple[float | None, ...]
    observed_delta_ob: tuple[float | None, ...]
    observed_t_tx: tuple[float | None, ...]
    lead_times_minutes: tuple[float, ...]
    realized_d_to_minutes: float | None
    realized_event_positive: bool | None
    taxi_reference_minutes: float | None
    taxi_reference_id: str | None
    taxi_reference_hash: str | None
    taxi_reference_supported: bool


def _scaled(normalization, name: str, value: float | None) -> float:
    if value is None:
        return 0.0
    return float(normalization.normalize(name, float(value)))


def _one_hot(levels: tuple[str, ...], value: str) -> list[float]:
    return [float(value == level) for level in levels]


def _canonical_node_id(
    *,
    episode_id: str,
    decision_time: datetime,
    config_hash: str,
    registry_hash: str,
    legal_record_ids: Iterable[str],
) -> str:
    return content_id(
        {
            "episode_id": episode_id,
            "decision_time": decision_time,
            "information_cutoff": decision_time,
            "config_hash": config_hash,
            "registry_hash": registry_hash,
            "legal_record_ids": sorted(legal_record_ids),
        }
    )


def _weather_fields(observation) -> dict[str, float | None]:
    if observation is None:
        return {name: None for name in WEATHER_FIELDS}
    return {
        "temperature_c": observation.temperature_c,
        "dewpoint_c": observation.dewpoint_c,
        "wind_direction_deg": observation.wind_direction_deg,
        "wind_speed_mps": observation.wind_speed_mps,
        "wind_gust_mps": observation.wind_gust_mps,
        "qnh_hpa": observation.qnh_hpa,
        "visibility_m": observation.visibility_m,
    }


def _value(item, name: str):
    return getattr(item, name) if hasattr(item, name) else item.get(name)


def _feature_row(
    *,
    decision_time: datetime,
    previous_time: datetime | None,
    stage: str,
    schedule,
    observation,
    normalization,
) -> list[float]:
    row: list[float] = []
    motion_values = {name: None for name in MOTION_FIELDS}
    weather_values = _weather_fields(observation)

    for prefix, fields, values in (
        ("motion", MOTION_FIELDS, motion_values),
        ("weather", WEATHER_FIELDS, weather_values),
    ):
        for field in fields:
            raw = values[field]
            if field in {"heading_deg", "wind_direction_deg"}:
                angle = radians(float(raw)) if raw is not None else 0.0
                row.extend(
                    (
                        sin(angle) if raw is not None else 0.0,
                        cos(angle) if raw is not None else 0.0,
                    )
                )
            elif field == "on_ground":
                row.append(float(bool(raw)) if raw is not None else 0.0)
            else:
                row.append(_scaled(normalization, f"{prefix}.{field}", raw))

    scheduled = schedule["scheduled_departure_utc"]
    schedule_minutes = (scheduled - decision_time).total_seconds() / 60.0
    row.append(
        _scaled(
            normalization, "schedule.signed_minutes_to_crs_departure", schedule_minutes
        )
    )

    for prefix, fields, values in (
        ("motion", MOTION_FIELDS, motion_values),
        ("weather", WEATHER_FIELDS, weather_values),
    ):
        for field in fields:
            raw = values[field]
            row.extend((float(raw is None), 0.0, 0.0))
    row.extend((0.0, 0.0, 0.0))

    motion_age = None
    weather_age = (
        None
        if observation is None
        else (decision_time - observation.availability_time).total_seconds() / 60.0
    )
    spacing = (
        0.0
        if previous_time is None
        else ((decision_time - previous_time).total_seconds() / 60.0)
    )
    row.extend(
        (
            _scaled(normalization, "motion.observation_age_minutes", motion_age),
            _scaled(normalization, "weather.observation_age_minutes", weather_age),
            _scaled(normalization, "node.spacing_minutes", spacing),
        )
    )

    row.extend(_one_hot(EVIDENCE_LEVELS, EvidenceClass.UNSUPPORTED.value))
    row.extend(
        _one_hot(
            EVIDENCE_LEVELS,
            (
                EvidenceClass.DIRECT.value
                if observation is not None
                else EvidenceClass.UNSUPPORTED.value
            ),
        )
    )
    row.extend(_one_hot(EVIDENCE_LEVELS, EvidenceClass.EMPIRICAL_REFERENCE.value))
    row.extend(_one_hot(SUPPORT_LEVELS, SupportState.ABSTAIN.value))
    row.extend(
        _one_hot(
            SUPPORT_LEVELS,
            (
                SupportState.SUPPORTED.value
                if observation is not None
                else SupportState.ABSTAIN.value
            ),
        )
    )
    row.extend(_one_hot(SUPPORT_LEVELS, SupportState.SUPPORTED.value))
    row.extend(_one_hot(STAGE_LEVELS, stage))
    if len(row) != len(FEATURE_NAMES):
        raise RuntimeError(
            f"M1_COMPACT_FEATURE_COUNT_MISMATCH:{len(row)}:{len(FEATURE_NAMES)}"
        )
    return row


def build_compact_warning_episode(
    item,
    *,
    weather,
    weather_max_age_minutes: int,
    normalization,
    config_hash: str,
    registry_hash: str,
    taxi_reference,
) -> CompactWarningEpisode:
    """Build one episode without retaining PREState objects or scenario rows."""
    episode, successor_schedule, predecessor_outcome, successor_outcome = item
    schedule = {
        "flight_id": _value(successor_schedule, "flight_id"),
        "scheduled_departure_utc": _value(
            successor_schedule, "scheduled_departure_utc"
        ),
        "scheduled_arrival_utc": _value(successor_schedule, "scheduled_arrival_utc"),
        "canonical_record_id": _value(
            successor_schedule, "canonical_schedule_record_id"
        )
        or _value(successor_schedule, "canonical_record_id"),
        "service_date": _value(successor_schedule, "service_date"),
    }
    reference = taxi_reference.lookup(episode.connection_airport_id)
    reference_state = getattr(
        reference.support_state, "value", str(reference.support_state)
    )
    reference_supported = (
        reference_state == SupportState.SUPPORTED.value and reference.value is not None
    )
    reference_minutes = None if not reference_supported else float(reference.value)
    reference_id = taxi_reference.reference_id if reference_supported else None
    reference_hash = taxi_reference.manifest_freeze_id if reference_supported else None

    count = episode_node_count(
        episode_start_time=episode.episode_start_time,
        episode_end_time=episode.episode_end_time,
    )
    times = tuple(
        episode.episode_start_time + timedelta(minutes=5 * index)
        for index in range(count)
    )
    rows, node_ids, stages = [], [], []
    observed_r_ib, observed_delta, observed_tx = [], [], []
    lead_times, decision_times = [], []
    previous = None
    for decision_time in times:
        stage = stage_at(
            decision_time,
            predecessor_in_block=_value(predecessor_outcome, "actual_arrival_utc"),
            successor_off_block=_value(successor_outcome, "actual_departure_utc"),
            successor_takeoff=_value(successor_outcome, "wheels_off_utc"),
        ).value
        observation = latest_weather(
            weather,
            episode.connection_airport_id,
            decision_time,
            weather_max_age_minutes,
        )
        legal_ids = [schedule["canonical_record_id"]]
        if observation is not None:
            legal_ids.append(observation.canonical_record_id)
        node_ids.append(
            _canonical_node_id(
                episode_id=episode.episode_id,
                decision_time=decision_time,
                config_hash=config_hash,
                registry_hash=registry_hash,
                legal_record_ids=legal_ids,
            )
        )
        rows.append(
            _feature_row(
                decision_time=decision_time,
                previous_time=previous,
                stage=stage,
                schedule=schedule,
                observation=observation,
                normalization=normalization,
            )
        )
        stages.append(stage)
        observed_r_ib.append(None if stage == OperationalStage.PRE_IB.value else 0.0)
        observed_delta.append(
            None
            if stage
            not in {
                OperationalStage.POST_OB_PRE_TO.value,
                OperationalStage.COMPLETED.value,
            }
            else (
                _value(successor_outcome, "actual_departure_utc")
                - schedule["scheduled_departure_utc"]
            ).total_seconds()
            / 60.0
        )
        observed_tx.append(
            None
            if stage != OperationalStage.COMPLETED.value
            else _value(successor_outcome, "taxi_out_minutes")
        )
        lead_times.append(
            (
                _value(successor_outcome, "wheels_off_utc") - decision_time
            ).total_seconds()
            / 60.0
            if _value(successor_outcome, "wheels_off_utc") is not None
            else float("nan")
        )
        decision_times.append(decision_time)
        previous = decision_time

    realized_d_to = None
    if (
        reference_minutes is not None
        and _value(successor_outcome, "actual_departure_utc") is not None
        and _value(successor_outcome, "taxi_out_minutes") is not None
    ):
        realized_delta = (
            _value(successor_outcome, "actual_departure_utc")
            - schedule["scheduled_departure_utc"]
        ).total_seconds() / 60.0
        realized_d_to = max(0.0, realized_delta) + max(
            0.0,
            float(_value(successor_outcome, "taxi_out_minutes")) - reference_minutes,
        )

    return CompactWarningEpisode(
        episode_id=episode.episode_id,
        episode_date=(
            schedule["service_date"].isoformat()
            if hasattr(schedule["service_date"], "isoformat")
            else str(schedule["service_date"])
        ),
        decision_times=tuple(decision_times),
        decision_node_ids=tuple(node_ids),
        features=torch.tensor(rows, dtype=torch.float32),
        stages=tuple(stages),
        observed_r_ib=tuple(observed_r_ib),
        observed_delta_ob=tuple(observed_delta),
        observed_t_tx=tuple(observed_tx),
        lead_times_minutes=tuple(lead_times),
        realized_d_to_minutes=realized_d_to,
        realized_event_positive=None if realized_d_to is None else realized_d_to > 30.0,
        taxi_reference_minutes=reference_minutes,
        taxi_reference_id=reference_id,
        taxi_reference_hash=reference_hash,
        taxi_reference_supported=reference_supported,
    )
