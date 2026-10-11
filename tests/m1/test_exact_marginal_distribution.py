from model.M1.marginal_distribution import (
    EXACT_PRODUCT_IDENTITY_NOTE,
    ExactWeightedMarginalDistribution,
)
from model.common.decision_contracts import (
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
)
from model.common.enums import OperationalStage


def _source() -> StateScenarioSet:
    spec = StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=8,
        history_scope="FULL_PREFIX",
    )
    return StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=OperationalStage.PRE_IB,
        representation=spec,
        scenarios=(
            StateScenario(
                scenario_id=0,
                scenario_weight=0.25,
                stage=OperationalStage.PRE_IB,
                t_ib_minutes=10.0,
                d_ob_minutes=2.0,
                d_tx_minutes=8.0,
            ),
            StateScenario(
                scenario_id=1,
                scenario_weight=0.75,
                stage=OperationalStage.PRE_IB,
                t_ib_minutes=20.0,
                d_ob_minutes=5.0,
                d_tx_minutes=11.0,
            ),
        ),
    )


def test_exact_adapter_preserves_unequal_weighted_marginals():
    adapter = ExactWeightedMarginalDistribution.from_source(_source())

    assert adapter.scenario_count == 8
    assert tuple((atom.value, atom.mass) for atom in adapter.weighted_atoms("t_ib_minutes")) == (
        (10.0, 0.25),
        (20.0, 0.75),
    )
    materialized = adapter.materialize()
    assert sum(s.scenario_weight for s in materialized.scenarios) == 1.0
    assert all(
        abs(s.d_to_minutes - (s.d_ob_minutes + s.d_tx_minutes)) < 1e-9
        for s in materialized.scenarios
    )
    assert adapter.identity_note == EXACT_PRODUCT_IDENTITY_NOTE


def test_exact_adapter_aggregates_duplicate_atoms():
    source = _source().model_copy(
        update={
            "scenarios": (
                _source().scenarios[0],
                _source().scenarios[1].model_copy(update={"t_ib_minutes": 10.0}),
            )
        }
    )
    adapter = ExactWeightedMarginalDistribution.from_source(source)
    assert tuple((a.value, a.mass) for a in adapter.weighted_atoms("t_ib_minutes")) == (
        (10.0, 1.0),
    )
