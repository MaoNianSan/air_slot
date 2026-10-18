from model.M2.consequence_service import ConsequenceReferenceBinding, native_consequence_vector
from model.M3.transition import TransitionContext, scenario_headroom
from model.common.decision_contracts import StateScenario
from model.common.enums import OperationalStage
from model.M1.marginal_distribution import ExactWeightedMarginalDistribution
from model.common.decision_contracts import StateRepresentationSpec, TemporalKind, UncertaintyKind, StateScenarioSet, HistoryScope


def _state(*, signed=-10.0, legacy=0.0, sobt=0.0, d_ob=30.0, weight=1.0, scenario_id=1):
    return StateScenario(
        scenario_id=scenario_id, scenario_weight=weight, stage=OperationalStage.PRE_IB,
        t_ib_minutes=legacy, t_ib_signed_minutes=signed,
        sobt_relative_minutes=sobt, d_ob_minutes=d_ob, d_tx_minutes=5.0,
        d_to_minutes=d_ob + 5.0,
    )


def _binding(contract):
    return ConsequenceReferenceBinding(
        reference_id="node", turnaround_reference_minutes=41.0,
        taxi_reference_minutes=0.0, expected_pax=100.0, connection_share=0.2,
        downstream_exposure=1.0, continuity_contract=contract,
        sobt_relative_minutes=0.0,
    )


def test_continuity_b_preserves_signed_turn_coordinate():
    state = _state(signed=-10.0)
    legacy = native_consequence_vector(state, _binding("LEGACY_A_V1"))
    current = native_consequence_vector(state, _binding("JATM_F_CONTINUITY_B_V1"))
    assert legacy["F_continuity"] == 0.0
    assert current["F_continuity"] == 31.0


def test_stage2_signed_headroom_differs_from_legacy_truncation():
    state = _state(signed=-10.0, legacy=0.0, d_ob=50.0)
    legacy = scenario_headroom(state, TransitionContext(sobt_minutes=0.0, turnaround_lower_bound_minutes=41.0))
    signed = scenario_headroom(state, TransitionContext(
        sobt_minutes=0.0, turnaround_lower_bound_minutes=41.0,
        time_coordinate_contract="JATM_STAGE2_SIGNED_T_IB_V1"))
    assert legacy == 9.0
    assert signed == 19.0


def test_exact_marginal_retains_signed_coordinate_and_origin():
    source = StateScenarioSet(
        episode_id="e", chain_id="c", node_id="n", stage=OperationalStage.PRE_IB,
        representation=StateRepresentationSpec(temporal=TemporalKind.HISTORY,
            uncertainty=UncertaintyKind.JOINT, history_capacity=16, history_scope=HistoryScope.FIXED_WINDOW),
        scenarios=(_state(signed=-10.0, legacy=0.0, weight=.5, scenario_id=1),
                   _state(signed=20.0, legacy=20.0, weight=.5, scenario_id=2)),
    )
    adapter = ExactWeightedMarginalDistribution.from_source(
        source, time_coordinate_contract="JATM_STAGE2_SIGNED_T_IB_V1")
    assert adapter.scenario_count == 2
    assert {s.t_ib_signed_minutes for s in adapter.iter_scenarios()} == {-10.0, 20.0}
    assert {s.sobt_relative_minutes for s in adapter.iter_scenarios()} == {0.0}
