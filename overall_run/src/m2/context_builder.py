from __future__ import annotations

import json
import math
from typing import Mapping

import pandas as pd

from ..m1.adapter.bundle_loader import PublishedPreBundle
from ..m1.contracts import M1ScenarioBundle
from .contracts import (
    AvailabilityStatus,
    CONTEXT_FIELD_REGISTRY,
    ContextDirection,
    FlightContext,
    M2ContextBundle,
    M2ContextMetadata,
    M2ContractError,
    PassengerContext,
    ResourceContext,
)


NORMALIZATION_VERSION = "PRE_TRAIN_REFERENCE_AND_UNIT_INTERVAL_V1"


def _number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _support_status(value: object) -> AvailabilityStatus:
    normalized = str(value or "UNSUPPORTED").upper()
    if normalized in {
        "OFFICIAL_OBSERVED",
        "OFFICIAL_OPERATIONAL",
        "RECONSTRUCTED_HIGH",
        "AVAILABLE",
    }:
        return AvailabilityStatus.AVAILABLE
    if normalized in {
        "SUPPORTED_PROXY",
        "FALLBACK_PROXY",
        "OBSERVED_CHAIN_PROXY",
        "INFERRED_OPERATIONAL",
        "OPERATIONAL_INFERENCE",
        "EMPIRICAL_REFERENCE",
        "PROXY_AVAILABLE",
    }:
        return AvailabilityStatus.PROXY_AVAILABLE
    if normalized == "MISSING":
        return AvailabilityStatus.MISSING
    return AvailabilityStatus.UNSUPPORTED


def _status_label(status: AvailabilityStatus | str) -> str:
    return status.value if isinstance(status, AvailabilityStatus) else str(status)


def risk_direction_value(field: str, value: float) -> float:
    if field not in CONTEXT_FIELD_REGISTRY:
        raise M2ContractError(f"M2_CONTEXT_DIRECTION_NOT_REGISTERED:{field}")
    spec = CONTEXT_FIELD_REGISTRY[field]
    number = float(value)
    if not math.isfinite(number):
        raise M2ContractError(f"M2_CONTEXT_VALUE_NONFINITE:{field}")
    if not spec.normalized_unit_interval:
        if spec.direction is ContextDirection.LARGER_IS_LOWER_RISK:
            raise M2ContractError(f"M2_CONTEXT_NORMALIZER_REQUIRED:{field}")
        return number
    if not 0.0 <= number <= 1.0:
        raise M2ContractError(f"M2_CONTEXT_UNIT_INTERVAL_REQUIRED:{field}")
    if spec.direction is ContextDirection.LARGER_IS_LOWER_RISK:
        return 1.0 - number
    return number


def _explicit_context(
    episode: pd.Series,
    field: str,
    support: dict[str, AvailabilityStatus],
    provenance: dict[str, dict[str, object]],
) -> float | None:
    if field not in episode.index:
        return None
    value = _number(episode.get(field))
    if value is None:
        support[field] = AvailabilityStatus.MISSING
        provenance[field] = {
            "source": "PRE_EPISODES",
            "source_field": field,
            "reason": "PRE_FIELD_VALUE_MISSING",
        }
        return None
    spec = CONTEXT_FIELD_REGISTRY[field]
    if spec.normalized_unit_interval and not 0.0 <= value <= 1.0:
        support[field] = AvailabilityStatus.UNSUPPORTED
        provenance[field] = {
            "source": "PRE_EPISODES",
            "source_field": field,
            "reason": "PRE_FIELD_NOT_UNIT_INTERVAL_AND_NO_FROZEN_NORMALIZER",
            "raw_value": value,
        }
        return None
    status = _support_status(
        episode.get(f"{field}_evidence_status", episode.get("chain_support_level"))
    )
    support[field] = status
    provenance[field] = {
        "source": "PRE_EPISODES",
        "source_field": field,
        "support_status": status.value,
    }
    return value


