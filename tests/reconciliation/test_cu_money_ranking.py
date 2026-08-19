"""Tests E/F/G — CU normalization vs monetary mapping separation and ranking.

Test E: native q -> C^CU passes through CUNormalizationRegistry and is never
interpreted as money.  Test F: with unequal RMB weights, raw-CU ranking and
RMB-weighted ranking differ and M4 must use the RMB-weighted one.
Test G: a NOT_FROZEN monetary mapping yields no authoritative ranking and no
raw-CU fallback.
"""

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.cu_normalization import CUNormalizationRegistry
from model.M3.contracts import ResponseParameterStatus, ResponseProvenance
from model.M4.decision import evaluate_decision
from tests.fixtures.p0_p1_contracts import (
    candidate,
    consequence,
    coverage_contract,
    monetary_fixture,
    scope_fixture,
)


def test_e_cu_normalization_is_not_money():
    registry = CUNormalizationRegistry.from_scales(
        registry_id="TEST-CU-V1",
        version="1.0.0",
        freeze_id="sha256:freeze",
        reference_period="TRAIN-2019-H1",
        scales={component: 2.0 for component in CONSEQUENCE_COMPONENTS},
        provenance=("TEST",),
    )
    cu = registry.to_cu("F_execution", 10.0)
    assert cu == 5.0
    # CU is a unitless consequence value; the monetary registry is a separate
    # layer and is not consulted by CU normalization.
    assert registry.rule("F_execution").normalization_parameter == 2.0
    assert registry.final_test_access_count == 0


def _pre_cu(mapping):
    m1 = [{"scenario_id": 0, "scenario_weight": 1.0, "deadline_minutes": 30}]
    scope = scope_fixture(components=("F_execution", "R_operating"))
    rows = (
        consequence(
            scope=scope,
            values={"F_execution": 10.0, "R_operating": 10.0},
        ),
    )
    baseline = candidate("A00")
    # Action A reduces the resource burden; action B reduces F_execution.
    action_a = candidate(
        "A11", action_index=1, candidate_index=1,
        mitigation={"R_operating": 0.9},
        provenance=ResponseProvenance.OPERATOR_INDUSTRY,
        parameter_status=ResponseParameterStatus.FROZEN,
    )
    action_b = candidate(
        "A11", action_index=2, candidate_index=2,
        mitigation={"F_execution": 0.5},
        provenance=ResponseProvenance.OPERATOR_INDUSTRY,
        parameter_status=ResponseParameterStatus.FROZEN,
    )
    return evaluate_decision(
        "e", m1, rows, (baseline, action_a, action_b),
        material_coverage_contract=coverage_contract(resource_required=True),
        monetary_mapping=mapping,
    )


def test_f_rmb_weighted_ranking_differs_from_raw_cu_and_is_selected():
    unity = monetary_fixture(
        registry_id="TEST-RMB-UNITY",
        weights={component: 1.0 for component in CONSEQUENCE_COMPONENTS},
    )
    weighted = monetary_fixture(
        registry_id="TEST-RMB-WEIGHTED",
        weights={**{component: 1.0 for component in CONSEQUENCE_COMPONENTS},
                 "F_execution": 100.0, "R_operating": 1.0},
    )
    raw = _pre_cu(unity)
    rmb = _pre_cu(weighted)
    by_id = {item.candidate_action_id: item for item in raw.actions}
    # Raw CU post totals: A (reduce R) = 10 + 1 = 11, B (reduce F) = 5 + 10 = 15.
    assert by_id["A11:instance-1"].post_totals == (11.0,)
    assert by_id["A11:instance-2"].post_totals == (15.0,)
    assert raw.authoritative_ranking == ("A11:instance-1", "A11:instance-2", "A00:instance-0")
    # RMB weights F=100, R=1: A = 10*100 + 1 = 1001, B = 5*100 + 10 = 510 -> B preferred.
    rmb_by_id = {item.candidate_action_id: item for item in rmb.actions}
    assert rmb_by_id["A11:instance-1"].post_totals == (1001.0,)
    assert rmb_by_id["A11:instance-2"].post_totals == (510.0,)
    assert rmb.authoritative_ranking == ("A11:instance-2", "A11:instance-1", "A00:instance-0")
    # M4 must rank in the selected monetary system, never on raw CU.
    assert rmb.authoritative_ranking[0] != raw.authoritative_ranking[0]


def test_g_not_frozen_monetary_mapping_blocks_authoritative_ranking():
    unfrozen = monetary_fixture(frozen=False)
    result = _pre_cu(unfrozen)
    assert result.authoritative_decision_available is False
    assert result.authoritative_ranking == ()
    assert result.decision_outcome == "AUTHORITATIVE_DECISION_UNAVAILABLE"
    # No raw-CU fallback: every candidate stays below the FORMAL lane.
    assert all(item.lane != "FORMAL" for item in result.actions if item.template_id != "A00")
