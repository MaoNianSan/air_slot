from datetime import datetime, timezone
from pathlib import Path

import torch

from model import M1, M2, M3, M4, PRE
from model.M2.contracts import M2ScientificContext, ScientificContextValue
from model.M2.mapper import M2Mapper
from model.M2.valuation import ValuationRegistry
from model.PRE.transformation import ConstructionType
from model.common.enums import EvidenceClass, SupportState
from tests.fixtures.p0_p1_contracts import candidate, consequence, coverage_contract, scope_fixture
from tests.fixtures.pre.foundation_cases import build_request


def _unsupported_context() -> M2ScientificContext:
    values = {name: ScientificContextValue(
        object_id=name, value=None, unit="unit", support_state=SupportState.ABSTAIN,
        evidence_class=EvidenceClass.UNSUPPORTED,
        construction_type=ConstructionType.UNSUPPORTED, reason_code="NOT_FROZEN")
        for name in M2ScientificContext.model_fields}
    return M2ScientificContext(**values)


def test_refactor_behavioral_equivalence_across_pre_m4():
    direct_pre = PRE.build_pre_state(build_request()).pre_state
    repeated_pre = PRE.build_pre_state(build_request()).pre_state
    assert direct_pre.model_dump(mode="json") == repeated_pre.model_dump(mode="json")
    assert direct_pre.decision_node.decision_node_id == repeated_pre.decision_node.decision_node_id
    assert [item.support_state for item in direct_pre.target_support] == [
        item.support_state for item in repeated_pre.target_support]
    assert [item.source_record_id for item in direct_pre.variable_lineage] == [
        item.source_record_id for item in repeated_pre.variable_lineage]

    pipeline = M1.M1Pipeline.smoke(input_size=4)
    values, lengths = torch.zeros(1, 2, 4), torch.tensor([2])
    distributions = pipeline.predict_distributions(values, lengths)
    scenarios = pipeline.sample_aligned(distributions, episode_id="episode", decision_node_id="node",
        stage="PRE_IB", observed={}, count=4, seed=11)
    repeated = pipeline.sample_aligned(distributions, episode_id="episode", decision_node_id="later",
        stage="PRE_IB", observed={}, count=4, seed=11)
    assert [row.scenario_id for row in scenarios] == [0, 1, 2, 3]
    assert [row.scenario_seed_key for row in scenarios] == [row.scenario_seed_key for row in repeated]
    assert [row.d_to_minutes for row in scenarios] == [None] * len(scenarios)

    m2_scenarios = ({"decision_node_id": "node", "scenario_id": 0, "scenario_weight": 1.0,
                     "r_ib_minutes": 10, "delta_ob_minutes": 5, "t_tx_minutes": 15,
                     "d_ob_minutes": 5, "d_tx_minutes": 0, "d_to_minutes": 5,
                     "ib_support": "SUPPORTED", "delta_ob_support": "SUPPORTED",
                     "tx_support": "SUPPORTED", "d_ob_support": "SUPPORTED",
                     "d_tx_support": "SUPPORTED", "d_to_support": "SUPPORTED"},)
    registry = ValuationRegistry.smoke()
    scope = scope_fixture(cu_normalization_registry_id="DEV-1")
    direct_m2 = M2Mapper(registry, scope).map_scenarios(m2_scenarios, _unsupported_context())
    public_m2 = M2.map_pre_action_consequence(m2_scenarios, _unsupported_context(),
                                               registry=registry, consequence_scope=scope)
    assert [row.model_dump(mode="json") for row in public_m2] == [
        row.model_dump(mode="json") for row in direct_m2]

    action_registry = M3.ActionRegistry.load(Path("registries/action_templates.yaml"))
    m3_candidates = M3.instantiate_candidates({"episode_id": "episode", "decision_node_id": "node",
                                                "facts": {}, "parameters": {}}, action_registry)
    assert m3_candidates[0].template_id == "A00"
    assert len({row.candidate_action_id for row in m3_candidates}) == len(m3_candidates)

    from tests.fixtures.p0_p1_contracts import monetary_fixture

    decision = M4.evaluate_decision("episode",
        [{"scenario_id": 0, "scenario_weight": 1.0, "deadline_minutes": 30}],
        (consequence(),), (candidate("A00"), candidate("A11")),
        material_coverage_contract=coverage_contract(),
        monetary_mapping=monetary_fixture())
    assert [row.template_id for row in decision.actions] == ["A00", "A11"]
    assert decision.actions[0].post_totals == (10.0,)
    assert decision.actions[1].residual_risk_j == 5.0
    assert decision.authoritative_ranking == ("A11:instance-0", "A00:instance-0")