def _derive_inverse(
    source_field: str,
    target_field: str,
    value: float | None,
    support: dict[str, AvailabilityStatus],
    provenance: dict[str, dict[str, object]],
) -> float | None:
    if value is None:
        return None
    result = risk_direction_value(source_field, value)
    support[target_field] = support[source_field]
    provenance[target_field] = {
        "source": "M2_CONTEXT_DIRECTION_NORMALIZATION",
        "source_field": source_field,
        "transformation": "ONE_MINUS_UNIT_INTERVAL",
        "source_support_status": _status_label(support[source_field]),
    }
    return result


def _reference_group_matches(group_key: object, episode: pd.Series) -> bool:
    try:
        payload = json.loads(str(group_key))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping):
        return False
    aliases = {
        "airport": ("turnaround_airport", "airport"),
        "turnaround_airport": ("turnaround_airport", "airport"),
        "aircraft_group": ("aircraft_group",),
        "episode_start_time_bin": ("episode_start_time_bin",),
        "destination": ("successor_destination", "destination"),
    }
    for key, expected in payload.items():
        if key == "source_period":
            continue
        candidates = aliases.get(str(key), (str(key),))
        actual = next(
            (episode.get(name) for name in candidates if name in episode.index),
            None,
        )
        if actual is None or pd.isna(actual) or str(actual) != str(expected):
            return False
    return True


def _calibration_reference(
    bundle: PublishedPreBundle,
    episode: pd.Series,
    reference_types: tuple[str, ...],
) -> pd.Series | None:
    frame = bundle.calibration
    if frame.empty or "reference_type" not in frame:
        return None
    candidates = frame[
        frame["reference_type"].astype(str).isin(reference_types)
        & pd.to_numeric(frame.get("reference_value"), errors="coerce").notna()
    ].copy()
    if candidates.empty:
        return None
    matched = candidates[
        candidates.get("group_key", pd.Series(index=candidates.index, dtype=object))
        .map(lambda value: _reference_group_matches(value, episode))
    ]
    if matched.empty:
        return None
    order = {name: index for index, name in enumerate(reference_types)}
    matched["_priority"] = matched["reference_type"].map(order)
    return matched.sort_values(["_priority", "cell_size"], ascending=[True, False]).iloc[0]


def _turnaround_context(
    bundle: PublishedPreBundle,
    scenario: M1ScenarioBundle,
    episode: pd.Series,
    support: dict[str, AvailabilityStatus],
    provenance: dict[str, dict[str, object]],
) -> tuple[object | None, float | None, str]:
    refs = scenario.operational_references
    sobt = refs.successor_sobt.value if refs.successor_sobt.active else None
    support["successor_sobt"] = _support_status(refs.successor_sobt.support_level)
    provenance["successor_sobt"] = {
        "source": "M1_OPERATIONAL_REFERENCES",
        "source_field": refs.successor_sobt.source_field,
        "reference_version": refs.successor_sobt.reference_version,
        "inactive_reason": refs.successor_sobt.inactive_reason,
    }
    if not refs.successor_sobt.active:
        support["successor_sobt"] = AvailabilityStatus.UNSUPPORTED

    if refs.turnaround_floor_minutes.active:
        value = _number(refs.turnaround_floor_minutes.value)
        support["turnaround_reference_minutes"] = _support_status(
            refs.turnaround_floor_minutes.support_level
        )
        provenance["turnaround_reference_minutes"] = {
            "source": "M1_OPERATIONAL_REFERENCES",
            "source_field": refs.turnaround_floor_minutes.source_field,
            "reference_version": refs.turnaround_floor_minutes.reference_version,
            "reference_type": "OFFICIAL_FLOOR",
        }
        return sobt, value, "OFFICIAL_FLOOR"

    reference = _calibration_reference(
        bundle,
        episode,
        ("minimum_turnaround", "typical_turnaround"),
    )
    if reference is None:
        support["turnaround_reference_minutes"] = AvailabilityStatus.UNSUPPORTED
        provenance["turnaround_reference_minutes"] = {
            "source": "PRE_CALIBRATION",
            "reason": "NO_MATCHING_TRAIN_ONLY_TURNAROUND_REFERENCE",
        }
        return sobt, None, "UNSUPPORTED"
    value = _number(reference.get("reference_value"))
    support["turnaround_reference_minutes"] = AvailabilityStatus.PROXY_AVAILABLE
    provenance["turnaround_reference_minutes"] = {
        "source": "PRE_CALIBRATION",
        "reference_id": reference.get("reference_id"),
        "reference_type": reference.get("reference_type"),
        "statistic": reference.get("statistic"),
        "fit_split": reference.get("fit_split"),
        "source_hash": reference.get("source_hash"),
    }
    return sobt, value, "EMPIRICAL_REFERENCE"


