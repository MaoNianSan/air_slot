from datetime import datetime, timedelta
from model.common.enums import OperationalStage
from model.common.identity import content_id
from model.common.errors import NodeInvalidationError
from model.PRE.contracts.pre_state import DecisionNodeRecord
from .membership import require_episode_identity


def build_decision_node(*, episode_id: str, predecessor_id: str, successor_id: str,
                        decision_time: datetime, information_cutoff: datetime,
                        config_hash: str, registry_hash: str,
                        legal_record_ids: tuple[str, ...],
                        operational_stage: OperationalStage = OperationalStage.PRE_IB,
                        roll_minutes: int = 5, node_index: int = 0) -> DecisionNodeRecord:
    try:
        require_episode_identity(episode_id, predecessor_id, successor_id)
        if information_cutoff > decision_time:
            raise NodeInvalidationError("CRITICAL_DECISION_TIME_BOUNDARY_FAILURE")
    except Exception as exc:
        raise NodeInvalidationError(str(exc)) from exc
    if roll_minutes != 5:
        raise NodeInvalidationError("FORMAL_ROLL_INTERVAL_MUST_BE_FIVE_MINUTES")
    identity = content_id({"episode_id": episode_id, "decision_time": decision_time,
        "information_cutoff": information_cutoff, "config_hash": config_hash,
        "registry_hash": registry_hash, "legal_record_ids": sorted(legal_record_ids)})
    return DecisionNodeRecord(decision_node_id=identity, episode_id=episode_id,
        decision_time=decision_time, information_cutoff=information_cutoff,
        operational_stage=operational_stage, roll_minutes=roll_minutes, node_index=node_index,
        status="CONSTRUCTED", formal_eligible=True, config_hash=config_hash,
        registry_manifest_hash=registry_hash, legal_record_ids=tuple(sorted(legal_record_ids)))


def stage_at(decision_time: datetime, *, predecessor_in_block: datetime | None,
             successor_off_block: datetime | None,
             successor_takeoff: datetime | None) -> OperationalStage:
    if predecessor_in_block is None or decision_time < predecessor_in_block:
        return OperationalStage.PRE_IB
    if successor_off_block is None or decision_time < successor_off_block:
        return OperationalStage.POST_IB_PRE_OB
    if successor_takeoff is None or decision_time < successor_takeoff:
        return OperationalStage.POST_OB_PRE_TO
    return OperationalStage.COMPLETED


def build_rolling_decision_nodes(*, episode: "EpisodeRecord",
                                 predecessor_outcome: "OperationalEventRecord",
                                 successor_outcome: "OperationalEventRecord",
                                 config_hash: str, registry_hash: str,
                                 legal_record_ids: tuple[str, ...] = ()) -> tuple[DecisionNodeRecord, ...]:
    """Build the frozen t_n=t_0+5n grid without rewriting prior nodes."""
    from model.PRE.contracts.canonical import OperationalEventRecord
    from model.PRE.contracts.pre_state import EpisodeRecord

    if not isinstance(episode, EpisodeRecord) or not isinstance(predecessor_outcome, OperationalEventRecord) \
            or not isinstance(successor_outcome, OperationalEventRecord):
        raise NodeInvalidationError("TYPED_ROLLING_INPUT_REQUIRED")
    if predecessor_outcome.flight_id != episode.predecessor_flight_id \
            or successor_outcome.flight_id != episode.successor_flight_id:
        raise NodeInvalidationError("ROLLING_OUTCOME_EPISODE_IDENTITY_MISMATCH")
    nodes = []
    decision_time = episode.episode_start_time
    index = 0
    while decision_time <= episode.episode_end_time:
        stage = stage_at(decision_time,
            predecessor_in_block=predecessor_outcome.actual_arrival_utc,
            successor_off_block=successor_outcome.actual_departure_utc,
            successor_takeoff=successor_outcome.wheels_off_utc)
        nodes.append(build_decision_node(episode_id=episode.episode_id,
            predecessor_id=episode.predecessor_flight_id,
            successor_id=episode.successor_flight_id, decision_time=decision_time,
            information_cutoff=decision_time, config_hash=config_hash,
            registry_hash=registry_hash, legal_record_ids=legal_record_ids,
            operational_stage=stage, roll_minutes=5, node_index=index))
        decision_time += timedelta(minutes=5)
        index += 1
    return tuple(nodes)
