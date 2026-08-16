from datetime import datetime
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.PRE.contracts.pre_state import EpisodeRecord


CHAIN_RULE_ID = "SAME_AIRCRAFT_AIRPORT_GAP"
CHAIN_RULE_VERSION = "1.0.0"
CHAIN_RELATION_TYPE = "SAME_AIRCRAFT_PREDECESSOR_SUCCESSOR"
CHAIN_JOIN_KEYS = (
    "dataset_instance_id",
    "aircraft_id_namespace",
    "aircraft_id",
    "predecessor.destination_airport_id=successor.origin_airport_id",
)
CHAIN_ORDERING_RULE = (
    "GROUP_BY(dataset_instance_id,aircraft_id_namespace,aircraft_id);"
    "ORDER_BY(event_start_time,event_end_time,flight_id);"
    "WINDOW(ADJACENT_ROWS);TIE_BREAK(event_end_time,flight_id)"
)
CHAIN_CONTINUITY_RULE = "AIRPORT_CONTINUITY_AND_POSITIVE_BOUNDED_GAP"


def _source_record_id(record: dict) -> str:
    return str(
        record.get("canonical_record_id")
        or record.get("source_record_id")
        or record["flight_id"]
    )


def build_episode_chain(predecessor: dict, successor: dict, *, max_gap_minutes: int = 360) -> EpisodeRecord:
    for key in ("flight_id", "aircraft_id", "aircraft_id_namespace", "origin_airport_id",
                "destination_airport_id", "event_start_time", "event_end_time", "dataset_instance_id"):
        if not predecessor.get(key) or not successor.get(key): raise ContractError(f"EPISODE_IDENTITY_MISSING:{key}")
    if (predecessor["aircraft_id"], predecessor["aircraft_id_namespace"]) != (
            successor["aircraft_id"], successor["aircraft_id_namespace"]):
        raise ContractError("EPISODE_AIRCRAFT_MISMATCH")
    if predecessor["dataset_instance_id"] != successor["dataset_instance_id"]:
        raise ContractError("EPISODE_DATASET_MISMATCH")
    if predecessor["destination_airport_id"] != successor["origin_airport_id"]:
        raise ContractError("EPISODE_AIRPORT_DISCONTINUITY")
    if predecessor["event_end_time"] >= successor["event_start_time"]:
        raise ContractError("EPISODE_TIME_ORDER_INVALID")
    gap = (successor["event_start_time"] - predecessor["event_end_time"]).total_seconds() / 60
    if gap > max_gap_minutes: raise ContractError("EPISODE_GAP_EXCEEDS_RULE")
    payload = {"dataset": predecessor["dataset_instance_id"], "predecessor": predecessor["flight_id"],
               "successor": successor["flight_id"], "rule": f"{CHAIN_RULE_ID}_{max_gap_minutes}"}
    source_record_ids = (_source_record_id(predecessor), _source_record_id(successor))
    return EpisodeRecord(episode_id=content_id(payload), dataset_instance_id=predecessor["dataset_instance_id"],
        predecessor_flight_id=predecessor["flight_id"], successor_flight_id=successor["flight_id"],
        aircraft_id=predecessor["aircraft_id"], aircraft_id_namespace=predecessor["aircraft_id_namespace"],
        connection_airport_id=predecessor["destination_airport_id"],
        episode_start_time=predecessor["event_start_time"], episode_end_time=successor["event_end_time"],
        chain_rule_id=CHAIN_RULE_ID, chain_rule_version=CHAIN_RULE_VERSION,
        chain_rule_parameters=(f"max_gap_minutes={max_gap_minutes}",),
        relation_type=CHAIN_RELATION_TYPE, join_keys=CHAIN_JOIN_KEYS,
        ordering_rule=CHAIN_ORDERING_RULE, continuity_rule=CHAIN_CONTINUITY_RULE,
        source_record_ids=source_record_ids,
        construction_provenance=source_record_ids + (f"{CHAIN_RULE_ID}@{CHAIN_RULE_VERSION}",),
        lineage_support=SupportState.SUPPORTED,
        formal_eligible=True, quality_flags=())


def build_episode_records(flights: list[dict], *, max_gap_minutes: int = 360) -> list[EpisodeRecord]:
    required = (
        "dataset_instance_id", "aircraft_id_namespace", "aircraft_id", "flight_id",
        "origin_airport_id", "destination_airport_id", "event_start_time", "event_end_time",
    )
    for row in flights:
        for key in required:
            if not row.get(key):
                raise ContractError(f"EPISODE_IDENTITY_MISSING:{key}")
    ordered = sorted(flights, key=lambda row: (
        row["dataset_instance_id"], row["aircraft_id_namespace"], row["aircraft_id"],
        row["event_start_time"], row["event_end_time"], row["flight_id"]))
    ordering_keys = [
        (row["dataset_instance_id"], row["aircraft_id_namespace"], row["aircraft_id"],
         row["event_start_time"], row["event_end_time"], row["flight_id"])
        for row in ordered
    ]
    if len(ordering_keys) != len(set(ordering_keys)):
        raise ContractError("EPISODE_DUPLICATE_ORDERING_KEY")
    episodes = []
    for predecessor, successor in zip(ordered, ordered[1:]):
        try: episodes.append(build_episode_chain(predecessor, successor, max_gap_minutes=max_gap_minutes))
        except ContractError: continue
    return episodes


