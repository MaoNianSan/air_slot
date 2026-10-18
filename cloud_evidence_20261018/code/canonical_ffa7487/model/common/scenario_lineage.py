"""Cross-module scenario lineage contract.

One aligned joint draw keeps the same ``(episode_id, decision_node_id,
scenario_id, scenario_weight)`` identity from M1 through M2 into M4.  This
module is the single small helper for lineage checks; it deliberately does not
grow into an information-sharing framework.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .errors import ContractError


def scenario_lineage_key(scenario: Mapping[str, Any]) -> tuple[str, str, int, float]:
    """Return the stable lineage identity of one aligned scenario row."""
    try:
        return (
            str(scenario["episode_id"]),
            str(scenario["decision_node_id"]),
            int(scenario["scenario_id"]),
            float(scenario["scenario_weight"]),
        )
    except KeyError as exc:
        raise ContractError("SCENARIO_LINEAGE_FIELD_MISSING") from exc


def aligned_scenario_ids(scenarios: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
    return tuple(int(row["scenario_id"]) for row in scenarios)


def validate_same_lineage(
    *labels: Iterable[Mapping[str, Any]],
    require_weights_equal: bool = True,
) -> None:
    """Require identical lineage (ids and optionally weights) across modules."""
    keys = [tuple(scenario_lineage_key(row) for row in rows) for rows in labels]
    if not keys:
        return
    reference = keys[0]
    for other in keys[1:]:
        if require_weights_equal and other != reference:
            raise ContractError("SCENARIO_LINEAGE_MISMATCH")
        if not require_weights_equal and tuple(key[:3] for key in other) != tuple(
            key[:3] for key in reference
        ):
            raise ContractError("SCENARIO_LINEAGE_IDENTITY_MISMATCH")
    if len({key[2] for key in reference}) != len(reference):
        raise ContractError("SCENARIO_LINEAGE_DUPLICATE_SCENARIO_ID")


__all__ = [
    "aligned_scenario_ids",
    "scenario_lineage_key",
    "validate_same_lineage",
]
