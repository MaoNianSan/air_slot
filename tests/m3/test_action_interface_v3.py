from datetime import datetime, timezone

from model.M3 import (
    ActionInterfaceRequest,
    CandidateActionSetState,
    M3Service,
    MaterializationState,
    ResourceContext,
    ResourceContextState,
)
from model.M2.contracts import M2ScenarioInput
from model.PRE.contracts.pre_state import DecisionNodeRecord
from model.common.enums import OperationalStage, SupportState


def _request():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    node = DecisionNodeRecord(
        decision_node_id="N1",
        episode_id="E1",
        decision_time=now,
        information_cutoff=now,
        operational_stage=OperationalStage.PRE_IB,
        roll_minutes=60,
        node_index=0,
        status="CONSTRUCTED",
        formal_eligible=True,
        config_hash="config",
        registry_manifest_hash="manifest",
        legal_record_ids=("record",),
    )
    scenario = M2ScenarioInput.model_construct(
        episode_id="E1",
        decision_node_id="N1",
        scenario_id=0,
        scenario_weight=1.0,
        t_ib_a00_utc=None,
        r_ib_minutes=0.0,
        d_ob_minutes=0.0,
        d_tx_minutes=0.0,
        d_to_minutes=0.0,
        r_ib_support=SupportState.SUPPORTED,
        d_ob_support=SupportState.SUPPORTED,
        d_tx_support=SupportState.SUPPORTED,
        d_to_support=SupportState.SUPPORTED,
        pre_lineage=("synthetic",),
        reference_lineage=("synthetic",),
        m1_scenario_seed_key="seed",
    )
    context = object()
    request = ActionInterfaceRequest.model_construct(
        node=node,
        baseline_scenarios=(scenario,),
        consequence_context=context,
        resource_context=ResourceContext(state=ResourceContextState.UNKNOWN),
        request_digest="synthetic-request",
    )
    return request


def test_default_service_exposes_a00_without_materializing_non_a00():
    request = _request()
    service = M3Service()
    candidates = service.candidate_actions(request=request)
    assert candidates.state is CandidateActionSetState.NOT_MATERIALIZED
    state = service.transition_state(
        request=request, candidates=candidates, action_id="A00"
    )
    assert state.state is MaterializationState.MATERIALIZED
    assert state.scenarios == request.baseline_scenarios
    result = service.evaluate_post_action(request=request, state=state)
    assert result.state is MaterializationState.NOT_MATERIALIZED
    assert result.reason_codes == ("M3_CONSEQUENCE_PROVIDER_MISSING",)
