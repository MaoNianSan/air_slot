from model.common.enums import DecisionTimeRole, OperationalStage, SupportState
from model.common.errors import ContractError
from model.M1.contracts import M1TargetLabel, M1V2TargetLabel, V2_TARGETS
from model.M1.semantics import M1_V2_HAZARD_COORDINATE_TARGET
from model.PRE import split_for_date
from model.common.value_objects import ProvenanceRef
from model.PRE import FlightRecord, OperationalEventRecord
from model.PRE import (
    DecisionNodeRecord,
    EpisodeRecord,
    TargetSupportState,
)


def _active(
    support: dict[str, TargetSupportState], target: str, stage: OperationalStage
) -> bool:
    if (
        target not in support
        or not support[target].active
        or support[target].support_state is SupportState.ABSTAIN
    ):
        return False
    unresolved = {
        "R_IB": {OperationalStage.PRE_IB},
        "DELTA_OB": {OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB},
        "T_TX": {
            OperationalStage.PRE_IB,
            OperationalStage.POST_IB_PRE_OB,
            OperationalStage.POST_OB_PRE_TO,
        },
    }
    return stage in unresolved[target]


def build_target_labels(
    *,
    episode: EpisodeRecord,
    node: DecisionNodeRecord,
    predecessor_outcome: OperationalEventRecord,
    successor_schedule: FlightRecord,
    successor_outcome: OperationalEventRecord,
    target_support: tuple[TargetSupportState, ...],
) -> tuple[M1TargetLabel, ...]:
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
    if predecessor_outcome.decision_time_role not in {
        DecisionTimeRole.TRAIN_LABEL,
        DecisionTimeRole.EVAL_OUTCOME,
    } or successor_outcome.decision_time_role not in {
        DecisionTimeRole.TRAIN_LABEL,
        DecisionTimeRole.EVAL_OUTCOME,
    }:
        raise ContractError("M1_TARGET_OUTCOME_ROLE_INVALID")
    if (
        predecessor_outcome.flight_id != episode.predecessor_flight_id
        or successor_outcome.flight_id != episode.successor_flight_id
        or successor_schedule.flight_id != episode.successor_flight_id
        or node.episode_id != episode.episode_id
    ):
        raise ContractError("M1_TARGET_EPISODE_IDENTITY_MISMATCH")
    if successor_schedule.service_date is None:
        raise ContractError("M1_TARGET_SPLIT_DATE_MISSING")
    predecessor_complete = (
        not predecessor_outcome.cancelled and not predecessor_outcome.diverted
    )
    successor_complete = (
        not successor_outcome.cancelled and not successor_outcome.diverted
    )
    continuous = {
        "R_IB": (
            None
            if not predecessor_complete
            or predecessor_outcome.actual_arrival_utc is None
            else max(
                0.0,
                (
                    predecessor_outcome.actual_arrival_utc - node.decision_time
                ).total_seconds()
                / 60.0,
            )
        ),
        "DELTA_OB": (
            None
            if not successor_complete
            or successor_outcome.actual_departure_utc is None
            or successor_schedule.scheduled_departure_utc is None
            else (
                (
                    successor_outcome.actual_departure_utc
                    - successor_schedule.scheduled_departure_utc
                ).total_seconds()
                / 60.0
            )
        ),
        "T_TX": successor_outcome.taxi_out_minutes if successor_complete else None,
    }
    support = {item.target_name: item for item in target_support}
    result = []
    for target in ("R_IB", "DELTA_OB", "T_TX"):
        active = (
            _active(support, target, node.operational_stage)
            and continuous[target] is not None
        )
        if active and target != "DELTA_OB" and continuous[target] < 0:
            raise ContractError("M1_TARGET_NEGATIVE")
        result.append(
            M1TargetLabel(
                target_name=target,
                active=active,
                exact_minutes=continuous[target] if active else None,
                support=(
                    support[target].support_state.value
                    if target in support
                    else "ABSTAIN"
                ),
                episode_id=episode.episode_id,
                decision_node_id=node.decision_node_id,
                target_definition_id=f"{target}_V1",
                target_definition_version="1.0.0",
                label_status="EXACT" if active else "INACTIVE",
                abstention_reason=(
                    None
                    if active
                    else (
                        "TARGET_OBSERVED_AT_STAGE"
                        if continuous[target] is not None
                        else "REALIZED_OUTCOME_UNAVAILABLE"
                    )
                ),
                provenance=(
                    (predecessor_outcome.provenance,)
                    if target == "R_IB"
                    else (
                        (successor_schedule.provenance, successor_outcome.provenance)
                        if target == "DELTA_OB"
                        else (successor_outcome.provenance,)
                    )
                ),
                split=split_for_date(successor_schedule.service_date),
                episode_date=successor_schedule.service_date,
            )
        )
    return tuple(result)


