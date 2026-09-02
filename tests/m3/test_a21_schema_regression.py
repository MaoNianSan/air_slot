"""A21 schedule alias and contract-under-specified regression."""

from pathlib import Path

from model.M3.factual_adapter import FactualState, adapt_pre_state
from model.M3.instantiate import instantiate_action_records
from model.M3.registry import ActionRegistry
from model.PRE.contracts.pre_state import DecisionNodeRecord, PREState
from model.common.enums import EvidenceClass, OperationalStage, SupportState
from model.common.value_objects import SupportedValue


def _pre() -> PREState:
    node = DecisionNodeRecord(
        decision_node_id="node-a21", episode_id="episode-a21",
        decision_time="2019-01-01T00:00:00+00:00",
        information_cutoff="2019-01-01T00:00:00+00:00",
        operational_stage=OperationalStage.POST_IB_PRE_OB, roll_minutes=15,
        node_index=0, status="CONSTRUCTED", formal_eligible=True,
        config_hash="sha256:config", registry_manifest_hash="sha256:registry",
        legal_record_ids=(),
    )
    schedule = SupportedValue(
        value={"departure": "12:00"}, unit="schedule",
        evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
        support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
        support_state=SupportState.SUPPORTED,
    )
    return PREState(decision_node=node, successor_state={"schedule_reference": schedule}, reference_state={})


def test_a21_schedule_reference_is_explicitly_adapted_but_facts_stay_unknown():
    pre = _pre()
    adapted = adapt_pre_state(pre)
    assert adapted.facts["successor_schedule"].state is FactualState.TRUE
    assert adapted.facts["successor_schedule"].source_key == "schedule_reference"
    registry = ActionRegistry.load(Path(__file__).resolve().parents[2] / "registries" / "action_templates.yaml")
    record = next(item for item in instantiate_action_records(pre, registry) if item.template_id == "A21")
    assert record.instantiation_state.value == "FORMED"
    assert record.candidate is not None
    assert record.candidate.precondition_state == "UNKNOWN"
    assert record.candidate.precondition_reason == "CONTRACT_UNDERSPECIFIED"
