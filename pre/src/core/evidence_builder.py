from __future__ import annotations

from typing import Any

import pandas as pd

from ..input import object_hash
from .contracts import CHAIN_CONTRACT_ID, SupportLevel, stable_id


EVIDENCE_COLUMNS = [
    "evidence_id",
    "table",
    "entity_id",
    "variable_name",
    "raw_source",
    "raw_field",
    "source_record_id",
    "source_file",
    "source_hash",
    "event_time",
    "availability_time",
    "transformation",
    "support_level",
    "fallback_level",
    "missing_reason",
    "future_information_used",
]


def _finalize(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["evidence_id"] = [
        stable_id(row.table, row.entity_id, row.variable_name, row.source_record_id)
        for row in frame.itertuples(index=False)
    ]
    for column in ["event_time", "availability_time"]:
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return frame[EVIDENCE_COLUMNS].sort_values("evidence_id", kind="mergesort").reset_index(drop=True)


def build_evidence_audit(
    events: pd.DataFrame,
    episodes: pd.DataFrame,
    calibration: pd.DataFrame,
    observation_evidence: list[dict[str, object]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = list(observation_evidence)
    for event in events.itertuples(index=False):
        unsupported = event.support_level == SupportLevel.UNSUPPORTED.value
        rows.append(
            {
                "table": "events",
                "entity_id": event.flight_id,
                "variable_name": event.event_name,
                "raw_source": event.source_type,
                "raw_field": event.source_field,
                "source_record_id": event.source_record_id,
                "source_file": event.source_file,
                "source_hash": event.source_hash,
                "event_time": event.event_time,
                "availability_time": event.availability_time,
                "transformation": event.reconstruction_method,
                "support_level": event.support_level,
                "fallback_level": "NONE" if not unsupported else "UNSUPPORTED",
                "missing_reason": "" if not unsupported else "NO_LOCAL_SOURCE_FIELD",
                "future_information_used": False,
            }
        )
    for episode in episodes.itertuples(index=False):
        source_hash = object_hash(
            sorted(
                value
                for value in [episode.predecessor_source_hash, episode.successor_source_hash]
                if pd.notna(value)
            )
        )
        rows.append(
            {
                "table": "episodes",
                "entity_id": episode.chain_episode_id,
                "variable_name": "chain_match_status",
                "raw_source": "OPEN_SKY_FLIGHTLIST",
                "raw_field": "icao24,origin,destination,firstseen,lastseen",
                "source_record_id": f"{episode.predecessor_source_record_id}|{episode.successor_source_record_id}",
                "source_file": f"{episode.predecessor_source_file}|{episode.successor_source_file}",
                "source_hash": source_hash,
                "event_time": episode.episode_start_time,
                "availability_time": episode.successor_lastseen_proxy,
                "transformation": CHAIN_CONTRACT_ID,
                "support_level": episode.chain_support_level,
                "fallback_level": "NONE",
                "missing_reason": episode.exclusion_reason,
                "future_information_used": False,
            }
        )
        for label in ["y_ob", "y_tx", "y_to"]:
            rows.append(
                {
                    "table": "episodes",
                    "entity_id": episode.chain_episode_id,
                    "variable_name": label,
                    "raw_source": "UNSUPPORTED",
                    "raw_field": pd.NA,
                    "source_record_id": episode.successor_source_record_id,
                    "source_file": episode.successor_source_file,
                    "source_hash": source_hash,
                    "event_time": episode.episode_end_time,
                    "availability_time": episode.successor_lastseen_proxy,
                    "transformation": "NOT_COMPUTED",
                    "support_level": SupportLevel.UNSUPPORTED.value,
                    "fallback_level": "UNSUPPORTED",
                    "missing_reason": episode.label_missing_reason,
                    "future_information_used": False,
                }
            )
    for reference in calibration.itertuples(index=False):
        rows.append(
            {
                "table": "calibration",
                "entity_id": reference.reference_id,
                "variable_name": reference.reference_type,
                "raw_source": "TRAIN_ONLY_REFERENCE",
                "raw_field": reference.statistic,
                "source_record_id": reference.group_key,
                "source_file": pd.NA,
                "source_hash": reference.source_hash,
                "event_time": reference.fit_end_time,
                "availability_time": reference.fit_end_time,
                "transformation": reference.statistic,
                "support_level": (
                    SupportLevel.UNSUPPORTED.value
                    if reference.fallback_level == "UNSUPPORTED"
                    else SupportLevel.SUPPORTED_PROXY.value
                ),
                "fallback_level": reference.fallback_level,
                "missing_reason": "NO_SUPPORTED_REFERENCE" if pd.isna(reference.reference_value) else "",
                "future_information_used": False,
            }
        )
    return _finalize(rows)
