import pytest

from model.M1.contracts import AlignedScenario
from model.M1.warning import PRINCIPAL_WARNING_EVENT, warning_probability


def _scenario(*, scenario_id, weight, delta_ob, t_tx=20, reference=10,
              node="n", reference_state="SUPPORTED", overflow_delta=False):
    return AlignedScenario(
        episode_id="e",
        decision_node_id=node,
        scenario_id=scenario_id,
        scenario_weight=weight,
        operational_stage="PRE_IB",
        r_ib_minutes=10,
        delta_ob_minutes=delta_ob,
        t_tx_minutes=t_tx,
        tx_reference_minutes=reference,
        taxi_reference_id="DATA2_TAXI_REFERENCE@1.0.0",
        taxi_reference_hash="sha256:reference",
        taxi_reference_fallback_level="AIRPORT_CELL",
        taxi_reference_support_state=reference_state,
        ib_support="SUPPORTED",
        delta_ob_support="SUPPORTED",
        tx_support="SUPPORTED",
        overflow_delta_ob=overflow_delta,
        scenario_seed_key=f"seed-{scenario_id}",
    )


def test_warning_probability_uses_signed_d_to_strict_gt_and_weights():
    result = warning_probability((
        _scenario(scenario_id=0, weight=0.25, delta_ob=20),
        _scenario(scenario_id=1, weight=0.75, delta_ob=21),
    ))
    assert result.event_id == PRINCIPAL_WARNING_EVENT
    assert result.support_state == "SUPPORTED"
    assert result.delay_threshold_minutes == 30
    assert result.exceedance_weight == pytest.approx(0.75)
    assert result.probability == pytest.approx(0.75)


def test_warning_probability_abstains_instead_of_dropping_missing_reference():
    result = warning_probability((
        _scenario(scenario_id=0, weight=0.5, delta_ob=40),
        _scenario(scenario_id=1, weight=0.5, delta_ob=40, reference=None,
                  reference_state="ABSTAIN"),
    ))
    assert result.support_state == "ABSTAIN"
    assert result.probability is None
    assert result.reason_code == "TRAIN_FROZEN_TAXI_REFERENCE_OR_D_TO_UNAVAILABLE"


def test_warning_probability_rejects_mixed_decision_nodes():
    with pytest.raises(ValueError, match="one episode/decision node"):
        warning_probability((
            _scenario(scenario_id=0, weight=0.5, delta_ob=40),
            _scenario(scenario_id=1, weight=0.5, delta_ob=40, node="other"),
        ))


def test_warning_probability_records_explicit_tail_representative_use():
    result = warning_probability((
        _scenario(scenario_id=0, weight=1.0, delta_ob=185, overflow_delta=True),
    ))
    assert result.support_state == "SUPPORTED"
    assert result.tail_representative_used is True
    assert result.tail_value_policy == "TARGET_BIN_REPRESENTATIVE"
