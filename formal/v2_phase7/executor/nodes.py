"""Canonical decision-node records carried by the Phase-7 DAG.

A ``CanonicalNode`` is the *materialization boundary* object: it carries the
node identity, the M1 input sequence, the PRE-published observed state and the
M2 reference binding. The one-shot Final-Test materialization entry publishes
it; every downstream stage only consumes it from an immutable checkpoint.
"""

from __future__ import annotations

from datetime import datetime

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import TypedBlocker, _require


@dataclass(frozen=True)
class CanonicalNode:
    node_id: str
    episode_id: str
    chain_id: str
    stage: str
    decision_time: str
    sobt_minutes: float
    connection_airport_id: str
    destination_airport_id: str
    observed: Mapping[str, Any]
    binding: Mapping[str, float]
    history_values: tuple[tuple[float, ...], ...]
    pre_state: Mapping[str, Any]

    @property
    def history_length(self) -> int:
        return len(self.history_values)

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "episode_id": self.episode_id,
            "chain_id": self.chain_id,
            "stage": self.stage,
            "decision_time": self.decision_time,
            "sobt_minutes": float(self.sobt_minutes),
            "connection_airport_id": self.connection_airport_id,
            "destination_airport_id": self.destination_airport_id,
            "observed": dict(self.observed),
            "reference_binding": dict(self.binding),
            "pre_state": dict(self.pre_state),
            "history_length": self.history_length,
            "history_values": [list(row) for row in self.history_values],
        }

    @classmethod
    def from_payload(cls, data: Mapping[str, Any]) -> "CanonicalNode":
        rows = tuple(tuple(float(value) for value in row) for row in data["history_values"])
        _require(
            len(rows) == int(data.get("history_length", len(rows))),
            "PHASE7_CANONICAL_NODE_HISTORY_LENGTH_MISMATCH",
            data.get("node_id"),
        )
        _require(bool(rows), "PHASE7_CANONICAL_NODE_HISTORY_EMPTY", data.get("node_id"))
        width = {len(row) for row in rows}
        _require(
            len(width) == 1,
            "PHASE7_CANONICAL_NODE_HISTORY_RAGGED",
            data.get("node_id"),
        )
        _require(
            isinstance(data.get("pre_state"), Mapping),
            "PHASE7_CANONICAL_NODE_PRE_ENVIRONMENT_MISSING",
            data.get("node_id"),
        )
        return cls(
            node_id=str(data["node_id"]),
            episode_id=str(data["episode_id"]),
            chain_id=str(data["chain_id"]),
            stage=str(data["stage"]),
            decision_time=str(data["decision_time"]),
            sobt_minutes=float(data["sobt_minutes"]),
            connection_airport_id=str(data["connection_airport_id"]),
            destination_airport_id=str(data["destination_airport_id"]),
            observed=dict(data.get("observed", {})),
            binding={
                key: float(value)
                for key, value in data["reference_binding"].items()
            },
            history_values=rows,
            pre_state=dict(data["pre_state"]),
        )


def pre_environment_payload(state: Any) -> dict[str, Any]:
    """Serialize a PRE decision environment for the node checkpoint."""

    if hasattr(state, "model_dump"):
        return state.model_dump(mode="json")
    raise TypedBlocker(
        "PHASE7_PRE_ENVIRONMENT_NOT_SERIALIZABLE", type(state).__name__
    )


def restore_pre_environment(payload: Mapping[str, Any]) -> Any:
    """Rebuild the PRE decision environment from its checkpointed payload.

    JSON round-tripping turns datetimes into ISO strings. Every PRE field whose
    name ends in ``_utc`` is restored to ``datetime`` so the frozen M1 service
    consumes exactly the object it consumed at materialization time.
    """

    from model.PRE.contracts.pre_state import PREState

    return PREState.model_validate(_restore_datetimes(dict(payload)))


def _restore_datetimes(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                _as_datetime(item)
                if str(key).endswith("_utc")
                else _restore_datetimes(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_restore_datetimes(item) for item in value]
    return value


def _as_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return value


def canonical_nodes_payload(
    nodes: Sequence[CanonicalNode],
    *,
    scope: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the ``CANONICAL_NODES`` payload for one materialization scope."""

    _require(bool(nodes), "PHASE7_CANONICAL_NODES_EMPTY")
    ordered = tuple(sorted(nodes, key=lambda node: node.node_id))
    _require(
        len({node.node_id for node in ordered}) == len(ordered),
        "PHASE7_CANONICAL_NODE_ID_NOT_UNIQUE",
    )
    stage_counts: dict[str, int] = {}
    for node in ordered:
        stage_counts[node.stage] = stage_counts.get(node.stage, 0) + 1
    return {
        "materialization_scope": scope,
        "node_count": len(ordered),
        "episode_count": len({node.episode_id for node in ordered}),
        "stage_counts": dict(sorted(stage_counts.items())),
        "history_width": len(ordered[0].history_values[0]),
        "pre_environment_embedded": True,
        "provenance": dict(provenance),
        "nodes": [node.to_payload() for node in ordered],
    }


def nodes_from_payload(payload: Mapping[str, Any]) -> tuple[CanonicalNode, ...]:
    _require(
        payload.get("materialization_scope") is not None,
        "PHASE7_CANONICAL_NODES_SCOPE_MISSING",
    )
    nodes = tuple(CanonicalNode.from_payload(item) for item in payload["nodes"])
    _require(
        len(nodes) == int(payload.get("node_count", len(nodes))),
        "PHASE7_CANONICAL_NODES_COUNT_MISMATCH",
    )
    return nodes


def nodes_by_id(payload: Mapping[str, Any]) -> dict[str, CanonicalNode]:
    return {node.node_id: node for node in nodes_from_payload(payload)}


__all__ = [
    "CanonicalNode",
    "canonical_nodes_payload",
    "nodes_by_id",
    "nodes_from_payload",
    "pre_environment_payload",
    "restore_pre_environment",
]
