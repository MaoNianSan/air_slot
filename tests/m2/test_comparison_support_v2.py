"""M2 comparison-support and consequence-priority tests (Phase 2)."""

from __future__ import annotations

import pytest

from model.M2.comparison_support import (
    EQUAL_COMPONENT_VIEW,
    PRIMARY_AGGREGATION_VIEW,
    ComparisonSupportRule,
    build_comparison_support,
    consequence_priority_signal,
    delay_priority_signal,
    expected_cu_vector,
    phi_c,
    priority_signals,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.decision_contracts import (
    HistoryScope,
    ConsequenceScenario,
    ConsequenceScenarioSet,
    SignalKind,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    TypedStatus,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError


STAGE = OperationalStage.POST_IB_PRE_OB
CU_SCALES = {
    "F_continuity": 3.0,
    "F_execution": 3.0,
    "F_propagation": 3.0,
    "P_time": 6.0,
    "P_itinerary": 6.0,
    "P_service": 6.0,
    "R_operating": 9.0,
}


def _spec(uncertainty: UncertaintyKind = UncertaintyKind.JOINT) -> StateRepresentationSpec:
    return StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=uncertainty,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )


def _cu(
    *, overrides: dict[str, float | None] | None = None, scale: float = 1.0
) -> dict[str, float | None]:
    values: dict[str, float | None] = {
        component: CU_SCALES[component] * scale for component in CONSEQUENCE_COMPONENTS
    }
    for component, value in (overrides or {}).items():
        values[component] = value
    return values


def _pair(
    rows: tuple[dict, ...],
    *,
    representation: StateRepresentationSpec | None = None,
) -> tuple[StateScenarioSet, ConsequenceScenarioSet]:
    spec = representation or _spec()
    state_scenarios = []
    consequence_scenarios = []
    for row in rows:
        d_to = float(row["d_to"])
        d_ob = d_to * 0.6
        d_tx = d_to - d_ob
        state_scenarios.append(
            StateScenario(
                scenario_id=row["scenario_id"],
                scenario_weight=row["weight"],
                stage=STAGE,
                t_ib_minutes=float(row.get("t_ib", 0.0)),
                d_ob_minutes=d_ob,
                d_tx_minutes=d_tx,
                d_to_minutes=d_to,
                support=row.get("state_support", SupportState.SUPPORTED),
            )
        )
        cu_values = row.get("cu", _cu())
        consequence_scenarios.append(
            ConsequenceScenario(
                scenario_id=row["scenario_id"],
                scenario_weight=row["weight"],
                native_components=dict(cu_values),
                cu_components=dict(cu_values),
                support=row.get("consequence_support", SupportState.SUPPORTED),
            )
        )
    state = StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=STAGE,
        representation=spec,
        scenarios=tuple(state_scenarios),
    )
    consequence = ConsequenceScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=STAGE,
        representation=spec,
        registry_id="M2_DATA2_FORMAL_CU_V5",
        registry_hash="sha256:test-registry",
        scenarios=tuple(consequence_scenarios),
        support=SupportState.SUPPORTED,
    )
    return state, consequence


_BASE_ROWS = (
    {"scenario_id": 0, "weight": 0.5, "d_to": 10.0, "t_ib": 0.0},
    {"scenario_id": 1, "weight": 0.4, "d_to": 60.0, "t_ib": 5.0},
    {"scenario_id": 2, "weight": 0.1, "d_to": 120.0, "t_ib": 10.0},
)


def test_full_support_node_is_included_with_unit_mass():
    state, consequence = _pair(_BASE_ROWS)
    support = build_comparison_support(state, consequence)
    assert support.included is True
    assert support.status is TypedStatus.SUPPORTED
    assert support.supported_mass == pytest.approx(1.0)
    assert support.supported_scenario_ids == (0, 1, 2)
    assert support.scenario_count_total == 3
    assert support.threshold == pytest.approx(0.90)
    assert support.rule_id == "M2_COMMON_SUPPORT_NOMINAL_0P90"


