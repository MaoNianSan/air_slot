"""Canonical decision-node records carried by the Phase-7 DAG.

A ``CanonicalNode`` is the *materialization boundary* object: it carries the
node identity, the M1 input sequence, the PRE-published observed state and the
M2 reference binding. The one-shot Final-Test materialization entry publishes
it; every downstream stage only consumes it from an immutable checkpoint.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping, Sequence

from dataclasses import dataclass

from ..errors import TypedBlocker, _require

CANONICAL_STAGE_NODE_RULE = (
    "ONE_NODE_PER_EPISODE_STAGE_BY_DECISION_TIME_NODE_ID_BEFORE_SUPPORT"
)
ROLLING_IDENTITY_SCHEMA = (
    "AIR_SLOT_V2_PHASE7_MATERIALIZED_ROLLING_IDENTITY_V1"
)
ROLLING_REFERENCE_SUPPORTED = "SUPPORTED"
ROLLING_REFERENCE_UNSUPPORTED = "UNSUPPORTED_REFERENCE"


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
        rows = tuple(
            tuple(float(value) for value in row)
            for row in data["history_values"]
        )
        _require(
            len(rows) == int(data.get("history_length", len(rows))),
            "PHASE7_CANONICAL_NODE_HISTORY_LENGTH_MISMATCH",
            data.get("node_id"),
        )
        _require(
            bool(rows),
            "PHASE7_CANONICAL_NODE_HISTORY_EMPTY",
            data.get("node_id"),
        )
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


def canonicalize_stage_nodes(
    nodes: Sequence[CanonicalNode],
) -> tuple[CanonicalNode, ...]:
    """Return one canonical node per ``(episode_id, operational_stage)``.

    The selection uses only the frozen identity fields. Support, representation,
    priority and outcome information are intentionally unavailable here.
    """

    grouped: dict[tuple[str, str], list[CanonicalNode]] = defaultdict(list)
    for node in nodes:
        grouped[(str(node.episode_id), str(node.stage))].append(node)
    selected = [
        min(
            group,
            key=lambda node: (
                _decision_time_key(node.decision_time),
                str(node.node_id),
            ),
        )
        for group in grouped.values()
        if group
    ]
    return tuple(sorted(selected, key=_canonical_order_key))


def canonical_stage_identity(
    node_id: Any,
    episode_id: Any,
    stage: Any,
) -> tuple[str, str, str]:
    """Return the frozen ``(episode_id, stage, node_id)`` selection identity."""

    return (str(episode_id), str(stage), str(node_id))


def canonical_stage_group(
    identities: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Select one identity per ``(episode_id, operational_stage)``.

    ``identities`` must carry ``episode_id``, ``stage``, ``decision_time`` and
    ``node_id``. Support, representation, priority and outcome fields are
    deliberately not read, so the projected identity is immutable across every
    representation and every support state.
    """

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for identity in identities:
        grouped[
            (str(identity["episode_id"]), str(identity["stage"]))
        ].append(identity)
    selected: list[Mapping[str, Any]] = []
    for group in grouped.values():
        selected.append(
            min(
                group,
                key=lambda item: (
                    _decision_time_key(item["decision_time"]),
                    str(item["node_id"]),
                ),
            )
        )
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                str(item["episode_id"]),
                str(item["stage"]),
                _decision_time_key(item["decision_time"]),
                str(item["node_id"]),
            ),
        )
    )


