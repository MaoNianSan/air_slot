"""Development-safe Phase-7 executor fixture.

The fixture rebuilds canonical nodes from *frozen tracked* Development inputs:

* ``artifacts/models/pre/PRE_FORMAL_DEVELOPMENT_V1/PRE_FORMAL_DEVELOPMENT_STATES.jsonl``
  (PRE decision states, the canonical rolling environment authority), and
* ``artifacts/models/m1/M1_FROZEN_H16/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz``
  (the frozen encoded M1 input sequences).

The episode/node pairing follows the frozen bridge rule (episode identity plus
the encoded position). No Final-Test path is read, and the fixture is declared
``DEVELOPMENT_SAFE_FIXTURE_NOT_SCIENTIFIC_SUPPORT``: it exists to prove that the
DAG runs, not to make a scientific claim.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import constants as C
from ..errors import _require
from .nodes import CanonicalNode, pre_environment_payload

FIXTURE_SCHEMA = "AIR_SLOT_V2_PHASE7_DEVELOPMENT_SAFE_FIXTURE_V1"
FIXTURE_SCOPE = "DEVELOPMENT_SAFE_FIXTURE_NOT_SCIENTIFIC_SUPPORT"
DEFAULT_NODE_LIMIT = 16
FIXTURE_CONNECTION_SHARE = 0.35
FIXTURE_DOWNSTREAM_EXPOSURE = 1.2
FIXTURE_EXPECTED_PAX = 150.0
PRE_STATES_PATH = (
    C.ROOT
    / "artifacts"
    / "models"
    / "pre"
    / "PRE_FORMAL_DEVELOPMENT_V1"
    / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl"
)
M1_CACHE_PATH = (
    C.ROOT
    / "artifacts"
    / "models"
    / "m1"
    / "M1_FROZEN_H16"
    / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
)
M1_CACHE_MANIFEST_PATH = (
    C.ROOT
    / "artifacts"
    / "models"
    / "m1"
    / "M1_FROZEN_H16"
    / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
)


class DevelopmentSafeFixtureError(RuntimeError):
    """Raised when the fixture inputs are unavailable or inconsistent."""


def _iso_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _coerce_schedule_datetimes(pre_state: Any) -> None:
    """Restore the datetime objects ``M1Pipeline`` expects after JSON load."""

    schedule = pre_state.successor_state.get("schedule_reference")
    if schedule is None or not isinstance(schedule.value, dict):
        return
    for key in ("scheduled_departure_utc", "scheduled_arrival_utc"):
        value = schedule.value.get(key)
        if isinstance(value, str):
            schedule.value[key] = datetime.fromisoformat(value)


def load_fixture_pre_states(path: Path | None = None) -> dict[tuple[str, int], Any]:
    """Parse the frozen PRE decision states keyed by ``(episode_id, node_index)``."""

    from model.PRE.contracts.pre_state import PREState

    target = Path(path) if path is not None else PRE_STATES_PATH
    if not target.is_file():
        raise DevelopmentSafeFixtureError(f"FIXTURE_PRE_STATES_MISSING:{target}")
    states: dict[tuple[str, int], Any] = {}
    with target.open(encoding="utf-8") as stream:
        for line in stream:
            state = PREState.model_validate_json(line)
            _coerce_schedule_datetimes(state)
            key = (state.decision_node.episode_id, int(state.decision_node.node_index))
            if key in states:
                raise DevelopmentSafeFixtureError(f"FIXTURE_DUPLICATE_PRE_STATE:{key}")
            states[key] = state
    return states


def load_fixture_cache(cache_path: Path | None = None, manifest_path: Path | None = None):
    """Load the frozen H16 Development base cache (read-only)."""

    from model.M1.cache import M1DevelopmentBaseCache

    cache_target = Path(cache_path) if cache_path is not None else M1_CACHE_PATH
    manifest_target = (
        Path(manifest_path) if manifest_path is not None else M1_CACHE_MANIFEST_PATH
    )
    for target in (cache_target, manifest_target):
        if not target.is_file():
            raise DevelopmentSafeFixtureError(f"FIXTURE_CACHE_MISSING:{target}")
    manifest = json.loads(manifest_target.read_text(encoding="utf-8"))
    return M1DevelopmentBaseCache.load(
        cache_target,
        manifest_target,
        expected_cache_key=manifest["cache_key"],
        allow_legacy_schema=True,
    )


def build_development_safe_nodes(
    *,
    node_limit: int = DEFAULT_NODE_LIMIT,
    pre_states_path: Path | None = None,
    cache_path: Path | None = None,
    cache_manifest_path: Path | None = None,
) -> tuple[tuple[CanonicalNode, ...], dict[str, Any]]:
    """Build the deterministic Development-safe canonical node subset."""

    limit = int(node_limit)
    if limit <= 0:
        raise DevelopmentSafeFixtureError("FIXTURE_NODE_LIMIT_MUST_BE_POSITIVE")
    states = load_fixture_pre_states(pre_states_path)
    cache = load_fixture_cache(cache_path, cache_manifest_path)
    rows = sorted(
        cache.partition("development"),
        key=lambda row: (str(row.episode_id), len(row.values) - 1),
    )
    if not rows:
        raise DevelopmentSafeFixtureError("FIXTURE_DEVELOPMENT_CACHE_EMPTY")
    selected = rows[:limit]
    nodes: list[CanonicalNode] = []
    identity_disagreements = 0
    for row in selected:
        position = len(row.values) - 1
        state = states.get((str(row.episode_id), position))
        if state is None:
            raise DevelopmentSafeFixtureError(
                f"FIXTURE_PRE_STATE_MISSING:{row.episode_id}:{position}"
            )
        if state.decision_node.decision_node_id != row.decision_node_id:
            identity_disagreements += 1
        schedule = state.successor_state.get("schedule_reference")
        route = state.successor_state.get("route_context")
        if schedule is None or route is None:
            raise DevelopmentSafeFixtureError(
                f"FIXTURE_PRE_REFERENCE_MISSING:{state.decision_node.decision_node_id}"
            )
        schedule_value = schedule.value
        route_value = route.value
        if not isinstance(schedule_value, dict) or not isinstance(route_value, dict):
            raise DevelopmentSafeFixtureError(
                f"FIXTURE_PRE_REFERENCE_INVALID:{state.decision_node.decision_node_id}"
            )
        decision_time = state.decision_node.decision_time
        sobt = _iso_datetime(schedule_value["scheduled_departure_utc"])
        sobt_minutes = (sobt - decision_time).total_seconds() / 60.0
        turnaround = state.successor_state.get("turnaround_reference")
        turnaround_value = None if turnaround is None else turnaround.value
        turnaround_reference = (
            float(turnaround_value["value"])
            if isinstance(turnaround_value, dict)
            and isinstance(turnaround_value.get("value"), (int, float))
            else C.NOMINAL_TURNAROUND_Q20
        )
        nodes.append(
            CanonicalNode(
                node_id=str(row.decision_node_id),
                episode_id=str(row.episode_id),
                chain_id=str(row.episode_id),
                stage=str(state.decision_node.operational_stage.value),
                decision_time=decision_time.isoformat(),
                sobt_minutes=float(sobt_minutes),
                connection_airport_id=str(route_value["origin_airport_id"]),
                destination_airport_id=str(route_value["destination_airport_id"]),
                observed=_observed_for_fixture(state),
                binding={
                    "turnaround_reference_minutes": turnaround_reference,
                    "taxi_reference_minutes": 0.0,
                    "expected_pax": FIXTURE_EXPECTED_PAX,
                    "connection_share": FIXTURE_CONNECTION_SHARE,
                    "downstream_exposure": FIXTURE_DOWNSTREAM_EXPOSURE,
                },
                history_values=tuple(
                    tuple(float(value) for value in row_values)
                    for row_values in row.values.tolist()
                ),
                pre_state=pre_environment_payload(state),
            )
        )
    provenance = {
        "fixture_schema": FIXTURE_SCHEMA,
        "fixture_scope": FIXTURE_SCOPE,
        "node_selection_rule": "FIRST_N_DEVELOPMENT_NODES_ORDERED_BY_EPISODE_AND_POSITION",
        "node_limit": limit,
        "pre_states_path": str(PRE_STATES_PATH),
        "m1_cache_path": str(M1_CACHE_PATH),
        "m1_cache_manifest_path": str(M1_CACHE_MANIFEST_PATH),
        "final_test_data_read": False,
        "q4_raw_read": False,
        "legacy_final_test_result_tree_read": False,
        "reference_binding_semantics": (
            "TURNAROUND_FROM_PRE_PUBLISHED_A2_REFERENCE; "
            "PAX_CONNECTION_DOWNSTREAM_SYNTHETIC_FIXTURE_CONSTANTS"
        ),
        "transition_frame_note": (
            "sobt_minutes is published in the M1 scenario frame "
            "(minutes from the decision time to SOBT); the executor consumes it "
            "verbatim and never re-derives the frame"
        ),
        "pre_state_node_identity_disagreements": identity_disagreements,
        "pre_state_node_identity_semantics": (
            "PRE_STATE_AND_M1_CACHE_NODE_ID_NAMESPACES_DIFFER_IN_THIS_REVISION; "
            "PAIRING_FOLLOWS_THE_FROZEN_BRIDGE_POSITIONAL_RULE"
        ),
    }
    return tuple(nodes), provenance


def _observed_for_fixture(state: Any) -> dict[str, Any]:
    from model.M1.factual_state import factual_observed_state

    observed = factual_observed_state(state)
    return {
        key: (value.isoformat() if isinstance(value, datetime) else value)
        for key, value in observed.items()
    }


def fixture_checkpoint_payload(
    *, node_limit: int = DEFAULT_NODE_LIMIT
) -> dict[str, Any]:
    from .nodes import canonical_nodes_payload

    nodes, provenance = build_development_safe_nodes(node_limit=node_limit)
    return canonical_nodes_payload(
        nodes,
        scope=FIXTURE_SCOPE,
        provenance=provenance,
    )


def require_fixture_payload(payload: Any) -> dict[str, Any]:
    _require(
        isinstance(payload, dict)
        and payload.get("materialization_scope") == FIXTURE_SCOPE,
        "PHASE7_CANONICAL_NODES_NOT_DEVELOPMENT_SAFE_FIXTURE",
        None if not isinstance(payload, dict) else payload.get("materialization_scope"),
    )
    return payload


__all__ = [
    "DEFAULT_NODE_LIMIT",
    "FIXTURE_SCOPE",
    "DevelopmentSafeFixtureError",
    "build_development_safe_nodes",
    "fixture_checkpoint_payload",
    "load_fixture_cache",
    "load_fixture_pre_states",
    "require_fixture_payload",
]
