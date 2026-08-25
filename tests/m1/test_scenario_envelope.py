from model.M1.contracts import HazardBinContract, HurdleQuantileContract
from model.M1.scenario_envelope import JointScenarioEnvelope, TargetScenarioEnvelope
from exp.workflows.m1_v2_current_stage_scenario_envelope import _class_envelope


LINEAGE = ("test:lineage",)


def _delay_contract():
    return HurdleQuantileContract(
        target_name="D_OB", max_finite_minutes=210, bin_width_minutes=5,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
    )


def test_zero_and_first_positive_bin_have_distinct_public_identity():
    contract = _delay_contract()
    zero = _class_envelope(
        target="D_OB", index=0, conditioning_index=0, contract=contract,
        source_role="MODEL_DRAW", decision_time="2019-08-01T00:00:00+00:00",
        scalar=0.0, lineage=LINEAGE,
    )
    positive = _class_envelope(
        target="D_OB", index=0, conditioning_index=0, contract=contract,
        source_role="MODEL_DRAW", decision_time="2019-08-01T00:00:00+00:00",
        scalar=2.5, lineage=LINEAGE,
    )
    assert (zero.class_id, zero.class_index, zero.conditioning_index) == ("ZERO", 0, 0)
    assert (positive.class_id, positive.class_index, positive.conditioning_index) == (
        "POSITIVE_BIN_0", 1, 0,
    )


def test_tail_class_has_no_scalar_and_can_retain_supported_candidate():
    contract = _delay_contract()
    tail = _class_envelope(
        target="D_OB", index=contract.overflow_index,
        conditioning_index=contract.overflow_index, contract=contract,
        source_role="MODEL_DRAW", decision_time="2019-08-01T00:00:00+00:00",
        scalar=215.0, raw_model_candidate_minutes=215.0, lineage=LINEAGE,
    )
    assert tail.class_id == "OVERFLOW_TAIL"
    assert tail.class_index == contract.overflow_index + 1
    assert tail.scalar_minutes is None
    assert tail.raw_model_candidate_minutes == 215.0


def test_joint_d_to_abstains_when_a_primitive_is_tail():
    hazard = HazardBinContract(bin_width_minutes=5, max_finite_minutes=360)
    d_ob_contract = _delay_contract()
    d_tx_contract = HurdleQuantileContract(
        target_name="D_TX", max_finite_minutes=60, bin_width_minutes=5,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
    )
    ib = _class_envelope(
        target="T_IB_A00", index=0, conditioning_index=0, contract=hazard,
        source_role="MODEL_DRAW", decision_time="2019-08-01T00:00:00+00:00",
        scalar=2.5, event_time_utc="2019-08-01T00:02:30+00:00", lineage=LINEAGE,
    )
    d_ob = _class_envelope(
        target="D_OB", index=d_ob_contract.overflow_index,
        conditioning_index=d_ob_contract.overflow_index, contract=d_ob_contract,
        source_role="MODEL_DRAW", decision_time="2019-08-01T00:00:00+00:00",
        scalar=None, lineage=LINEAGE,
    )
    d_tx = _class_envelope(
        target="D_TX", index=0, conditioning_index=0, contract=d_tx_contract,
        source_role="MODEL_DRAW", decision_time="2019-08-01T00:00:00+00:00",
        scalar=0.0, lineage=LINEAGE,
    )
    joint = JointScenarioEnvelope(
        episode_id="episode", decision_node_id="node", scenario_id=0,
        scenario_weight=1.0, operational_stage="PRE_IB",
        decision_time_utc="2019-08-01T00:00:00+00:00",
        information_cutoff_utc="2019-08-01T00:00:00+00:00",
        targets=(ib, d_ob, d_tx), r_ib_minutes=2.5, r_ib_support="SUPPORTED",
        d_to_minutes=None, d_to_support="ABSTAIN_TAIL_CLASS",
        scenario_seed_key="seed", lineage=LINEAGE,
    )
    assert joint.d_to_minutes is None
    assert joint.d_to_support == "ABSTAIN_TAIL_CLASS"


def test_factual_tail_preserves_raw_value_separately():
    contract = _delay_contract()
    tail = TargetScenarioEnvelope(
        target_name="D_OB", class_index=contract.overflow_index + 1,
        conditioning_index=contract.overflow_index, class_id="OVERFLOW_TAIL",
        class_lower_minutes=210.0, scalar_minutes=None, raw_observed_minutes=240.0,
        source_role="FACTUAL_OBSERVED", support_state="SUPPORTED",
        scalar_support_state="ABSTAIN_TAIL_CLASS", overflow=True, lineage=LINEAGE,
    )
    assert tail.raw_observed_minutes == 240.0
    assert tail.scalar_minutes is None