def canonical_decision_node_ids(
    identities: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return the canonical node ids selected from rolling identities."""

    return tuple(
        str(item["node_id"]) for item in canonical_stage_group(identities)
    )


def rolling_identities_from_nodes(
    nodes: Sequence[CanonicalNode],
    *,
    canonical_ids: Sequence[str],
    reference_support: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Build identity records for a set of fully bound canonical nodes."""

    selected = {str(node_id) for node_id in canonical_ids}
    support = dict(reference_support or {})
    return tuple(
        {
            "schema_version": ROLLING_IDENTITY_SCHEMA,
            "node_id": node.node_id,
            "episode_id": node.episode_id,
            "chain_id": node.chain_id,
            "stage": node.stage,
            "decision_time": node.decision_time,
            "canonical_selected": node.node_id in selected,
            "reference_support": support.get(
                node.node_id, ROLLING_REFERENCE_SUPPORTED
            ),
        }
        for node in _ordered_nodes(nodes)
    )


def _rolling_identity_from_payload(
    item: Mapping[str, Any],
) -> dict[str, Any]:
    for field in ("node_id", "episode_id", "stage", "decision_time"):
        _require(
            item.get(field) is not None,
            "PHASE7_MATERIALIZED_ROLLING_NODE_IDENTITY_INCOMPLETE",
            {"missing": field, "item": dict(item)},
        )
    return {
        "schema_version": item.get(
            "schema_version", ROLLING_IDENTITY_SCHEMA
        ),
        "node_id": str(item["node_id"]),
        "episode_id": str(item["episode_id"]),
        "chain_id": str(item.get("chain_id", item["episode_id"])),
        "stage": str(item["stage"]),
        "decision_time": str(item["decision_time"]),
        "canonical_selected": bool(item.get("canonical_selected", False)),
        "reference_support": str(
            item.get("reference_support", ROLLING_REFERENCE_SUPPORTED)
        ),
    }


def assert_canonical_stage_uniqueness(
    nodes: Sequence[CanonicalNode],
) -> None:
    """Fail closed when more than one node survives per episode-stage."""

    counts: dict[tuple[str, str], int] = defaultdict(int)
    for node in nodes:
        counts[(str(node.episode_id), str(node.stage))] += 1
    duplicates = {
        f"{episode_id}|{stage}": count
        for (episode_id, stage), count in counts.items()
        if count != 1
    }
    _require(
        not duplicates,
        "PHASE7_STAGE1_NONCANONICAL_EPISODE_STAGE_DUPLICATION",
        duplicates,
    )


def _decision_time_key(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as error:
        raise TypedBlocker(
            "PHASE7_CANONICAL_NODE_DECISION_TIME_INVALID", value
        ) from error


def _canonical_order_key(node: CanonicalNode) -> tuple[Any, ...]:
    return (
        str(node.episode_id),
        str(node.stage),
        _decision_time_key(node.decision_time),
        str(node.node_id),
    )


def _stage_counts(nodes: Sequence[CanonicalNode]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        stage = str(node.stage)
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


def _rolling_stage_counts(
    identities: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for identity in identities:
        stage = str(identity["stage"])
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


def _ordered_nodes(nodes: Sequence[CanonicalNode]) -> tuple[CanonicalNode, ...]:
    return tuple(sorted(nodes, key=_canonical_order_key))


def canonical_nodes_payload(
    nodes: Sequence[CanonicalNode],
    *,
    scope: str,
    provenance: Mapping[str, Any],
    canonical_nodes: Sequence[CanonicalNode] | None = None,
    materialized_rolling_identities: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the ``CANONICAL_NODES`` payload for one materialization scope.

    ``nodes`` carries the materialized rolling observations. The canonical
    Stage-I decision set is derived from their frozen identities only
    (``episode_id``, ``operational_stage``, ``decision_time``, ``node_id``) and
    is exactly one node per ``(episode_id, operational_stage)``.

    ``canonical_nodes`` optionally supplies an already projected canonical set;
    ``materialized_rolling_identities`` optionally supplies the separate
    diagnostic object that preserves every materialized rolling observation,
    including observations canonicalization did not select. Stage-I consumes
    only the canonical decision nodes.
    """

    if canonical_nodes is None:
        ordered_rolling = _ordered_nodes(nodes)
        ordered = canonicalize_stage_nodes(ordered_rolling)
        canonical_ids = {node.node_id for node in ordered}
        rolling = (
            tuple(materialized_rolling_identities)
            if materialized_rolling_identities is not None
            else rolling_identities_from_nodes(
                ordered_rolling, canonical_ids=canonical_ids
            )
        )
    else:
        ordered = _ordered_nodes(canonical_nodes)
        canonical_ids = {node.node_id for node in ordered}
        rolling = (
            tuple(materialized_rolling_identities)
            if materialized_rolling_identities is not None
            else rolling_identities_from_nodes(
                ordered, canonical_ids=canonical_ids
            )
        )
    rolling = tuple(
        _rolling_identity_from_payload(item) for item in rolling
    )
    _require(bool(ordered), "PHASE7_CANONICAL_NODES_EMPTY")
    assert_canonical_stage_uniqueness(ordered)
    _require(bool(rolling), "PHASE7_MATERIALIZED_ROLLING_NODES_EMPTY")
    rolling_ids = [item["node_id"] for item in rolling]
    _require(
        len(set(rolling_ids)) == len(rolling_ids),
        "PHASE7_CANONICAL_NODE_ID_NOT_UNIQUE",
    )
    _require(
        canonical_ids <= set(rolling_ids),
        "PHASE7_CANONICAL_NODES_NOT_IN_ROLLING_IDENTITY_SET",
        sorted(canonical_ids - set(rolling_ids)),
    )
    flagged = sorted(
        item["node_id"] for item in rolling if item["canonical_selected"]
    )
    _require(
        flagged == sorted(canonical_ids),
        "PHASE7_CANONICAL_NODES_SELECTION_FLAG_MISMATCH",
        {"canonical": sorted(canonical_ids), "flagged": flagged},
    )
    return {
        "materialization_scope": scope,
        "node_count": len(ordered),
        "canonical_decision_node_count": len(ordered),
        "canonical_decision_node_ids": [node.node_id for node in ordered],
        "episode_count": len({node.episode_id for node in ordered}),
        "stage_counts": _stage_counts(ordered),
        "canonical_stage_counts": _stage_counts(ordered),
        "materialized_rolling_node_count": len(rolling),
        "materialized_rolling_node_ids": [
            item["node_id"] for item in rolling
        ],
        "rolling_stage_counts": _rolling_stage_counts(rolling),
        "canonical_selected_rolling_node_count": len(flagged),
        "history_width": len(ordered[0].history_values[0]),
        "pre_environment_embedded": True,
        "canonicalization": {
            "rule": CANONICAL_STAGE_NODE_RULE,
            "group_by": ["episode_id", "operational_stage"],
            "order_by": ["decision_time", "node_id"],
            "selected_without_support_information": True,
            "support_filtering_after_canonicalization": True,
            "materialized_rolling_node_count": len(rolling),
            "canonical_decision_node_count": len(ordered),
        },
        "provenance": dict(provenance),
        "nodes": [node.to_payload() for node in ordered],
        "materialized_rolling_nodes": [dict(item) for item in rolling],
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
    assert_canonical_stage_uniqueness(nodes)
    return nodes


def rolling_nodes_from_payload(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    items = payload.get("materialized_rolling_nodes")
    _require(
        isinstance(items, Sequence),
        "PHASE7_MATERIALIZED_ROLLING_NODES_MISSING",
        type(items).__name__,
    )
    identities = tuple(
        _rolling_identity_from_payload(item) for item in items
    )
    _require(
        len(identities)
        == int(payload.get("materialized_rolling_node_count", len(identities))),
        "PHASE7_MATERIALIZED_ROLLING_NODES_COUNT_MISMATCH",
    )
    return identities


rolling_identities_from_payload = rolling_nodes_from_payload

def nodes_by_id(payload: Mapping[str, Any]) -> dict[str, CanonicalNode]:
    return {node.node_id: node for node in nodes_from_payload(payload)}


__all__ = [
    "CANONICAL_STAGE_NODE_RULE",
    "CanonicalNode",
    "assert_canonical_stage_uniqueness",
    "canonical_nodes_payload",
    "canonicalize_stage_nodes",
    "nodes_by_id",
    "nodes_from_payload",
    "pre_environment_payload",
    "restore_pre_environment",
    "rolling_nodes_from_payload",
    "rolling_identities_from_nodes",
    "rolling_identities_from_payload",
]