def test_below_threshold_abstains_without_renormalisation_or_zero_fill():
    rows = tuple(
        {**row, "state_support": SupportState.ABSTAIN} if row["scenario_id"] == 0 else row
        for row in _BASE_ROWS
    )
    state, consequence = _pair(rows)
    support = build_comparison_support(state, consequence)
    assert support.included is False
    assert support.status is TypedStatus.ABSTAIN_NO_COMMON_SUPPORT
    assert support.supported_mass == pytest.approx(0.5)
    assert support.supported_scenario_ids == (1, 2)
    assert "M2_CS_BELOW_NOMINAL_THRESHOLD" in support.reason_codes
    assert "M2_CS_STATE_UNSUPPORTED" in support.reason_codes
    for signal in (
        delay_priority_signal(state, support),
        consequence_priority_signal(consequence, support),
    ):
        assert signal.score is None
        assert signal.support is SupportState.ABSTAIN
        assert signal.status is TypedStatus.ABSTAIN_NO_COMMON_SUPPORT
        assert signal.comparison_support_mass == pytest.approx(0.5)
    with pytest.raises(ContractError):
        expected_cu_vector(consequence, support)


def test_boundary_mass_at_the_nominal_threshold_is_included():
    rows = (
        {"scenario_id": 0, "weight": 0.9, "d_to": 10.0},
        {
            "scenario_id": 1,
            "weight": 0.1,
            "d_to": 60.0,
            "state_support": SupportState.ABSTAIN,
        },
    )
    state, consequence = _pair(rows)
    support = build_comparison_support(state, consequence)
    assert support.supported_mass == pytest.approx(0.9)
    assert support.included is True


def test_missing_cu_excludes_while_supported_zero_is_kept():
    rows = (
        {"scenario_id": 0, "weight": 0.5, "d_to": 10.0, "cu": _cu()},
        {"scenario_id": 1, "weight": 0.4, "d_to": 60.0, "cu": _cu(overrides={"P_itinerary": 0.0})},
        {
            "scenario_id": 2,
            "weight": 0.1,
            "d_to": 120.0,
            "cu": _cu(overrides={"P_service": None}),
        },
    )
    state, consequence = _pair(rows)
    support = build_comparison_support(state, consequence)
    assert support.supported_scenario_ids == (0, 1)
    assert support.supported_mass == pytest.approx(0.9)
    assert "M2_CS_CU_MISSING:P_service" in support.reason_codes
    expected = expected_cu_vector(consequence, support)
    assert expected["P_itinerary"] == pytest.approx(
        (0.4 * 0.0 + 0.5 * CU_SCALES["P_itinerary"]) / 0.9
    )
    # the excluded missing value is never treated as zero
    assert expected["P_service"] == pytest.approx(CU_SCALES["P_service"])


def test_delay_signal_is_the_manuscript_common_support_conditional_mean():
    rows = tuple(
        {**row, "consequence_support": SupportState.ABSTAIN}
        if row["scenario_id"] == 2
        else row
        for row in _BASE_ROWS
    )
    state, consequence = _pair(rows)
    support, delay, effect = priority_signals(state, consequence)
    assert support.included is True
    assert support.supported_mass == pytest.approx(0.9)
    expected = (0.5 * 10.0 + 0.4 * 60.0) / 0.9
    assert delay.score == pytest.approx(expected)
    # the legacy deviation (weight sum without m^CS renormalisation) differs
    assert delay.score != pytest.approx(0.5 * 10.0 + 0.4 * 60.0)
    assert delay.signal_type is SignalKind.DELAY
    assert effect.signal_type is SignalKind.CONSEQUENCE
    assert delay.comparison_support_mass == pytest.approx(support.supported_mass)
    assert effect.comparison_support_threshold == pytest.approx(support.threshold)


