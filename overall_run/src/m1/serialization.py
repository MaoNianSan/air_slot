from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping

from .contracts import (
    M1JointSample,
    M1MarginalDistribution,
    M1ScenarioBundle,
    OperationalReferences,
    SupportedOperationalValue,
)


def _encode(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _encode(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value


def scenario_to_dict(bundle: M1ScenarioBundle) -> dict[str, object]:
    return _encode(bundle)


def _datetime(value):
    return None if value is None else datetime.fromisoformat(str(value))


def _supported(payload: Mapping[str, object]) -> SupportedOperationalValue:
    raw_value = payload.get("value")
    if isinstance(raw_value, str):
        try:
            raw_value = datetime.fromisoformat(raw_value)
        except ValueError:
            pass
    return SupportedOperationalValue(
        value=raw_value,
        active=bool(payload["active"]),
        support_level=str(payload["support_level"]),
        source_field=payload.get("source_field"),
        source_event_id=payload.get("source_event_id"),
        availability_time=_datetime(payload.get("availability_time")),
        reference_version=payload.get("reference_version"),
        inactive_reason=payload.get("inactive_reason"),
    )


def scenario_from_dict(payload: Mapping[str, object]) -> M1ScenarioBundle:
    references_raw = payload["operational_references"]
    references = OperationalReferences(
        **{name: _supported(value) for name, value in references_raw.items()}
    )
    distributions = {}
    for name, value in payload["marginal_distributions"].items():
        record = dict(value)
        record["query_time"] = _datetime(record["query_time"])
        record["information_cutoff"] = _datetime(record["information_cutoff"])
        record["bin_lower_minutes"] = tuple(record["bin_lower_minutes"])
        record["bin_upper_minutes"] = tuple(record["bin_upper_minutes"])
        record["probabilities"] = tuple(record["probabilities"])
        distributions[name] = M1MarginalDistribution(**record)
    samples = []
    datetime_fields = (
        "query_time", "information_cutoff", "earliest_offblock_time",
        "T_predecessor_inblock", "AOBT_successor", "ATOT_successor",
    )
    for value in payload["joint_samples"]:
        record = dict(value)
        for field in datetime_fields:
            record[field] = _datetime(record.get(field))
        samples.append(M1JointSample(**record))
    metadata = dict(payload["metadata"])
    for field in ("query_time", "information_cutoff"):
        if field in metadata:
            metadata[field] = _datetime(metadata[field])
    return M1ScenarioBundle(
        metadata=metadata,
        operational_references=references,
        marginal_distributions=distributions,
        sampling_metadata=dict(payload["sampling_metadata"]),
        joint_samples=tuple(samples),
        pre_context=dict(payload.get("pre_context", {})),
    )