# Adapter/validation callers from the previous release may retain this name;
# it is an alias only and contains no dataset-specific scientific branch.
build_data2_target_labels = build_target_labels


# ---------------------------------------------------------------------------
# V2 labels (Round-2 M1 V2 real estimator).
# ---------------------------------------------------------------------------

V2_STAGE_ACTIVE = {
    M1_V2_HAZARD_COORDINATE_TARGET: frozenset({OperationalStage.PRE_IB}),
    "D_OB": frozenset({OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB}),
    "D_TX": frozenset(
        {
            OperationalStage.PRE_IB,
            OperationalStage.POST_IB_PRE_OB,
            OperationalStage.POST_OB_PRE_TO,
        }
    ),
}

# PRE target-support names (V1) mapped onto V2 INTERNAL training-target names.
# The predecessor hazard label is the internal remaining-time coordinate
# (T_IB_REMAINING_HAZARD); the public absolute T_IB_A00 is carried by the
# label's ``t_ib_a00_utc`` field.
V2_SUPPORT_MAP = {
    "R_IB": M1_V2_HAZARD_COORDINATE_TARGET,
    "DELTA_OB": "D_OB",
    "T_TX": "D_TX",
}


def _v2_active(
    support: dict[str, TargetSupportState], target: str, stage: OperationalStage
) -> bool:
    if (
        target not in support
        or not support[target].active
        or support[target].support_state is SupportState.ABSTAIN
    ):
        return False
    return stage in V2_STAGE_ACTIVE[target]