# ---- DATA2 chain (D2-1, approved 2026-08-14: option A + D) ----
DATA2_CHAIN_RULE_ID = "DATA2_SAME_AIRCRAFT_AIRPORT_GAP"
DATA2_CHAIN_RULE_VERSION = "1.0.0"
DATA2_CHAIN_JOIN_KEYS = CHAIN_JOIN_KEYS
DATA2_CHAIN_ORDERING_RULE = (
    "GROUP_BY(dataset_instance_id,aircraft_id_namespace,aircraft_id);"
    "ORDER_BY(actual_departure_utc,actual_arrival_utc,flight_id);"
    "WINDOW(ADJACENT_ROWS)"
)
DATA2_CHAIN_CONTINUITY_RULE = "AIRPORT_CONTINUITY_AND_POSITIVE_BOUNDED_ACTUAL_GATE_GAP"


def build_data2_episode_chain(predecessor: dict, successor: dict, *, max_gap_minutes: int = 360) -> EpisodeRecord:
    """D2-1 chain adjacency on DIRECT actual gate events: gap = succ.DepTime - pred.ArrTime (UTC).

    D2-2 episode anchors (approved 2026-08-14, option B): the CRS schedule turnaround
    window [pred.CRSArr, succ.CRSDep] (UTC); pairs with schedule turnaround <= 0
    (inverted window) are excluded from the chain. Labels keep DIRECT actuals.
    """
    for key in ("flight_id", "aircraft_id", "aircraft_id_namespace", "origin_airport_id",
                "destination_airport_id", "event_start_time", "event_end_time",
                "actual_arrival_utc", "actual_departure_utc", "dataset_instance_id"):
        if not predecessor.get(key) or not successor.get(key):
            raise ContractError(f"EPISODE_IDENTITY_MISSING:{key}")
    if (predecessor["aircraft_id"], predecessor["aircraft_id_namespace"]) != (
            successor["aircraft_id"], successor["aircraft_id_namespace"]):
        raise ContractError("EPISODE_AIRCRAFT_MISMATCH")
    if predecessor["dataset_instance_id"] != successor["dataset_instance_id"]:
        raise ContractError("EPISODE_DATASET_MISMATCH")
    if predecessor["destination_airport_id"] != successor["origin_airport_id"]:
        raise ContractError("EPISODE_AIRPORT_DISCONTINUITY")
    if predecessor["actual_arrival_utc"] >= successor["actual_departure_utc"]:
        raise ContractError("EPISODE_TIME_ORDER_INVALID")
    gap = (successor["actual_departure_utc"] - predecessor["actual_arrival_utc"]).total_seconds() / 60
    if gap > max_gap_minutes:
        raise ContractError("EPISODE_GAP_EXCEEDS_RULE")
    payload = {"dataset": predecessor["dataset_instance_id"], "predecessor": predecessor["flight_id"],
               "successor": successor["flight_id"], "rule": f"{DATA2_CHAIN_RULE_ID}_{max_gap_minutes}"}
    source_record_ids = (_source_record_id(predecessor), _source_record_id(successor))
    return EpisodeRecord(
        episode_id=content_id(payload),
        dataset_instance_id=predecessor["dataset_instance_id"],
        predecessor_flight_id=predecessor["flight_id"],
        successor_flight_id=successor["flight_id"],
        aircraft_id=predecessor["aircraft_id"],
        aircraft_id_namespace=predecessor["aircraft_id_namespace"],
        connection_airport_id=predecessor["destination_airport_id"],
        episode_start_time=predecessor["event_end_time"],
        episode_end_time=successor["event_start_time"],
        chain_rule_id=DATA2_CHAIN_RULE_ID,
        chain_rule_version=DATA2_CHAIN_RULE_VERSION,
        chain_rule_parameters=(f"max_gap_minutes={max_gap_minutes}", "gap_source=actual_gate_utc",
                               "episode_anchors=schedule_turnaround_window"),
        relation_type=CHAIN_RELATION_TYPE,
        join_keys=DATA2_CHAIN_JOIN_KEYS,
        ordering_rule=DATA2_CHAIN_ORDERING_RULE,
        continuity_rule=DATA2_CHAIN_CONTINUITY_RULE,
        source_record_ids=source_record_ids,
        construction_provenance=source_record_ids + (f"{DATA2_CHAIN_RULE_ID}@{DATA2_CHAIN_RULE_VERSION}",),
        lineage_support=SupportState.SUPPORTED,
        formal_eligible=True,
        quality_flags=(),
    )


def build_data2_episode_records(flights: list[dict], *, max_gap_minutes: int = 360) -> list[EpisodeRecord]:
    required = (
        "dataset_instance_id", "aircraft_id_namespace", "aircraft_id", "flight_id",
        "origin_airport_id", "destination_airport_id", "event_start_time", "event_end_time",
        "actual_arrival_utc", "actual_departure_utc",
    )
    for row in flights:
        for key in required:
            if not row.get(key):
                raise ContractError(f"EPISODE_IDENTITY_MISSING:{key}")
    ordered = sorted(flights, key=lambda row: (
        row["dataset_instance_id"], row["aircraft_id_namespace"], row["aircraft_id"],
        row["actual_departure_utc"], row["actual_arrival_utc"], row["flight_id"]))
    ordering_keys = [
        (row["dataset_instance_id"], row["aircraft_id_namespace"], row["aircraft_id"],
         row["actual_departure_utc"], row["actual_arrival_utc"], row["flight_id"])
        for row in ordered
    ]
    if len(ordering_keys) != len(set(ordering_keys)):
        raise ContractError("EPISODE_DUPLICATE_ORDERING_KEY")
    episodes = []
    for predecessor, successor in zip(ordered, ordered[1:]):
        try:
            episodes.append(build_data2_episode_chain(predecessor, successor, max_gap_minutes=max_gap_minutes))
        except (ContractError, ValueError):
            # ValueError = inverted CRS turnaround window (pred.CRSArr >= succ.CRSDep),
            # i.e. schedule turnaround <= 0 -> pair excluded (D2-2 option B boundary).
            continue
    return episodes
