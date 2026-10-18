from datetime import datetime
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.PRE.contracts.pre_state import EpisodeRecord


def build_episode_chain(predecessor: dict, successor: dict, *, max_gap_minutes: int = 360) -> EpisodeRecord:
    for key in ("flight_id", "aircraft_id", "aircraft_id_namespace", "origin_airport_id",
                "destination_airport_id", "event_start_time", "event_end_time", "dataset_instance_id"):
        if not predecessor.get(key) or not successor.get(key): raise ContractError(f"EPISODE_IDENTITY_MISSING:{key}")
    if (predecessor["aircraft_id"], predecessor["aircraft_id_namespace"]) != (
            successor["aircraft_id"], successor["aircraft_id_namespace"]):
        raise ContractError("EPISODE_AIRCRAFT_MISMATCH")
    if predecessor["destination_airport_id"] != successor["origin_airport_id"]:
        raise ContractError("EPISODE_AIRPORT_DISCONTINUITY")
    if predecessor["event_end_time"] >= successor["event_start_time"]:
        raise ContractError("EPISODE_TIME_ORDER_INVALID")
    gap = (successor["event_start_time"] - predecessor["event_end_time"]).total_seconds() / 60
    if gap > max_gap_minutes: raise ContractError("EPISODE_GAP_EXCEEDS_RULE")
    payload = {"dataset": predecessor["dataset_instance_id"], "predecessor": predecessor["flight_id"],
               "successor": successor["flight_id"], "rule": f"SAME_AIRCRAFT_AIRPORT_GAP_{max_gap_minutes}"}
    return EpisodeRecord(episode_id=content_id(payload), dataset_instance_id=predecessor["dataset_instance_id"],
        predecessor_flight_id=predecessor["flight_id"], successor_flight_id=successor["flight_id"],
        aircraft_id=predecessor["aircraft_id"], aircraft_id_namespace=predecessor["aircraft_id_namespace"],
        connection_airport_id=predecessor["destination_airport_id"],
        episode_start_time=predecessor["event_start_time"], episode_end_time=successor["event_end_time"],
        chain_rule_id=payload["rule"], lineage_support=SupportState.SUPPORTED,
        formal_eligible=True, quality_flags=())


def build_episode_records(flights: list[dict], *, max_gap_minutes: int = 360) -> list[EpisodeRecord]:
    ordered = sorted(flights, key=lambda row: (row.get("aircraft_id", ""), row.get("event_start_time")))
    episodes = []
    for predecessor, successor in zip(ordered, ordered[1:]):
        try: episodes.append(build_episode_chain(predecessor, successor, max_gap_minutes=max_gap_minutes))
        except ContractError: continue
    return episodes
