from __future__ import annotations

import pandas as pd

from .contracts import SUBITEMS_M2_V2, FootprintRole, M3ContractBundle


def footprint_frame(contract: M3ContractBundle) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for action_id, spec in contract.footprints.items():
        for subitem_id in SUBITEMS_M2_V2:
            rows.append({
                "action_library_version": contract.action_library_version,
                "action_id": action_id,
                "subitem_id": subitem_id,
                "footprint_role": spec.roles[subitem_id].value,
            })
    return pd.DataFrame(rows)


def footprint_matrix(contract: M3ContractBundle) -> pd.DataFrame:
    return (
        footprint_frame(contract)
        .pivot(index="action_id", columns="subitem_id", values="footprint_role")
        .reindex(index=contract.catalog, columns=SUBITEMS_M2_V2)
    )


def validate_semantic_footprints(contract: M3ContractBundle) -> None:
    checks = (
        (contract.footprints["A31"].roles["P_DELAY"] is FootprintRole.NONE, "A31.P_DELAY"),
        (contract.footprints["A33"].roles["P_CARE"] is FootprintRole.PRIMARY, "A33.P_CARE"),
        (
            all(
                contract.footprints["A33"].roles[name] is FootprintRole.NONE
                for name in ("F_TURN", "F_WAIT", "F_PROPAGATION")
            ),
            "A33.F",
        ),
        (
            all(role is FootprintRole.NONE for role in contract.footprints["A00"].roles.values()),
            "A00",
        ),
    )
    failures = [name for passed, name in checks if not passed]
    if failures:
        raise ValueError("M3_FOOTPRINT_SEMANTIC_FAILURE:" + ",".join(failures))


def footprint_counts(contract: M3ContractBundle) -> pd.DataFrame:
    rows = []
    for action_id, spec in contract.footprints.items():
        counts = {
            role: sum(value is role for value in spec.roles.values())
            for role in FootprintRole
        }
        rows.append({
            "action_id": action_id,
            "primary_count": counts[FootprintRole.PRIMARY],
            "secondary_count": counts[FootprintRole.SECONDARY],
            "none_count": counts[FootprintRole.NONE],
            "nonzero_count": counts[FootprintRole.PRIMARY] + counts[FootprintRole.SECONDARY],
        })
    return pd.DataFrame(rows)