def _passenger_load_proxy(
    bundle: PublishedPreBundle,
    episode: pd.Series,
    support: dict[str, AvailabilityStatus],
    provenance: dict[str, dict[str, object]],
) -> float | None:
    explicit = _explicit_context(episode, "passenger_load_proxy", support, provenance)
    if explicit is not None:
        return explicit
    reference = _calibration_reference(
        bundle,
        episode,
        ("passenger_per_flight", "passenger_load_factor"),
    )
    if reference is None:
        return None
    value = _number(reference.get("reference_value"))
    if value is None:
        return None
    support["passenger_load_proxy"] = AvailabilityStatus.PROXY_AVAILABLE
    provenance["passenger_load_proxy"] = {
        "source": "PRE_CALIBRATION",
        "reference_id": reference.get("reference_id"),
        "reference_type": reference.get("reference_type"),
        "fit_split": reference.get("fit_split"),
        "source_hash": reference.get("source_hash"),
    }
    return value


def _flow_pressure(
    bundle: PublishedPreBundle,
    episode: pd.Series,
    query_time: datetime,
    support: dict[str, AvailabilityStatus],
    provenance: dict[str, dict[str, object]],
) -> float | None:
    explicit = _explicit_context(episode, "airport_flow_pressure", support, provenance)
    if explicit is not None:
        return explicit
    memberships = bundle.observation_membership
    observations = bundle.observations
    if memberships.empty or observations.empty:
        return None
    episode_id = str(episode.get("chain_episode_id", ""))
    member = memberships[
        memberships.get("chain_episode_id", pd.Series(dtype=str)).astype(str).eq(episode_id)
        & memberships.get("availability_supported", pd.Series(dtype=bool)).fillna(False).astype(bool)
    ]
    if member.empty:
        return None
    selected = observations[
        observations.get("observation_id", pd.Series(dtype=str)).astype(str).isin(
            member["observation_id"].astype(str)
        )
        & observations.get("source", pd.Series(dtype=str)).astype(str).eq("flow")
    ].copy()
    if selected.empty or "flow_count" not in selected:
        return None
    selected["availability_time"] = pd.to_datetime(
        selected["availability_time"], utc=True, errors="coerce"
    )
    selected = selected[selected["availability_time"].le(pd.Timestamp(query_time))]
    if selected.empty:
        return None
    row = selected.sort_values(["availability_time", "observation_id"]).iloc[-1]
    value = _number(row.get("flow_count"))
    reference = _calibration_reference(bundle, episode, ("flow_flow_count",))
    reference_value = None if reference is None else _number(reference.get("reference_value"))
    if value is None or reference_value is None or reference_value <= 0.0:
        return None
    normalized = min(max(value / reference_value, 0.0), 1.0)
    support["airport_flow_pressure"] = AvailabilityStatus.PROXY_AVAILABLE
    provenance["airport_flow_pressure"] = {
        "source": "PRE_OBSERVATIONS_PLUS_TRAIN_REFERENCE",
        "observation_id": row.get("observation_id"),
        "source_record_id": row.get("source_record_id"),
        "reference_id": reference.get("reference_id") if reference is not None else None,
        "transformation": "CLIP_FLOW_COUNT_DIV_TRAIN_Q90_0_1",
    }
    return normalized