def build_v2_target_labels(
    *,
    episode: EpisodeRecord,
    node: DecisionNodeRecord,
    predecessor_outcome: OperationalEventRecord,
    successor_schedule: FlightRecord,
    successor_outcome: OperationalEventRecord,
    target_support: tuple[TargetSupportState, ...],
    taxi_reference_minutes: float | None = None,
    taxi_reference_id: str | None = None,
    taxi_reference_hash: str | None = None,
) -> tuple[M1V2TargetLabel, ...]:
    """V2 training labels for T_IB_REMAINING_HAZARD / D_OB / D_TX.

    The predecessor hazard label is the INTERNAL remaining-time coordinate
    ``max(0, actual_arrival - decision_time)``; its public absolute event
    time ``T_IB_A00`` (ISO UTC) and the decision time are retained on the
    label so past events with R_IB == 0 stay distinguishable.
    D_OB = max(0, actual_departure - scheduled_departure).
    D_TX = max(0, taxi_out - taxi_reference); without the train-frozen taxi
    reference the D_TX label abstains.
    """
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
    if predecessor_outcome.decision_time_role not in {
        DecisionTimeRole.TRAIN_LABEL,
        DecisionTimeRole.EVAL_OUTCOME,
    } or successor_outcome.decision_time_role not in {
        DecisionTimeRole.TRAIN_LABEL,
        DecisionTimeRole.EVAL_OUTCOME,
    }:
        raise ContractError("M1_TARGET_OUTCOME_ROLE_INVALID")
    if (
        predecessor_outcome.flight_id != episode.predecessor_flight_id
        or successor_outcome.flight_id != episode.successor_flight_id
        or successor_schedule.flight_id != episode.successor_flight_id
        or node.episode_id != episode.episode_id
    ):
        raise ContractError("M1_TARGET_EPISODE_IDENTITY_MISMATCH")
    if successor_schedule.service_date is None:
        raise ContractError("M1_TARGET_SPLIT_DATE_MISSING")
    predecessor_complete = (
        not predecessor_outcome.cancelled and not predecessor_outcome.diverted
    )
    successor_complete = (
        not successor_outcome.cancelled and not successor_outcome.diverted
    )
    continuous = {
        M1_V2_HAZARD_COORDINATE_TARGET: (
            None
            if not predecessor_complete
            or predecessor_outcome.actual_arrival_utc is None
            else max(
                0.0,
                (
                    predecessor_outcome.actual_arrival_utc - node.decision_time
                ).total_seconds()
                / 60.0,
            )
        ),
        "D_OB": (
            None
            if not successor_complete
            or successor_outcome.actual_departure_utc is None
            or successor_schedule.scheduled_departure_utc is None
            else max(
                0.0,
                (
                    (
                        successor_outcome.actual_departure_utc
                        - successor_schedule.scheduled_departure_utc
                    ).total_seconds()
                    / 60.0
                ),
            )
        ),
        "D_TX": (
            None
            if not successor_complete
            or successor_outcome.taxi_out_minutes is None
            or taxi_reference_minutes is None
            else max(
                0.0,
                float(successor_outcome.taxi_out_minutes)
                - float(taxi_reference_minutes),
            )
        ),
    }
    v1_support = {item.target_name: item for item in target_support}
    support = {
        V2_SUPPORT_MAP[name]: item
        for name, item in v1_support.items()
        if name in V2_SUPPORT_MAP
    }
    result = []
    for target in V2_TARGETS:
        active = (
            _v2_active(support, target, node.operational_stage)
            and continuous[target] is not None
        )
        support_state = (
            support[target].support_state.value
            if target in support
            and support[target].support_state is not SupportState.ABSTAIN
            else "ABSTAIN"
        )
        if target == "D_TX" and taxi_reference_minutes is None:
            support_state = "ABSTAIN"
        if active and continuous[target] is not None and continuous[target] < 0:
            raise ContractError("M1_TARGET_NEGATIVE")
        if continuous[target] is not None and continuous[target] < 0:
            raise ContractError("M1_TARGET_NEGATIVE")
        if active:
            abstention_reason = None
        elif continuous[target] is not None:
            abstention_reason = "TARGET_OBSERVED_AT_STAGE"
        elif target == "D_TX" and taxi_reference_minutes is None:
            abstention_reason = "TAXI_REFERENCE_UNAVAILABLE"
        else:
            abstention_reason = "REALIZED_OUTCOME_UNAVAILABLE"
        if target == M1_V2_HAZARD_COORDINATE_TARGET:
            provenance = (predecessor_outcome.provenance,)
        elif target == "D_OB":
            provenance = (successor_schedule.provenance, successor_outcome.provenance)
        else:
            provenance = (successor_outcome.provenance,)
        if (
            target == "D_TX"
            and taxi_reference_id is not None
            and taxi_reference_hash is not None
        ):
            provenance = provenance + (
                ProvenanceRef(
                    dataset_instance_id="data2_2019",
                    logical_source="data2_taxi_reference",
                    source_record_id=taxi_reference_id,
                    rule_id="DATA2_TAXI_REFERENCE",
                    source_version=taxi_reference_hash,
                ),
            )
        t_ib_a00_utc = None
        decision_time_utc = None
        if target == M1_V2_HAZARD_COORDINATE_TARGET:
            if (
                predecessor_complete
                and predecessor_outcome.actual_arrival_utc is not None
            ):
                # Public identity is preserved even when the remaining time is
                # already zero (past event): R_IB == 0 never erases the event.
                t_ib_a00_utc = predecessor_outcome.actual_arrival_utc.isoformat()
                decision_time_utc = node.decision_time.isoformat()
        result.append(
            M1V2TargetLabel(
                target_name=target,
                active=active,
                exact_minutes=continuous[target] if active else None,
                support=support_state,
                episode_id=episode.episode_id,
                decision_node_id=node.decision_node_id,
                target_definition_id=f"{target}_V2",
                target_definition_version="2.0.0",
                label_status="EXACT" if active else "INACTIVE",
                abstention_reason=abstention_reason,
                provenance=provenance,
                split=split_for_date(successor_schedule.service_date),
                episode_date=successor_schedule.service_date,
                t_ib_a00_utc=t_ib_a00_utc,
                decision_time_utc=decision_time_utc,
            )
        )
    return tuple(result)
