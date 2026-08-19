"""V2 warning probability: P(D_TO > 30) from formal M1V2Scenario rows.

D_TO = D_OB + D_TX is derived per scenario and the warning never reconstructs
it from signed DELTA_OB or raw T_TX (LEGACY_V1 semantics).
"""

import pytest

from model.M1.contracts import M1V2Scenario
from model.M1.warning import PRINCIPAL_WARNING_EVENT, warning_probability


def _scenario(*, scenario_id, weight, d_ob, d_tx, node="n",
              overflow_ob=False, overflow_tx=False):
    return M1V2Scenario(
        episode_id="e",
        decision_node_id=node,
        scenario_id=scenario_id,
        scenario_weight=weight,
        operational_stage="PRE_IB",
        decision_time_utc="2019-01-01T12:00:00+00:00",
        t_ib_a00_utc="2019-01-01T12:10:00+00:00",
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        t_ib_support="SUPPORTED",
        d_ob_support="SUPPORTED",
        d_tx_support="SUPPORTED",
        overflow_d_ob=overflow_ob,
        overflow_d_tx=overflow_tx,
        scenario_seed_key=f"seed-{scenario_id}",
        taxi_reference_id="DATA2_TAXI_REFERENCE@1.0.0",
        taxi_reference_hash="sha256:reference",
        taxi_reference_support_state="SUPPORTED",
    )


def test_warning_probability_uses_d_to_strict_gt_and_weights():
    result = warning_probability((
        _scenario(scenario_id=0, weight=0.25, d_ob=20, d_tx=5),   # D_TO 25
        _scenario(scenario_id=1, weight=0.75, d_ob=21, d_tx=10),  # D_TO 31
    ))
    assert result.event_id == PRINCIPAL_WARNING_EVENT
    assert result.support_state == "SUPPORTED"
    assert result.delay_threshold_minutes == 30
    assert result.exceedance_weight == pytest.approx(0.75)
    assert result.probability == pytest.approx(0.75)


def test_warning_probability_abstains_instead_of_dropping_missing_d_to():
    result = warning_probability((
        _scenario(scenario_id=0, weight=0.5, d_ob=40, d_tx=0),
        _scenario(scenario_id=1, weight=0.5, d_ob=None, d_tx=None),
    ))
    assert result.support_state == "ABSTAIN"
    assert result.probability is None
    assert result.reason_code == "M1_V2_D_TO_UNAVAILABLE"


def test_warning_probability_rejects_mixed_decision_nodes():
    with pytest.raises(ValueError, match="one episode/decision node"):
        warning_probability((
            _scenario(scenario_id=0, weight=0.5, d_ob=40, d_tx=0),
            _scenario(scenario_id=1, weight=0.5, d_ob=40, d_tx=0, node="other"),
        ))


def test_warning_probability_records_explicit_tail_representative_use():
    result = warning_probability((
        _scenario(scenario_id=0, weight=1.0, d_ob=185, d_tx=0, overflow_ob=True),
    ))
    assert result.support_state == "SUPPORTED"
    assert result.tail_representative_used is True
    assert result.tail_value_policy == "TARGET_BIN_REPRESENTATIVE"
