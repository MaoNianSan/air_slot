from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from model.M1.contracts import AlignedScenario
from model.M4.contracts import M4DecisionRequest
from model.M4.decision import evaluate_request
from model.M4.response import response_value
from model.PRE.foundation import PREBuildRequest, build_pre_state
from tests.fixtures.p0_p1_contracts import (
    candidate,
    consequence,
    coverage_contract,
    monetary_fixture,
    monetary_fixture_hash,
    scope_fixture,
)


def pre_and_scenario():
    pre = build_pre_state(
        PREBuildRequest(
            episode_id="e",
            predecessor_id="P",
            successor_id="S",
            decision_time=datetime(2019, 1, 1, 12, tzinfo=timezone.utc),
            information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=timezone.utc),
            config_hash="sha256:c",
            registry_hash="sha256:r",
            dataset_instance_id="data2_2019",
        )
    ).pre_state
    scenario = AlignedScenario(
        episode_id="e",
        decision_node_id=pre.decision_node.decision_node_id,
        scenario_id=0,
        scenario_weight=1,
        operational_stage="PRE_IB",
        r_ib_minutes=5,
        delta_ob_minutes=5,
        t_tx_minutes=5,
        ib_observed=False,
        delta_ob_observed=False,
        ib_support="SUPPORTED",
        delta_ob_support="SUPPORTED",
        tx_support="SUPPORTED",
        overflow_ib=False,
        overflow_delta_ob=False,
        overflow_tx=False,
        scenario_seed_key="k",
    )
    return pre, scenario


def test_bernoulli_beta_is_stochastic_stable_and_shared_across_components():
    action = candidate("A11").model_copy(
        update={
            "response_model": "BERNOULLI_BETA",
            "response_parameters": {
                "failure_probability": 0.0,
                "mean_intensity": 0.5,
                "concentration": 4.0,
            },
        }
    )
    values = [response_value(action, seed=11, episode="e", scenario=s) for s in range(20)]
    assert values == [
        response_value(action, seed=11, episode="e", scenario=s, component="P_time")
        for s in range(20)
    ]
    assert len({round(value, 8) for value in values}) > 1


def test_typed_request_preserves_lineage_and_allows_non_scope_abstain():
    pre, scenario = pre_and_scenario()
    scope = scope_fixture()
    raw = consequence(scope=scope, missing=("P_service",))
    consequence_row = raw.model_copy(update={"decision_node_id": pre.decision_node.decision_node_id})
    request = M4DecisionRequest(
        pre_state=pre,
        m1_scenarios=(scenario,),
        m2_consequences=(consequence_row,),
        candidates=(candidate("A00"), candidate("A11")),
        material_coverage_contract=coverage_contract(p_service_nonmaterial=True),
        monetary_system="RMB",
        monetary_mapping_registry_id="TEST-RMB-V1",
        monetary_mapping_registry_hash=monetary_fixture_hash(),
        seed=3,
    )
    result = evaluate_request(request, monetary_mapping=monetary_fixture())
    assert result.ranking_at_1 == "A11:instance-0"
    assert next(item for item in result.actions if item.template_id == "A00").post_totals == (10.0,)


def test_request_rejects_mixed_scopes_explicitly():
    pre, scenario = pre_and_scenario()
    first = consequence(scope=scope_fixture())
    second_scope = scope_fixture(estimand_id="OTHER")
    second = consequence(scenario_id=1, scope=second_scope).model_copy(
        update={"scenario_weight": 1.0}
    )
    scenario2 = scenario.model_copy(update={"scenario_id": 1})
    first = first.model_copy(update={"decision_node_id": pre.decision_node.decision_node_id})
    second = second.model_copy(update={"decision_node_id": pre.decision_node.decision_node_id})
    with pytest.raises(ValidationError, match="M4_COMMON_ESTIMAND_SCOPE_MISMATCH"):
        M4DecisionRequest(
            pre_state=pre,
            m1_scenarios=(scenario, scenario2),
            m2_consequences=(first, second),
            candidates=(candidate("A00"),),
            material_coverage_contract=coverage_contract(),
            monetary_system="RMB",
            monetary_mapping_registry_id="TEST-RMB-V1",
            monetary_mapping_registry_hash=monetary_fixture_hash(),
        )
