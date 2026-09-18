"""M1 representation-ownership tests (Phase 2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from model.M1.state_representation import (
    COORDINATE_ORDER,
    MARGINAL_IDENTITY_NOTE,
    build_joint_representation,
    build_marginal_representation,
    build_point_representation,
)
from model.common.decision_contracts import (
    HistoryScope,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError


STAGE = OperationalStage.POST_IB_PRE_OB

_ROWS = (
    # scenario_id, weight, t_ib, d_ob, d_tx
    (0, 0.25, 0.0, 30.0, 5.0),
    (1, 0.25, 60.0, 10.0, 20.0),
    (2, 0.25, 10.0, 200.0, 60.0),
    (3, 0.25, 5.0, 25.0, 8.0),
)


def _spec(
    *, temporal: TemporalKind = TemporalKind.HISTORY, uncertainty: UncertaintyKind = UncertaintyKind.JOINT,
    capacity: int | None = 16,
) -> StateRepresentationSpec:
    if temporal is TemporalKind.CURRENT:
        return StateRepresentationSpec(temporal=temporal, uncertainty=uncertainty)
    return StateRepresentationSpec(
        temporal=temporal,
        uncertainty=uncertainty,
        history_capacity=capacity,
        history_scope=HistoryScope.FULL_PREFIX,
    )


def _scenario(
    scenario_id: int,
    weight: float,
    t_ib: float,
    d_ob: float,
    d_tx: float,
    *,
    support: SupportState = SupportState.SUPPORTED,
    ib_observed: bool = False,
    ob_observed: bool = False,
) -> StateScenario:
    return StateScenario(
        scenario_id=scenario_id,
        scenario_weight=weight,
        stage=STAGE,
        t_ib_minutes=t_ib,
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        d_to_minutes=d_ob + d_tx,
        support=support,
        ib_observed=ib_observed,
        ob_observed=ob_observed,
    )


def _joint_set(rows=_ROWS, *, capacity: int = 16) -> StateScenarioSet:
    return StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=STAGE,
        representation=_spec(capacity=capacity),
        scenarios=tuple(_scenario(*row) for row in rows),
    )


def _weighted_l1_medoid_id(rows) -> int:
    best_id = None
    best_distance = None
    for candidate in rows:
        point = (candidate[2], candidate[3], candidate[4])
        distance = 0.0
        for other in rows:
            weight = other[1]
            target = (other[2], other[3], other[4])
            distance += weight * sum(abs(a - b) for a, b in zip(point, target))
        if best_distance is None or (distance, candidate[0]) < (best_distance, best_id):
            best_distance, best_id = distance, candidate[0]
    return best_id


def test_point_representation_is_the_weighted_joint_medoid_not_a_coordinate_summary():
    source = _joint_set()
    point = build_point_representation(source)
    assert point.representation.uncertainty is UncertaintyKind.POINT
    assert point.representation.temporal is TemporalKind.HISTORY
    assert point.representation.history_capacity == 16
    assert len(point.scenarios) == 1
    medoid = point.scenarios[0]
    assert medoid.scenario_id == _weighted_l1_medoid_id(_ROWS)
    assert medoid.scenario_weight == 1.0
    # the retained scenario is a real joint draw, not the coordinate-wise median
    # (7.5, 27.5, 14.0) nor the coordinate-wise mean (18.75, 66.25, 23.25)
    assert (medoid.t_ib_minutes, medoid.d_ob_minutes, medoid.d_tx_minutes) == (5.0, 25.0, 8.0)
    assert medoid.d_to_minutes == medoid.d_ob_minutes + medoid.d_tx_minutes
    assert medoid.scenario_id in {row[0] for row in _ROWS}


def test_point_representation_is_deterministic_under_scenario_order():
    forward = build_point_representation(_joint_set())
    reversed_rows = tuple(reversed(_ROWS))
    backward = build_point_representation(_joint_set(reversed_rows))
    assert forward.scenarios == backward.scenarios


def test_marginal_representation_preserves_coordinate_multisets_and_slot_weights():
    source = _joint_set()
    marginal = build_marginal_representation(source)
    assert marginal.representation.uncertainty is UncertaintyKind.MARGINAL
    assert [scenario.scenario_id for scenario in marginal.scenarios] == [
        scenario.scenario_id for scenario in source.scenarios
    ]
    assert [scenario.scenario_weight for scenario in marginal.scenarios] == [
        scenario.scenario_weight for scenario in source.scenarios
    ]
    for coordinate in COORDINATE_ORDER:
        source_values = sorted(
            getattr(scenario, coordinate) for scenario in source.scenarios
        )
        marginal_values = sorted(
            getattr(scenario, coordinate) for scenario in marginal.scenarios
        )
        assert marginal_values == source_values


def test_marginal_representation_destroys_joint_alignment_and_keeps_d_to_identity():
    source = _joint_set()
    marginal = build_marginal_representation(source)
    source_by_id = {scenario.scenario_id: scenario for scenario in source.scenarios}
    moved = [
        scenario.scenario_id
        for scenario in marginal.scenarios
        if (
            scenario.t_ib_minutes,
            scenario.d_ob_minutes,
            scenario.d_tx_minutes,
        )
        != (
            source_by_id[scenario.scenario_id].t_ib_minutes,
            source_by_id[scenario.scenario_id].d_ob_minutes,
            source_by_id[scenario.scenario_id].d_tx_minutes,
        )
    ]
    assert moved, "coordinate permutation must move at least one scenario"
    for scenario in marginal.scenarios:
        assert scenario.d_to_minutes == scenario.d_ob_minutes + scenario.d_tx_minutes
    # the coupling changed: Var(D_TO) differs from the source joint
    def weighted_variance(values: list[float], weights: list[float]) -> float:
        mean = sum(v * w for v, w in zip(values, weights)) / sum(weights)
        return sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / sum(weights)

    source_weights = [scenario.scenario_weight for scenario in source.scenarios]
    marginal_weights = [scenario.scenario_weight for scenario in marginal.scenarios]
    assert weighted_variance(
        [scenario.d_to_minutes for scenario in source.scenarios], source_weights
    ) != pytest.approx(
        weighted_variance(
            [scenario.d_to_minutes for scenario in marginal.scenarios],
            marginal_weights,
        )
    )


def test_marginal_representation_is_deterministic_and_not_labelled_independent():
    first = build_marginal_representation(_joint_set())
    second = build_marginal_representation(_joint_set())
    assert first.model_dump() == second.model_dump()
    assert "NOT_PHYSICAL_INDEPENDENCE" in MARGINAL_IDENTITY_NOTE
    assert first.representation.representation_id.endswith("MARGINAL")


def test_marginal_representation_requires_the_full_coordinate_order():
    with pytest.raises(ContractError):
        build_marginal_representation(
            _joint_set(), coordinate_order=("t_ib_minutes", "d_ob_minutes")
        )
    with pytest.raises(ContractError):
        build_marginal_representation(
            _joint_set(),
            coordinate_order=("t_ib_minutes", "d_ob_minutes", "d_to_minutes"),
        )


def test_point_and_marginal_require_a_history_joint_source():
    joint = _joint_set()
    point_source = build_point_representation(joint)
    for builder in (build_point_representation, build_marginal_representation):
        with pytest.raises(ContractError):
            builder(point_source)
    current_rows = _ROWS
    current_source = StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=STAGE,
        representation=_spec(temporal=TemporalKind.CURRENT),
        scenarios=tuple(_scenario(*row) for row in current_rows),
    )
    with pytest.raises(ContractError):
        build_point_representation(current_source)


def test_joint_representation_is_returned_unchanged():
    source = _joint_set()
    assert build_joint_representation(source) is source


def test_realized_milestones_collapse_to_point_under_the_shared_contract():
    realized = _scenario(7, 1.0, 5.0, 20.0, 4.0, ib_observed=True, ob_observed=True)
    collapsed = StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=STAGE,
        representation=_spec(uncertainty=UncertaintyKind.POINT),
        scenarios=(realized,),
    )
    assert collapsed.scenarios[0].is_realized
    with pytest.raises(ValidationError):
        StateScenarioSet(
            episode_id="episode-1",
            chain_id="chain-1",
            node_id="node-1",
            stage=STAGE,
            representation=_spec(uncertainty=UncertaintyKind.JOINT),
            scenarios=(realized, _scenario(8, 0.5, 1.0, 1.0, 1.0)),
        )
    with pytest.raises(ValidationError):
        StateScenarioSet(
            episode_id="episode-1",
            chain_id="chain-1",
            node_id="node-1",
            stage=STAGE,
            representation=_spec(uncertainty=UncertaintyKind.POINT),
            scenarios=(
                _scenario(7, 0.5, 5.0, 20.0, 4.0, ib_observed=True, ob_observed=True),
                _scenario(8, 0.5, 6.0, 21.0, 5.0),
            ),
        )


def test_d_to_identity_is_enforced_by_the_shared_contract():
    with pytest.raises(ValidationError):
        StateScenario(
            scenario_id=0,
            scenario_weight=1.0,
            stage=STAGE,
            t_ib_minutes=0.0,
            d_ob_minutes=10.0,
            d_tx_minutes=5.0,
            d_to_minutes=99.0,
        )


def test_history_capacity_h8_and_h16_constructible_h32_rejected():
    for capacity in (8, 16):
        spec = _spec(capacity=capacity)
        assert spec.history_capacity == capacity
        assert spec.representation_id == f"HISTORY_H{capacity}:JOINT"
    with pytest.raises(ValidationError):
        StateRepresentationSpec(
            temporal=TemporalKind.HISTORY,
            uncertainty=UncertaintyKind.JOINT,
            history_capacity=32,
            history_scope=HistoryScope.FULL_PREFIX,
        )
    with pytest.raises(ValidationError):
        StateRepresentationSpec(
            temporal=TemporalKind.CURRENT,
            uncertainty=UncertaintyKind.JOINT,
            history_capacity=16,
            history_scope=HistoryScope.FULL_PREFIX,
        )
