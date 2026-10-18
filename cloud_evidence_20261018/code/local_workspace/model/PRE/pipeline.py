from datetime import datetime
from model.common.enums import EvidenceClass, SupportState
from model.common.value_objects import FrozenModel
from model.PRE.contracts.pre_state import PREState, ReferenceState, TargetSupportState
from model.PRE.episode.node_builder import build_decision_node
from model.PRE.evidence.publication import select_and_publish
from model.PRE.foundation import PREBuildResult


def _target_support(dataset_instance_id: str):
    r_ob_supported = dataset_instance_id == "data2_2019"
    return (
        TargetSupportState(target_name="R_IB", active=True, support_state=SupportState.SUPPORTED,
            target_definition_id="R_IB_V1", dataset_ceiling=EvidenceClass.DERIVED,
            formal_input_support=EvidenceClass.DERIVED, realized_outcome_support=EvidenceClass.DERIVED),
        TargetSupportState(target_name="R_OB", active=r_ob_supported,
            support_state=SupportState.SUPPORTED if r_ob_supported else SupportState.ABSTAIN,
            target_definition_id="R_OB_V1",
            dataset_ceiling=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.UNSUPPORTED,
            formal_input_support=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.UNSUPPORTED,
            realized_outcome_support=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.DERIVED,
            abstention_reason=None if r_ob_supported else "TARGET_SEMANTICS_UNSUPPORTED"),
        TargetSupportState(target_name="T_TX", active=True, support_state=SupportState.SUPPORTED,
            target_definition_id="T_TX_V1", dataset_ceiling=EvidenceClass.DERIVED,
            formal_input_support=EvidenceClass.DERIVED, realized_outcome_support=EvidenceClass.DERIVED),
    )


class ProductionPRERequest(FrozenModel):
    episode_id: str
    predecessor_id: str
    successor_id: str
    dataset_instance_id: str
    decision_time: datetime
    information_cutoff: datetime
    records: tuple[dict, ...]
    config_hash: str
    registry_hash: str


def publish_production_pre(request: ProductionPRERequest) -> PREBuildResult:
    provisional = build_decision_node(episode_id=request.episode_id, predecessor_id=request.predecessor_id,
        successor_id=request.successor_id, decision_time=request.decision_time,
        information_cutoff=request.information_cutoff, config_hash=request.config_hash,
        registry_hash=request.registry_hash, legal_record_ids=())
    current, ledger, lineage, ids = select_and_publish(request.records,
        cutoff=request.information_cutoff, decision_node_id=provisional.decision_node_id)
    node = build_decision_node(episode_id=request.episode_id, predecessor_id=request.predecessor_id,
        successor_id=request.successor_id, decision_time=request.decision_time,
        information_cutoff=request.information_cutoff, config_hash=request.config_hash,
        registry_hash=request.registry_hash, legal_record_ids=ids)
    # Re-key entries to final deterministic node identity.
    ledger = tuple(item.model_copy(update={"decision_node_id": node.decision_node_id}) for item in ledger)
    lineage = tuple(item.model_copy(update={"decision_node_id": node.decision_node_id}) for item in lineage)
    return PREBuildResult(pre_state=PREState(decision_node=node, current_state=current,
        evidence_ledger=ledger, variable_lineage=lineage, reference_state=ReferenceState(entries={}),
        target_support=_target_support(request.dataset_instance_id)), FIXTURE_ONLY=False,
        evaluation_scope="PRODUCTION")
