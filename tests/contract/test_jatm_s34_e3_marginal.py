from model.M1.marginal_distribution import ExactWeightedMarginalDistribution
from model.common.decision_contracts import StateRepresentationSpec, StateScenario, StateScenarioSet
from model.common.enums import OperationalStage
from model.common.decision_contracts import TemporalKind, UncertaintyKind

from exp.jatm_s34.e3_marginal import audit_state_set


def _source() -> StateScenarioSet:
    return StateScenarioSet(
        episode_id="episode-e3",
        chain_id="chain-e3",
        node_id="node-e3",
        stage=OperationalStage.PRE_IB,
        representation=StateRepresentationSpec(
            temporal=TemporalKind.HISTORY,
            uncertainty=UncertaintyKind.JOINT,
            history_capacity=8,
            history_scope="FULL_PREFIX",
        ),
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


def test_e3_pilot_uses_lazy_product_when_limit_is_small():
    result = audit_state_set(_source(), max_materialize=2)
    assert result["status"] == "PASS_EXACT_WEIGHTED_MARGINAL"
    assert result["product_scenario_count"] == 8
    assert result["materialized"] is False
    assert result["weighted_marginal_match"] is True


def test_e3_pilot_materializes_and_checks_d_to_when_allowed():
    result = audit_state_set(_source(), max_materialize=8)
    assert result["materialized"] is True
    assert result["materialized_weight_sum"] == 1.0
    assert result["d_to_identity_ok"] is True
