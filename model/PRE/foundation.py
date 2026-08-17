from datetime import datetime
from model.common.enums import EvidenceClass, SupportState
from model.common.value_objects import FrozenModel, SupportedValue
from model.PRE.contracts.pre_state import (EvidenceLedgerEntry, PREState, ReferenceState,
                                           TargetSupportState, VariableLineageEntry)
from model.PRE.episode.node_builder import build_decision_node


class PREBuildRequest(FrozenModel):
    episode_id: str
    predecessor_id: str
    successor_id: str
    decision_time: datetime
    information_cutoff: datetime
    config_hash: str
    registry_hash: str
    legal_record_ids: tuple[str, ...] = ()
    dataset_instance_id: str


class PREBuildResult(FrozenModel):
    pre_state: PREState
    FIXTURE_ONLY: bool = True
    paper_result: bool = False
    evaluation_scope: str = "FOUNDATION_ONLY"


def _value(value, evidence=EvidenceClass.DIRECT, ceiling=EvidenceClass.DIRECT):
    return SupportedValue(value=value, unit="canonical", evidence_class=evidence,
        support_ceiling=ceiling, support_state=SupportState.SUPPORTED)


def build_pre_state(request: PREBuildRequest) -> PREBuildResult:
    node = build_decision_node(episode_id=request.episode_id,
        predecessor_id=request.predecessor_id, successor_id=request.successor_id,
        decision_time=request.decision_time, information_cutoff=request.information_cutoff,
        config_hash=request.config_hash, registry_hash=request.registry_hash,
        legal_record_ids=request.legal_record_ids)
    r_ob_supported = request.dataset_instance_id == "data2_2019"
    targets = (
        TargetSupportState(target_name="R_IB", active=True, support_state=SupportState.SUPPORTED,
            target_definition_id="R_IB_V1", dataset_ceiling=EvidenceClass.DIRECT,
            formal_input_support=EvidenceClass.DIRECT, realized_outcome_support=EvidenceClass.DERIVED),
        TargetSupportState(target_name="DELTA_OB", active=r_ob_supported,
            support_state=SupportState.SUPPORTED if r_ob_supported else SupportState.ABSTAIN,
            target_definition_id="DELTA_OB_V1",
            dataset_ceiling=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.UNSUPPORTED,
            formal_input_support=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.UNSUPPORTED,
            realized_outcome_support=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.DERIVED,
            abstention_reason=None if r_ob_supported else "TARGET_SEMANTICS_UNSUPPORTED"),
        TargetSupportState(target_name="T_TX", active=True, support_state=SupportState.SUPPORTED,
            target_definition_id="T_TX_V1", dataset_ceiling=EvidenceClass.DERIVED,
            formal_input_support=EvidenceClass.DERIVED, realized_outcome_support=EvidenceClass.DERIVED),
    )
    motion = _value(0)
    weather = _value(10, EvidenceClass.DERIVED, EvidenceClass.DIRECT)
    ledger = (
        EvidenceLedgerEntry(decision_node_id=node.decision_node_id, scientific_object="predecessor_motion",
            source_name="fixture_motion", source_record_id="motion-1", event_time=request.information_cutoff,
            availability_time=request.information_cutoff, availability_basis="REPLAY_EVENT_TIME",
            decision_time_role="INFERENCE_EVIDENCE", evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT, episode_support=SupportState.SUPPORTED),
        EvidenceLedgerEntry(decision_node_id=node.decision_node_id, scientific_object="current_weather",
            source_name="fixture_weather", source_record_id="weather-1", event_time=request.information_cutoff,
            availability_time=request.information_cutoff, availability_basis="REPLAY_EVENT_TIME",
            decision_time_role="INFERENCE_EVIDENCE", evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DIRECT, episode_support=SupportState.SUPPORTED),
    )
    lineage = (
        VariableLineageEntry(decision_node_id=node.decision_node_id, scientific_variable="predecessor_motion",
            supported_value=motion, canonical_variable="predecessor_motion", rule_id="D1-OPENSKY-STATE",
            source_name="fixture_motion", source_record_id="motion-1", event_time=request.information_cutoff,
            availability_time=request.information_cutoff, availability_basis="REPLAY_EVENT_TIME"),
        VariableLineageEntry(decision_node_id=node.decision_node_id, scientific_variable="current_weather",
            supported_value=weather, canonical_variable="current_weather", rule_id="D1-METAR",
            source_name="fixture_weather", source_record_id="weather-1", event_time=request.information_cutoff,
            availability_time=request.information_cutoff, availability_basis="REPLAY_EVENT_TIME"),
    )
    return PREBuildResult(pre_state=PREState(decision_node=node,
        predecessor_state={"motion": motion}, current_state={"weather": weather},
        successor_state={}, evidence_ledger=ledger, variable_lineage=lineage,
        reference_state=ReferenceState(entries={}), target_support=targets))