def test_consequence_priority_is_the_domain_balanced_phi_c():
    state, consequence = _pair(_BASE_ROWS)
    support = build_comparison_support(state, consequence)
    expected = expected_cu_vector(consequence, support)
    signal = consequence_priority_signal(consequence, support)
    assert signal.score == pytest.approx(phi_c(expected))
    # (3 + 6 + 9) / 3 for the F, P and R domain means
    assert signal.score == pytest.approx(6.0)
    assert signal.score != pytest.approx(
        phi_c(expected, view=EQUAL_COMPONENT_VIEW)
    )
    assert phi_c({**{component: 0.0 for component in CONSEQUENCE_COMPONENTS}, "F_continuity": 1.0}) == pytest.approx(1 / 9)
    assert phi_c({**{component: 0.0 for component in CONSEQUENCE_COMPONENTS}, "R_operating": 1.0}) == pytest.approx(1 / 3)
    assert phi_c(
        {component: 0.0 for component in CONSEQUENCE_COMPONENTS},
        view=EQUAL_COMPONENT_VIEW,
    ) == pytest.approx(0.0)
    assert phi_c(
        {**{component: 0.0 for component in CONSEQUENCE_COMPONENTS}, "F_continuity": 1.0},
        view=EQUAL_COMPONENT_VIEW,
    ) == pytest.approx(1 / 7)


def test_phi_c_rejects_incomplete_cu_vectors():
    with pytest.raises(ContractError):
        phi_c({"F_continuity": 1.0})
    with pytest.raises(ContractError):
        phi_c({component: 1.0 for component in CONSEQUENCE_COMPONENTS}, view="NOT_A_VIEW")


def test_priority_signals_share_one_support_attestation_and_identity():
    state, consequence = _pair(_BASE_ROWS)
    support, delay, effect = priority_signals(state, consequence)
    for signal in (delay, effect):
        assert signal.episode_id == support.episode_id
        assert signal.chain_id == support.chain_id
        assert signal.node_id == support.node_id
        assert signal.representation_id == state.representation.representation_id
        assert signal.comparison_support_mass == pytest.approx(support.supported_mass)
        assert signal.comparison_support_threshold == pytest.approx(support.threshold)


def test_representation_and_weight_mismatch_are_rejected():
    state, consequence = _pair(_BASE_ROWS)
    marginal = consequence.model_copy(
        update={"representation": _spec(UncertaintyKind.MARGINAL)}
    )
    with pytest.raises(ContractError):
        build_comparison_support(state, marginal)

    rows = tuple(
        {**row, "weight": 0.45}
        if row["scenario_id"] in {0, 1}
        else row
        for row in _BASE_ROWS
    )
    _, mismatched = _pair(rows)
    with pytest.raises(ContractError):
        build_comparison_support(state, mismatched)

    other_node = consequence.model_copy(update={"node_id": "node-2"})
    with pytest.raises(ContractError):
        build_comparison_support(state, other_node)


def test_rule_records_nominal_threshold_and_empty_manuscript_sensitivity():
    rule = ComparisonSupportRule()
    assert rule.threshold == pytest.approx(0.90)
    assert rule.predefined_sensitivity == ()
    assert rule.sensitivity_status == "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES"
    state, consequence = _pair(_BASE_ROWS)
    support = build_comparison_support(
        state, consequence, rule=ComparisonSupportRule(threshold=0.5)
    )
    assert support.threshold == pytest.approx(0.5)
    assert support.included is True


def test_supported_degraded_scenarios_are_carried_as_degraded():
    rows = tuple(
        {**row, "consequence_support": SupportState.DEGRADED}
        if row["scenario_id"] == 1
        else row
        for row in _BASE_ROWS
    )
    state, consequence = _pair(rows)
    support, delay, effect = priority_signals(state, consequence)
    assert support.included is True
    assert support.status is TypedStatus.DEGRADED
    assert delay.support is SupportState.DEGRADED
    assert effect.support is SupportState.DEGRADED