def build_m2_context(
    pre_bundle: PublishedPreBundle,
    scenario: M1ScenarioBundle,
) -> M2ContextBundle:
    metadata = scenario.metadata
    episode_id = str(metadata.get("episode_id", ""))
    expected_pre_id = str(metadata.get("pre_bundle_id", ""))
    if expected_pre_id != pre_bundle.identity.pre_manifest_hash:
        raise M2ContractError("M2_PRE_M1_VERSION_MISMATCH")
    rows = pre_bundle.episodes[
        pre_bundle.episodes.get("chain_episode_id", pd.Series(dtype=str))
        .astype(str)
        .eq(episode_id)
    ]
    if len(rows) != 1:
        raise M2ContractError("M2_PRE_EPISODE_NOT_UNIQUE")
    episode = rows.iloc[0]
    support = {
        field: AvailabilityStatus.UNSUPPORTED for field in CONTEXT_FIELD_REGISTRY
    }
    provenance = {
        field: {
            "source": "PRE_CORE_V2",
            "reason": "PRE_FIELD_NOT_AVAILABLE",
        }
        for field in CONTEXT_FIELD_REGISTRY
    }
    successor_sobt, turnaround, turnaround_type = _turnaround_context(
        pre_bundle, scenario, episode, support, provenance
    )

    continuity = _explicit_context(episode, "continuity_exposure", support, provenance)
    downstream_raw = _explicit_context(episode, "downstream_leg_count", support, provenance)
    downstream = None if downstream_raw is None else int(downstream_raw)
    margin = _explicit_context(episode, "execution_window_margin", support, provenance)
    window_pressure = _derive_inverse(
        "execution_window_margin", "execution_window_pressure", margin, support, provenance
    )
    flexibility = _explicit_context(episode, "aircraft_flexibility", support, provenance)
    aircraft_constraint = _derive_inverse(
        "aircraft_flexibility", "aircraft_constraint", flexibility, support, provenance
    )

    passenger_load = _passenger_load_proxy(pre_bundle, episode, support, provenance)
    slack = _explicit_context(episode, "connection_slack", support, provenance)
    pressure = _explicit_context(episode, "connection_pressure", support, provenance)
    if pressure is None and slack is not None:
        pressure = _derive_inverse(
            "connection_slack", "connection_pressure", slack, support, provenance
        )
    rebooking = _explicit_context(episode, "rebooking_scarcity", support, provenance)

    query_time = metadata["query_time"]
    flow_pressure = _flow_pressure(
        pre_bundle, episode, query_time, support, provenance
    )
    infrastructure = _explicit_context(
        episode, "infrastructure_flexibility", support, provenance
    )
    infrastructure_constraint = _derive_inverse(
        "infrastructure_flexibility",
        "infrastructure_constraint",
        infrastructure,
        support,
        provenance,
    )
    availability = _explicit_context(
        episode, "resource_availability", support, provenance
    )
    scarcity = _derive_inverse(
        "resource_availability", "resource_scarcity", availability, support, provenance
    )
    ground_pressure = _explicit_context(
        episode, "ground_support_pressure", support, provenance
    )

    return M2ContextBundle(
        metadata=M2ContextMetadata(
            episode_id=episode_id,
            query_time=query_time,
            information_cutoff=metadata["information_cutoff"],
            pre_bundle_id=pre_bundle.identity.pre_manifest_hash,
            pre_contract_id=pre_bundle.identity.contract_id,
            pre_schema_version=pre_bundle.identity.schema_version,
            pre_research_revision=pre_bundle.identity.research_code_revision,
        ),
        flight_context=FlightContext(
            successor_sobt=successor_sobt,
            turnaround_reference_minutes=turnaround,
            turnaround_reference_type=turnaround_type,
            continuity_exposure=continuity,
            downstream_leg_count=downstream,
            execution_window_margin=margin,
            execution_window_pressure=window_pressure,
            aircraft_flexibility=flexibility,
            aircraft_constraint=aircraft_constraint,
        ),
        passenger_context=PassengerContext(
            passenger_load_proxy=passenger_load,
            connection_pressure=pressure,
            connection_slack=slack,
            rebooking_scarcity=rebooking,
        ),
        resource_context=ResourceContext(
            airport_flow_pressure=flow_pressure,
            infrastructure_flexibility=infrastructure,
            infrastructure_constraint=infrastructure_constraint,
            resource_availability=availability,
            resource_scarcity=scarcity,
            ground_support_pressure=ground_pressure,
        ),
        context_support=support,
        normalization_version=(
            f"{NORMALIZATION_VERSION}:{pre_bundle.identity.frozen_config_hash[:12]}"
        ),
        provenance=provenance,
    )
