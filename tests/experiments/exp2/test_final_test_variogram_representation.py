"""Regression tests for representation-specific Final Test Exp2A variograms."""

from __future__ import annotations

from exp.exp2.global_development import _finite_variant_draws


def _row(scenario_id: int, r_ib: float, d_ob: float, d_tx: float) -> dict:
    return {
        "scenario_id": scenario_id,
        "scenario_weight": 1 / 3,
        "T_IB_A00": r_ib,
        "D_OB": d_ob,
        "D_TX": d_tx,
        "D_TO": d_ob + d_tx,
        "lineage": (f"M1:{scenario_id}",),
        "target_envelopes": [
            {"target_name": "T_IB_A00", "class_id": "FINITE", "scalar_minutes": r_ib},
            {"target_name": "D_OB", "class_id": "FINITE", "scalar_minutes": d_ob},
            {"target_name": "D_TX", "class_id": "FINITE", "scalar_minutes": d_tx},
        ],
    }


def test_final_test_variogram_draws_are_representation_specific() -> None:
    rows = [
        _row(0, 0.0, 0.0, 0.0),
        _row(1, 1.0, 1.0, 4.0),
        _row(2, 2.0, 4.0, 9.0),
    ]
    point, point_meta = _finite_variant_draws(rows, "EXP2A_POINT")
    marginal, marginal_meta = _finite_variant_draws(rows, "EXP2A_MARGINAL")
    joint, joint_meta = _finite_variant_draws(rows, "EXP2A_JOINT")

    assert point_meta["representation"] == "Point"
    assert marginal_meta["representation"] == "Marginal"
    assert joint_meta["representation"] == "Joint"
    assert len(point) == 1
    assert len(marginal) == len(joint) == 3
    assert marginal != joint
    assert len({point_meta["representation_input_hash"], marginal_meta["representation_input_hash"], joint_meta["representation_input_hash"]}) == 3
