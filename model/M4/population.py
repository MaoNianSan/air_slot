from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from model.common.enums import OperationalStage
from model.common.errors import ContractError
from model.common.identity import content_id

from .contracts import (
    ExcludedNode,
    PopulationScope,
    PriorityPopulation,
    PriorityScoreRecord,
)
from .priority import AGGREGATION_CONTRACT_ID


def build_population(
    records: tuple[PriorityScoreRecord, ...],
    scope: PopulationScope,
) -> PriorityPopulation:
    records = tuple(records)
    if len({item.decision_node_id for item in records}) != len(records):
        raise ContractError("M4_POPULATION_ID_DUPLICATE")
    if records:
        input_basis = (
            records[0].policy_id,
            records[0].cu_registry_digest,
            records[0].aggregation_contract_id,
        )
        if any(
            (item.policy_id, item.cu_registry_digest, item.aggregation_contract_id)
            != input_basis
            for item in records
        ):
            raise ContractError("M4_COMPARISON_BASIS_MISMATCH")
    if scope.kind == "LIVE_EPOCH":
        if any(item.decision_time != scope.decision_time for item in records):
            raise ContractError("M4_POPULATION_TIME_MISMATCH")
        if len({item.episode_id for item in records}) != len(records):
            raise ContractError("M4_POPULATION_EPISODE_DUPLICATE")
        selected = tuple(
            item
            for item in records
            if item.comparative_eligible
            and item.operational_stage is not OperationalStage.COMPLETED
        )
        excluded = tuple(
            ExcludedNode(
                episode_id=item.episode_id,
                decision_node_id=item.decision_node_id,
                reason_code=(
                    "M4_COMPLETED_STAGE_EXCLUDED"
                    if item.operational_stage is OperationalStage.COMPLETED
                    else item.eligibility_reasons[0]
                    if item.eligibility_reasons
                    else "M4_NOT_COMPARATIVELY_ELIGIBLE"
                ),
                decision_time=item.decision_time,
            )
            for item in records
            if not item.comparative_eligible
        )
        is_live = True
    else:
        if any(item.operational_stage is not scope.stage for item in records):
            raise ContractError("M4_POPULATION_STAGE_MISMATCH")
        grouped: dict[str, list[PriorityScoreRecord]] = defaultdict(list)
        for item in records:
            grouped[item.episode_id].append(item)
        canonical: list[PriorityScoreRecord] = []
        excluded_items: list[ExcludedNode] = []
        for episode_id, items in grouped.items():
            ordered = sorted(items, key=lambda item: (item.decision_time, item.decision_node_id))
            first = ordered[0]
            canonical.append(first)
            excluded_items.extend(
                ExcludedNode(
                    episode_id=item.episode_id,
                    decision_node_id=item.decision_node_id,
                    reason_code="M4_RETROSPECTIVE_NOT_CANONICAL_EARLIEST_NODE",
                    decision_time=item.decision_time,
                )
                for item in ordered[1:]
            )
        selected = tuple(
            item
            for item in canonical
            if item.comparative_eligible
            and item.operational_stage is not OperationalStage.COMPLETED
        )
        excluded_items.extend(
            ExcludedNode(
                episode_id=item.episode_id,
                decision_node_id=item.decision_node_id,
                reason_code=(
                    "M4_COMPLETED_STAGE_EXCLUDED"
                    if item.operational_stage is OperationalStage.COMPLETED
                    else item.eligibility_reasons[0]
                    if item.eligibility_reasons
                    else "M4_NOT_COMPARATIVELY_ELIGIBLE"
                ),
                decision_time=item.decision_time,
            )
            for item in canonical
            if not item.comparative_eligible
        )
        excluded = tuple(sorted(excluded_items, key=lambda item: item.decision_node_id))
        is_live = False
    selected = tuple(sorted(selected, key=lambda item: item.decision_node_id))
    if len({item.decision_node_id for item in selected}) != len(selected):
        raise ContractError("M4_POPULATION_ID_DUPLICATE")
    if selected:
        basis = (
            selected[0].policy_id,
            selected[0].cu_registry_digest,
            selected[0].aggregation_contract_id,
        )
    else:
        basis = (
            records[0].policy_id if records else "",
            records[0].cu_registry_digest if records else "",
            records[0].aggregation_contract_id if records else AGGREGATION_CONTRACT_ID,
        )
    payload = {
        "scope": scope.model_dump(mode="json"),
        "policy_id": basis[0],
        "cu_registry_digest": basis[1],
        "aggregation_contract_id": basis[2],
        "records": tuple(
            (item.episode_id, item.decision_node_id, item.input_digest)
            for item in sorted(selected, key=lambda x: x.decision_node_id)
        ),
    }
    return PriorityPopulation(
        records=selected,
        excluded=excluded,
        scope=scope,
        population_digest=content_id(payload),
        policy_id=basis[0],
        cu_registry_digest=basis[1],
        aggregation_contract_id=basis[2],
        is_live_queue=is_live,
    )


__all__ = ["build_population"]
