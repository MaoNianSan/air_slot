from datetime import datetime
from model.common.enums import OperationalStage
from model.common.identity import content_id
from model.common.errors import NodeInvalidationError
from model.PRE.contracts.pre_state import DecisionNodeRecord
from .membership import require_episode_identity


def build_decision_node(*, episode_id: str, predecessor_id: str, successor_id: str,
                        decision_time: datetime, information_cutoff: datetime,
                        config_hash: str, registry_hash: str,
                        legal_record_ids: tuple[str, ...]) -> DecisionNodeRecord:
    try:
        require_episode_identity(episode_id, predecessor_id, successor_id)
        if information_cutoff > decision_time:
            raise NodeInvalidationError("CRITICAL_DECISION_TIME_BOUNDARY_FAILURE")
    except Exception as exc:
        raise NodeInvalidationError(str(exc)) from exc
    identity = content_id({"episode_id": episode_id, "decision_time": decision_time,
        "information_cutoff": information_cutoff, "config_hash": config_hash,
        "registry_hash": registry_hash, "legal_record_ids": sorted(legal_record_ids)})
    return DecisionNodeRecord(decision_node_id=identity, episode_id=episode_id,
        decision_time=decision_time, information_cutoff=information_cutoff,
        operational_stage=OperationalStage.PRE_IB, roll_minutes=5, node_index=0,
        status="CONSTRUCTED", formal_eligible=True, config_hash=config_hash,
        registry_manifest_hash=registry_hash, legal_record_ids=tuple(sorted(legal_record_ids)))
