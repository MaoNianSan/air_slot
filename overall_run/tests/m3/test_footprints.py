from __future__ import annotations

from src.m3 import FootprintRole, SUBITEMS_M2_V2, footprint_counts, footprint_matrix


def test_footprint_schema_and_sparsity(m3_contract) -> None:
    matrix = footprint_matrix(m3_contract)
    assert tuple(matrix.columns) == SUBITEMS_M2_V2
    assert matrix.shape == (21, 9)
    counts = footprint_counts(m3_contract).set_index("action_id")
    assert counts["primary_count"].le(2).all()
    assert counts["secondary_count"].le(2).all()
    assert counts["nonzero_count"].le(4).all()


def test_hard_semantic_footprint_constraints(m3_contract) -> None:
    assert m3_contract.footprints["A31"].roles["P_DELAY"] is FootprintRole.NONE
    assert m3_contract.footprints["A33"].roles["P_CARE"] is FootprintRole.PRIMARY
    assert all(
        m3_contract.footprints["A33"].roles[name] is FootprintRole.NONE
        for name in ("F_TURN", "F_WAIT", "F_PROPAGATION")
    )
    assert all(
        role is FootprintRole.NONE
        for role in m3_contract.footprints["A00"].roles.values()
    )


def test_aircraft_action_footprints(m3_contract) -> None:
    expected = {
        "A51": {
            "F_TURN": FootprintRole.PRIMARY,
            "F_PROPAGATION": FootprintRole.SECONDARY,
            "P_CONNECTION": FootprintRole.SECONDARY,
        },
        "A52": {
            "F_TURN": FootprintRole.SECONDARY,
            "F_PROPAGATION": FootprintRole.PRIMARY,
        },
        "A53": {
            "F_TURN": FootprintRole.PRIMARY,
            "F_PROPAGATION": FootprintRole.PRIMARY,
            "P_CONNECTION": FootprintRole.SECONDARY,
        },
    }
    for action_id, nonzero in expected.items():
        roles = m3_contract.footprints[action_id].roles
        for subitem_id in SUBITEMS_M2_V2:
            assert roles[subitem_id] is nonzero.get(subitem_id, FootprintRole.NONE)
