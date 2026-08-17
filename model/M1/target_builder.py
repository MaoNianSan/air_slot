from model.common.enums import DecisionTimeRole, OperationalStage, SupportState
from model.common.errors import ContractError
from model.M1.contracts import M1TargetLabel
from model.PRE.cohort import split_for_date
from model.PRE.contracts.canonical import FlightRecord, OperationalEventRecord
from model.PRE.contracts.pre_state import DecisionNodeRecord, EpisodeRecord, TargetSupportState

def _active(support: dict[str, TargetSupportState], target: str, stage: OperationalStage) -> bool:
    if target not in support or not support[target].active \
            or support[target].support_state is SupportState.ABSTAIN:
        return False
    unresolved = {
        "R_IB": {OperationalStage.PRE_IB},
        "DELTA_OB": {OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB},
        "T_TX": {OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB,
                 OperationalStage.POST_OB_PRE_TO},
    }
    return stage in unresolved[target]


def build_target_labels(*, episode: EpisodeRecord, node: DecisionNodeRecord,
                              predecessor_outcome: OperationalEventRecord,
                              successor_schedule: FlightRecord,
                              successor_outcome: OperationalEventRecord,
                              target_support: tuple[TargetSupportState, ...]) -> tuple[M1TargetLabel, ...]:
    typed = (episode, node, predecessor_outcome, successor_schedule, successor_outcome)
    if any(item is None for item in typed):
        raise ContractError("M1_TYPED_TARGET_INPUT_REQUIRED")
    dataset_ids = {
        episode.dataset_instance_id,
        successor_schedule.dataset_instance_id,
        predecessor_outcome.dataset_instance_id,
        successor_outcome.dataset_instance_id,
    }
    if len(dataset_ids) != 1:
        raise ContractError("M1_TARGET_DATASET_IDENTITY_MISMATCH")
    if predecessor_outcome.decision_time_role not in {DecisionTimeRole.TRAIN_LABEL,
            DecisionTimeRole.EVAL_OUTCOME} or successor_outcome.decision_time_role not in {
            DecisionTimeRole.TRAIN_LABEL, DecisionTimeRole.EVAL_OUTCOME}:
        raise ContractError("M1_TARGET_OUTCOME_ROLE_INVALID")
    if predecessor_outcome.flight_id != episode.predecessor_flight_id \
            or successor_outcome.flight_id != episode.successor_flight_id \
            or successor_schedule.flight_id != episode.successor_flight_id \
            or node.episode_id != episode.episode_id:
        raise ContractError("M1_TARGET_EPISODE_IDENTITY_MISMATCH")
    if successor_schedule.service_date is None:
        raise ContractError("M1_TARGET_SPLIT_DATE_MISSING")
    predecessor_complete = not predecessor_outcome.cancelled and not predecessor_outcome.diverted
    successor_complete = not successor_outcome.cancelled and not successor_outcome.diverted
    continuous = {
        "R_IB": None if not predecessor_complete or predecessor_outcome.actual_arrival_utc is None else max(0.0,
            (predecessor_outcome.actual_arrival_utc - node.decision_time).total_seconds() / 60.0),
        "DELTA_OB": None if not successor_complete or successor_outcome.actual_departure_utc is None
            or successor_schedule.scheduled_departure_utc is None else (
            (successor_outcome.actual_departure_utc - successor_schedule.scheduled_departure_utc).total_seconds() / 60.0),
        "T_TX": successor_outcome.taxi_out_minutes if successor_complete else None,
    }
    support = {item.target_name: item for item in target_support}
    result = []
    for target in ("R_IB", "DELTA_OB", "T_TX"):
        active = _active(support, target, node.operational_stage) and continuous[target] is not None
        if active and target != "DELTA_OB" and continuous[target] < 0:
            raise ContractError("M1_TARGET_NEGATIVE")
        result.append(M1TargetLabel(target_name=target, active=active,
            exact_minutes=continuous[target] if active else None,
            support=support[target].support_state.value if target in support else "ABSTAIN",
            episode_id=episode.episode_id, decision_node_id=node.decision_node_id,
            target_definition_id=f"{target}_V1", target_definition_version="1.0.0",
            label_status="EXACT" if active else "INACTIVE",
            abstention_reason=None if active else (
                "TARGET_OBSERVED_AT_STAGE" if continuous[target] is not None
                else "REALIZED_OUTCOME_UNAVAILABLE"),
            provenance=(predecessor_outcome.provenance,) if target == "R_IB"
                else (successor_schedule.provenance, successor_outcome.provenance) if target == "DELTA_OB"
                else (successor_outcome.provenance,),
            split=split_for_date(successor_schedule.service_date),
            episode_date=successor_schedule.service_date))
    return tuple(result)


# Adapter/validation callers from the previous release may retain this name;
# it is an alias only and contains no dataset-specific scientific branch.
build_data2_target_labels = build_target_labels
