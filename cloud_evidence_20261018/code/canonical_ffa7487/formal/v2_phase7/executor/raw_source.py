"""Authorized one-shot Final-Test raw-source materialization.

``CANONICAL_NODES`` is the only DAG stage that may read a Final-Test raw
source, and it may do so exactly once per authorized access epoch. This module
implements the production raw-source adapter behind
:mod:`formal.v2_phase7.executor.raw_entry`:

    frozen cohort manifest
    -> raw episode reconstruction
    -> frozen PRE publication
    -> frozen M1 input sequences and PRE observed state
    -> frozen M2 node reference binding
    -> canonical nodes

No PRE rule, M1 rule, M2 formula, reference rule or M3/M4 rule is
re-implemented here. The adapter calls the frozen services:

* ``model.PRE`` for episode construction, rolling decision nodes and PRE state
  publication (with the frozen ``ProductionPREPublisher``),
* ``model.M1`` for the frozen input encoding and the PRE-observed adapter,
* ``validation.v2_phase5.common.build_node_binding`` for the frozen M2 node
  reference binding (corrected A2 airport-cell median turnaround reference,
  global fallback 57.0, per freeze ruling R7/R8).

Two boundary rules are owned by this module and are recorded in the published
materialization provenance:

* nodes whose frozen M2 reference binding abstains stay typed
  ``UNSUPPORTED_REFERENCE`` and are excluded, never zero-filled (the frozen
  Phase-5 handling of the four PGV->CLT Development nodes),
* every raw and reference file that is read is recorded with its SHA-256.

Importing this module reads nothing. Raw reads happen only inside
:func:`materialize_raw_source`, which is reachable only after
``raw_entry.validate_materialization_authorization`` accepted a human release
and an open access epoch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..materialization import _canonical_text_sha256, _file_sha256, _read_json, _sha256_bytes
from .nodes import (
    ROLLING_IDENTITY_SCHEMA,
    ROLLING_REFERENCE_SUPPORTED,
    ROLLING_REFERENCE_UNSUPPORTED,
    CanonicalNode,
    canonical_nodes_payload,
    pre_environment_payload,
)
from .raw_entry import MATERIALIZATION_SCOPE
from .services import FrozenScienceServices, load_frozen_services

RAW_SOURCE_ADAPTER_ID = C.RAW_SOURCE_ADAPTER_ID
RAW_SOURCE_PROFILE_SCHEMA = "AIR_SLOT_V2_PHASE7_RAW_SOURCE_PROFILE_V1"
PRODUCTION_RAW_PROFILE_ID = "FINAL_TEST_Q4_FROZEN_COHORT"
LOCAL_INPUT_ROOT_ENV = C.PHASE7_LOCAL_INPUT_ROOT_ENV
UNSUPPORTED_REFERENCE_STATE = "UNSUPPORTED_REFERENCE"
FINAL_TEST_EPISODE_COUNT = 128

#: Project-relative frozen reference payloads used by the frozen M2 reference
#: bundle. These are exactly the payloads consumed by the frozen Development
#: pipeline (``exp.exp2.development_inputs._reference_payloads``); the declared
#: paths are re-checked against that module in the Phase-7 tests.
REFERENCE_PAYLOAD_FILES: Mapping[str, str] = {
    "turnaround": (
        "artifacts/diagnostics/m1_v2_data_gate_a2/"
        "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
    ),
    "taxi": (
        "artifacts/diagnostics/v5_development_freeze/"
        "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
    ),
    "downstream_exposure": (
        "artifacts/diagnostics/v5_development_freeze/"
        "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json"
    ),
    "passenger": (
        "artifacts/diagnostics/v5_development_freeze/"
        "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json"
    ),
    "expected_passengers": (
        "artifacts/diagnostics/passenger_reference_freeze_v4/"
        "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json"
    ),
    "connection_share": (
        "artifacts/diagnostics/passenger_reference_freeze_v4/"
        "DB1B_CONNECTION_SHARE_REFERENCE.json"
    ),
}

#: Project-relative raw month files required by one materialization window.
RAW_ONTIME_FILE_TEMPLATE = (
    "data2/raw/bts/ontime/2019/month={month:02d}"
)

#: Local-only inputs the frozen execution worktree may not carry: the BTS
#: on-time raw files and the two over-100MB passenger reference payloads are
#: gitignored ("kept local") by project policy.
LOCAL_ONLY_INPUTS: tuple[str, ...] = (
    "data2/raw/bts/ontime/2019/month=10",
    "data2/raw/bts/ontime/2019/month=11",
    "data2/raw/bts/ontime/2019/month=12",
    "data2/raw/weather/noaa/2019",
    REFERENCE_PAYLOAD_FILES["expected_passengers"],
    REFERENCE_PAYLOAD_FILES["connection_share"],
)


@dataclass(frozen=True)
class RawMaterializationProfile:
    """One declared raw-source materialization window."""

    profile_id: str
    materialization_scope: str
    cohort_manifest_path: Path
    cohort_manifest_file_sha256: str
    cohort_ids_field: str
    expected_episode_count: int
    expected_selected_episode_hash: str
    expected_executed_manifest_sha256: str
    source_months: tuple[int, ...]
    allow_final_test: bool
    expected_split: str
    weather_start_inclusive: date | None
    weather_end_exclusive: date
    final_test_data_read: bool

    def as_metadata(self) -> dict[str, Any]:
        return {
            "profile_schema": RAW_SOURCE_PROFILE_SCHEMA,
            "profile_id": self.profile_id,
            "materialization_scope": self.materialization_scope,
            "cohort_manifest_path": str(
                self.cohort_manifest_path.relative_to(C.ROOT)
            )
            if C.ROOT in self.cohort_manifest_path.parents
            else str(self.cohort_manifest_path),
            "cohort_manifest_file_sha256": self.cohort_manifest_file_sha256,
            "expected_episode_count": int(self.expected_episode_count),
            "expected_selected_episode_hash": (
                self.expected_selected_episode_hash
            ),
            "expected_executed_manifest_sha256": (
                self.expected_executed_manifest_sha256
            ),
            "source_months": [int(month) for month in self.source_months],
            "allow_final_test": bool(self.allow_final_test),
            "expected_split": self.expected_split,
            "final_test_data_read": bool(self.final_test_data_read),
        }


PRODUCTION_RAW_PROFILE = RawMaterializationProfile(
    profile_id=PRODUCTION_RAW_PROFILE_ID,
    materialization_scope=MATERIALIZATION_SCOPE,
    cohort_manifest_path=C.COHORT_MANIFEST_PATH,
    cohort_manifest_file_sha256=C.COHORT_MANIFEST_FILE_SHA256,
    cohort_ids_field="selected_episode_ids",
    expected_episode_count=FINAL_TEST_EPISODE_COUNT,
    expected_selected_episode_hash=C.SELECTED_EPISODE_HASH,
    expected_executed_manifest_sha256=C.EXECUTED_COHORT_MANIFEST_SHA256,
    source_months=(10, 11, 12),
    allow_final_test=True,
    expected_split="test",
    weather_start_inclusive=date(2019, 10, 1),
    weather_end_exclusive=date(2020, 1, 1),
    final_test_data_read=True,
)


def missing_local_inputs(root: Path) -> tuple[str, ...]:
    """Return the declared local-only inputs that are absent under ``root``."""

    target = Path(root)
    return tuple(
        relative
        for relative in LOCAL_ONLY_INPUTS
        if not (target / relative).exists()
    )


def resolve_local_input_root(
    explicit: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Resolve the read-only root that carries the local-only inputs.

    The frozen execution worktree carries every versioned artifact, but the
    BTS raw files and the two over-100MB passenger reference payloads are
    gitignored by project policy. The root is therefore explicit: the
    worktree itself when it carries the inputs, otherwise an operator-declared
    root. Nothing is guessed silently.
    """

    if explicit is not None:
        root = Path(explicit)
        resolution = "EXPLICIT_ARGUMENT"
    elif os.environ.get(LOCAL_INPUT_ROOT_ENV):
        root = Path(os.environ[LOCAL_INPUT_ROOT_ENV])
        resolution = "ENVIRONMENT_VARIABLE"
    elif not missing_local_inputs(C.ROOT):
        root = C.ROOT
        resolution = "FROZEN_EXECUTION_WORKTREE"
    else:
        raise TypedBlocker(
            "PHASE7_LOCAL_INPUT_ROOT_REQUIRED",
            {
                "environment_variable": LOCAL_INPUT_ROOT_ENV,
                "worktree": str(C.ROOT),
                "worktree_missing_inputs": list(missing_local_inputs(C.ROOT)),
                "note": (
                    "raw BTS months and the over-100MB passenger reference "
                    "payloads are local-only inputs; declare their read-only "
                    "root explicitly instead of guessing a data source"
                ),
            },
        )
    _require(
        root.is_dir(),
        "PHASE7_LOCAL_INPUT_ROOT_MISSING",
        str(root),
    )
    missing = missing_local_inputs(root)
    _require(
        not missing,
        "PHASE7_LOCAL_INPUT_ROOT_INCOMPLETE",
        {"root": str(root), "missing": list(missing)},
    )
    return root, {
        "local_input_root": str(root),
        "local_input_root_resolution": resolution,
        "local_input_root_environment_variable": LOCAL_INPUT_ROOT_ENV,
        "local_input_root_local_only_inputs": list(LOCAL_ONLY_INPUTS),
    }


def load_cohort_manifest(profile: RawMaterializationProfile) -> tuple[str, ...]:
    """Load and validate the frozen cohort manifest named by ``profile``."""

    path = Path(profile.cohort_manifest_path)
    _require(path.is_file(), "PHASE7_RAW_COHORT_MANIFEST_MISSING", str(path))
    _require(
        _canonical_text_sha256(path) == profile.cohort_manifest_file_sha256,
        "PHASE7_RAW_COHORT_MANIFEST_FILE_HASH_MISMATCH",
        str(path),
    )
    manifest = _read_json(path)
    _require(
        manifest.get("authority_status") == "FINAL_TEST_COHORT_AUTHORITY_LOCKED",
        "PHASE7_RAW_COHORT_MANIFEST_STATUS_INVALID",
        manifest.get("authority_status"),
    )
    episode_ids = tuple(
        str(value) for value in manifest.get(profile.cohort_ids_field, ())
    )
    _require(
        len(episode_ids) == profile.expected_episode_count
        and len(set(episode_ids)) == len(episode_ids),
        "PHASE7_RAW_COHORT_EPISODE_ID_INVALID",
        {
            "observed": len(episode_ids),
            "expected": profile.expected_episode_count,
        },
    )
    payload_hash = _sha256_bytes("\n".join(sorted(episode_ids)).encode("utf-8"))
    _require(
        payload_hash == profile.expected_selected_episode_hash,
        "PHASE7_RAW_COHORT_SELECTED_EPISODE_HASH_MISMATCH",
        payload_hash,
    )
    _require(
        manifest.get("artifact_manifest_sha256")
        == profile.expected_executed_manifest_sha256,
        "PHASE7_RAW_COHORT_EXECUTED_MANIFEST_HASH_MISMATCH",
        manifest.get("artifact_manifest_sha256"),
    )
    _require(
        manifest.get("selection_reused") is True
        and manifest.get("selection_reperformed") is False,
        "PHASE7_RAW_COHORT_SELECTION_REUSE_INVALID",
    )
    return tuple(sorted(episode_ids))


def reconstruct_episodes(
    profile: RawMaterializationProfile,
    episode_ids: Sequence[str],
    *,
    source_root: Path,
):
    """Rebuild the frozen cohort episodes from the declared raw window."""

    from model.PRE.episode.builder import build_data2_episode_records
    from model.PRE.streaming.data2 import (
        aircraft_tail,
        lightweight_flights,
        load_timezones,
        ontime_paths,
    )

    root = Path(source_root)
    data2_root = root / "data2"
    paths = ontime_paths(
        root,
        months=profile.source_months,
        allow_final_test=profile.allow_final_test,
    )
    zones = load_timezones(data2_root / "refs" / "us_airport_timezones.csv")
    wanted = set(str(value) for value in episode_ids)
    found: dict[str, Any] = {}
    carry: tuple[Any, ...] = ()
    for path in paths:
        rows, _skipped = lightweight_flights(
            path, zones, include_warning_fields=True
        )
        chunk = list(carry) + list(rows)
        for episode in sorted(
            build_data2_episode_records(chunk),
            key=lambda item: item.episode_id,
        ):
            if episode.episode_id in wanted and episode.episode_id not in found:
                found[episode.episode_id] = episode
        carry = aircraft_tail(rows)
    missing = sorted(wanted - set(found))
    _require(
        not missing,
        "PHASE7_RAW_COHORT_EPISODE_RECONSTRUCTION_FAILED",
        {"missing_count": len(missing), "missing_preview": missing[:8]},
    )
    return tuple(found[key] for key in sorted(wanted))


def publish_pre_states(
    episodes: Sequence[Any],
    *,
    profile: RawMaterializationProfile,
    source_root: Path,
    taxi_reference: Any,
    turnaround_reference: Any,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Publish the frozen PRE states for the reconstructed episodes."""

    from model.PRE.cohort import split_for_date
    from model.PRE.development import _publish_partition
    from model.PRE.pipeline import ProductionPREPublisher
    from model.PRE.streaming.data2 import (
        config_hash,
        load_selected_typed_records,
        load_timezones,
        ontime_paths,
        registry_hash,
        weather_index,
    )
    from model.common.config import load_config_layers

    root = Path(source_root)
    data2_root = root / "data2"
    paths = ontime_paths(
        root,
        months=profile.source_months,
        allow_final_test=profile.allow_final_test,
    )
    zones = load_timezones(data2_root / "refs" / "us_airport_timezones.csv")
    schedules, outcomes = load_selected_typed_records(episodes, paths, zones)
    split_violations = [
        str(episode.episode_id)
        for episode in episodes
        if split_for_date(
            schedules[episode.successor_flight_id].service_date
        )
        != profile.expected_split
    ]
    _require(
        not split_violations,
        "PHASE7_RAW_COHORT_SPLIT_VIOLATION",
        {
            "expected": profile.expected_split,
            "violations": len(split_violations),
            "preview": split_violations[:8],
        },
    )
    scientific = load_config_layers(C.ROOT / "configs").scientific
    replay_lag = int(
        scientific.parameters["data2_weather_replay_lag_minutes"].value
    )
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        data2_root,
        replay_lag,
        start_inclusive=profile.weather_start_inclusive,
        end_exclusive=profile.weather_end_exclusive,
    )
    items = {
        episode.episode_id: (
            episode,
            schedules[episode.successor_flight_id],
            outcomes[episode.predecessor_flight_id],
            outcomes[episode.successor_flight_id],
        )
        for episode in episodes
    }
    published, stage_counts = _publish_partition(
        episodes,
        items,
        config_hash_value=config_hash(C.ROOT),
        registry_hash_value=registry_hash(C.ROOT),
        weather=weather,
        weather_max_age_minutes=max_age,
        publisher=ProductionPREPublisher.from_project(),
        taxi_reference=taxi_reference,
        turnaround_reference=turnaround_reference,
    )
    audit = {
        "episode_count": len(published),
        "rolling_node_count": sum(len(item.nodes) for item in published),
        "stage_counts": dict(stage_counts),
        "weather_audit": weather_audit,
        "weather_replay_lag_minutes": replay_lag,
        "weather_max_age_minutes": max_age,
    }
    return published, audit


def build_node_records(
    published: Sequence[Any],
    *,
    normalization: Any,
    taxi_reference: Any,
    reference_bundle: Any,
) -> tuple[tuple[CanonicalNode, ...], tuple[dict[str, Any], ...]]:
    """Project materialized rolling nodes onto canonical stage nodes.

    The frozen contract is a two-object projection:

    * ``MATERIALIZED_ROLLING_NODES`` - every active rolling observation with
      its frozen identity and its M2 reference-support status,
    * ``CANONICAL_DECISION_NODES`` - exactly one decision node per
      ``(episode_id, operational_stage)``.

    The canonical identity is selected from the rolling identities alone, using
    only ``(decision_time, node_id)`` inside each ``(episode_id, stage)`` group.
    Support, representation, priority and realized-outcome information are
    deliberately not consulted, so a canonical node that later fails support
    stays a typed abstention instead of being replaced by a later node.
    """

    nodes, excluded, _rolling = materialize_node_records(
        published,
        normalization=normalization,
        taxi_reference=taxi_reference,
        reference_bundle=reference_bundle,
    )
    return nodes, excluded


def materialize_node_records(
    published: Sequence[Any],
    *,
    normalization: Any,
    taxi_reference: Any,
    reference_bundle: Any,
) -> tuple[
    tuple[CanonicalNode, ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    """Build canonical nodes, typed exclusions and rolling identities.

    Canonicalization happens *before* reference support: every materialized
    rolling identity is enumerated first, the canonical node per
    ``(episode_id, operational_stage)`` is selected from identity fields only,
    and only then is the M2 reference binding resolved. A canonical node whose
    reference abstains is preserved as a typed abstention.
    """

    from model.M1.coverage import active_node_prefixes
    from model.M1.data import encode_pre_sequence
    from model.M1.factual_state import factual_observed_state
    from validation.v2_phase5.common import (
        build_node_binding,
        chain_id_for_episode,
    )

    materialized: list[dict[str, Any]] = []
    for prepared in published:
        chain_id = str(chain_id_for_episode(prepared.episode))
        taxi_minutes, taxi_id, taxi_hash = _taxi_reference(
            taxi_reference, prepared.episode.connection_airport_id
        )
        for node, prefix, _labels in active_node_prefixes(
            episode=prepared.episode,
            nodes=prepared.nodes,
            states=prepared.states,
            successor_schedule=prepared.successor_schedule,
            predecessor_outcome=prepared.predecessor_outcome,
            successor_outcome=prepared.successor_outcome,
            taxi_reference_minutes=taxi_minutes,
            taxi_reference_id=taxi_id,
            taxi_reference_hash=taxi_hash,
        ):
            state = prefix[-1]
            route = state.successor_state.get("route_context")
            route_value = None if route is None else route.value
            _require(
                isinstance(route_value, dict)
                and route_value.get("destination_airport_id"),
                "PHASE7_RAW_NODE_ROUTE_CONTEXT_MISSING",
                node.decision_node_id,
            )
            schedule = state.successor_state.get("schedule_reference")
            schedule_value = None if schedule is None else schedule.value
            _require(
                isinstance(schedule_value, dict)
                and schedule_value.get("scheduled_departure_utc") is not None,
                "PHASE7_RAW_NODE_SCHEDULE_REFERENCE_MISSING",
                node.decision_node_id,
            )
            resolved = build_node_binding(
                node_id=str(node.decision_node_id),
                episode_id=str(node.episode_id),
                chain_id=chain_id,
                connection_airport_id=str(
                    prepared.episode.connection_airport_id
                ),
                destination_airport_id=str(
                    route_value["destination_airport_id"]
                ),
                decision_time=node.decision_time,
                bundle=reference_bundle,
            )
            record: CanonicalNode | None = None
            if resolved.binding is not None:
                binding = resolved.binding
                scheduled_departure = schedule_value[
                    "scheduled_departure_utc"
                ]
                if isinstance(scheduled_departure, str):
                    scheduled_departure = datetime.fromisoformat(
                        scheduled_departure
                    )
                sobt_minutes = (
                    scheduled_departure - node.decision_time
                ).total_seconds() / 60.0
                observed = factual_observed_state(
                    state, taxi_reference_minutes=taxi_minutes
                )
                history = encode_pre_sequence(prefix, normalization)
                record = CanonicalNode(
                    node_id=str(node.decision_node_id),
                    episode_id=str(node.episode_id),
                    chain_id=chain_id,
                    stage=str(node.operational_stage.value),
                    decision_time=node.decision_time.isoformat(),
                    sobt_minutes=float(sobt_minutes),
                    connection_airport_id=str(
                        prepared.episode.connection_airport_id
                    ),
                    destination_airport_id=str(
                        route_value["destination_airport_id"]
                    ),
                    observed=_json_safe(observed),
                    binding={
                        "turnaround_reference_minutes": float(
                            binding.turnaround_reference_minutes
                        ),
                        "taxi_reference_minutes": float(
                            binding.taxi_reference_minutes
                        ),
                        "expected_pax": float(binding.expected_pax),
                        "connection_share": float(
                            binding.connection_share
                        ),
                        "downstream_exposure": float(
                            binding.downstream_exposure
                        ),
                    },
                    history_values=tuple(
                        tuple(float(value) for value in row)
                        for row in history.tolist()
                    ),
                    pre_state=pre_environment_payload(state),
                )
            materialized.append(
                {
                    "node_id": str(node.decision_node_id),
                    "episode_id": str(node.episode_id),
                    "chain_id": chain_id,
                    "stage": str(node.operational_stage.value),
                    "decision_time": node.decision_time,
                    "record": record,
                    "abstention": (
                        None
                        if record is not None
                        else {
                            "node_id": str(node.decision_node_id),
                            "episode_id": str(node.episode_id),
                            "stage": str(node.operational_stage.value),
                            "typed_state": UNSUPPORTED_REFERENCE_STATE,
                            "status": resolved.audit.get("status"),
                            "reason_codes": list(
                                resolved.audit.get("reason_codes", ())
                            ),
                            "reference_support": dict(
                                resolved.audit.get(
                                    "reference_support", {}
                                )
                            ),
                            "zero_filled": False,
                        }
                    ),
                }
            )

    canonical_ids = set(
        _canonical_stage_identity_keys(materialized)
    )
    nodes: list[CanonicalNode] = []
    excluded: list[dict[str, Any]] = []
    rolling: list[dict[str, Any]] = []
    for entry in materialized:
        identity = (
            entry["episode_id"],
            entry["stage"],
            entry["node_id"],
        )
        selected = identity in canonical_ids
        record = entry["record"]
        rolling.append(
            {
                "schema_version": ROLLING_IDENTITY_SCHEMA,
                "node_id": entry["node_id"],
                "episode_id": entry["episode_id"],
                "chain_id": entry["chain_id"],
                "stage": entry["stage"],
                "decision_time": entry["decision_time"].isoformat(),
                "canonical_selected": bool(selected),
                "reference_support": (
                    ROLLING_REFERENCE_SUPPORTED
                    if record is not None
                    else ROLLING_REFERENCE_UNSUPPORTED
                ),
            }
        )
        if not selected:
            continue
        if record is not None:
            nodes.append(record)
        else:
            excluded.append(
                {**entry["abstention"], "canonical_decision_node": True}
            )
    return tuple(nodes), tuple(excluded), tuple(rolling)


def _canonical_stage_identity_keys(
    materialized: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, str, str], ...]:
    """Select one identity per ``(episode_id, stage)`` from raw identities.

    Only ``episode_id``, ``stage``, ``decision_time`` and ``node_id`` are read.
    """

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for entry in materialized:
        grouped.setdefault(
            (str(entry["episode_id"]), str(entry["stage"])), []
        ).append(entry)
    selected = []
    for group in grouped.values():
        winner = min(
            group,
            key=lambda item: (
                item["decision_time"],
                str(item["node_id"]),
            ),
        )
        selected.append(
            (
                str(winner["episode_id"]),
                str(winner["stage"]),
                str(winner["node_id"]),
            )
        )
    return tuple(selected)


def load_reference_payloads(
    *, reference_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the frozen M2 reference payloads and record their file hashes."""

    root = Path(reference_root)
    payloads: dict[str, Any] = {}
    records: dict[str, Any] = {}
    for name, relative in REFERENCE_PAYLOAD_FILES.items():
        path = root / relative
        _require(
            path.is_file(),
            "PHASE7_RAW_REFERENCE_PAYLOAD_MISSING",
            {"reference": name, "path": str(path)},
        )
        payloads[name] = _read_json(path)
        records[name] = {
            "path": relative,
            "resolved_path": str(path),
            "file_sha256": _file_sha256(path),
        }
    return payloads, records


def materialize_raw_source(
    profile: RawMaterializationProfile,
    *,
    source_root: Path,
    reference_root: Path,
    adapter_id: str = RAW_SOURCE_ADAPTER_ID,
    services_factory: Callable[[], FrozenScienceServices] = (
        load_frozen_services
    ),
    extra_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize the canonical nodes for one authorized raw window."""

    episode_ids = load_cohort_manifest(profile)
    episodes = reconstruct_episodes(
        profile, episode_ids, source_root=source_root
    )
    services = services_factory()
    through_turnaround = _pre_turnaround_reference()
    payloads, reference_records = load_reference_payloads(
        reference_root=reference_root
    )
    from model.M2.context import load_data2_reference_bundle

    reference_bundle = load_data2_reference_bundle(payloads)
    published, pre_audit = publish_pre_states(
        episodes,
        profile=profile,
        source_root=source_root,
        taxi_reference=services.taxi_reference,
        turnaround_reference=through_turnaround,
    )
    nodes, excluded, rolling = materialize_node_records(
        published,
        normalization=services.h16_pipeline.normalization,
        taxi_reference=services.taxi_reference,
        reference_bundle=reference_bundle,
    )
    _require(
        bool(nodes),
        "PHASE7_RAW_SOURCE_NO_CONSEQUENCE_EVALUABLE_NODES",
        {"excluded_nodes": len(excluded)},
    )
    provenance = {
        "raw_source_adapter_id": adapter_id,
        "profile": profile.as_metadata(),
        "frozen_science_services": dict(services.provenance),
        "reference_bundle_ids": dict(reference_bundle.reference_ids),
        "reference_payloads": reference_records,
        "pre_publication": pre_audit,
        "active_node_count": len(nodes) + len(excluded),
        "consequence_evaluable_node_count": len(nodes),
        "excluded_node_count": len(excluded),
        "excluded_nodes": list(excluded),
        "excluded_node_state": UNSUPPORTED_REFERENCE_STATE,
        "excluded_nodes_zero_filled": False,
        "turnaround_reference_ruling": {
            "m2_node_reference": "CORRECTED_A2_AIRPORT_CELL_MEDIAN",
            "m2_node_reference_global_fallback_minutes": 57.0,
            "m2_node_reference_scope": "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY",
            "stage2_lower_bound_minutes": C.NOMINAL_TURNAROUND_Q20,
            "stage2_lower_bound_scope": "M3_STAGE2_FEASIBILITY_ONLY",
            "merged": False,
        },
        "final_test_data_read": bool(profile.final_test_data_read),
        "q4_raw_read": bool(profile.final_test_data_read),
        "legacy_final_test_result_tree_scientific_read": False,
    }
    if extra_provenance:
        provenance.update(dict(extra_provenance))
    return canonical_nodes_payload(
        nodes,
        materialized_rolling_identities=rolling,
        scope=profile.materialization_scope,
        provenance=provenance,
    )


def production_raw_adapter(
    authorization: Mapping[str, Any],
    *,
    local_input_root: Path | None = None,
) -> dict[str, Any]:
    """The bound Gate-B raw-source adapter.

    ``authorization`` is the validated release plus open access epoch passed by
    :func:`formal.v2_phase7.executor.raw_entry.materialize_canonical_nodes`.
    The adapter itself is inert: it only resolves the declared local input
    root and then materializes the frozen profile. It never creates a release,
    never opens an epoch and never writes outside the declared output root.
    """

    _require(
        isinstance(authorization, Mapping),
        "PHASE7_RAW_ADAPTER_AUTHORIZATION_REQUIRED",
        type(authorization).__name__,
    )
    root, root_record = resolve_local_input_root(local_input_root)
    return materialize_raw_source(
        PRODUCTION_RAW_PROFILE,
        source_root=root,
        reference_root=root,
        extra_provenance={
            "authorization_id": authorization.get("authorization_id"),
            **root_record,
        },
    )


def _pre_turnaround_reference() -> Any:
    """Return the PRE-published turnaround reference used by the publisher.

    The frozen Development PRE publication consumed the v5 train-frozen
    reference; the corrected A2 node reference is bound separately by the
    frozen M2 binding (ruling R7/R8). The two references are never merged.
    """

    from model.M1.development_training import _load_references

    _taxi, turnaround, _audit = _load_references(C.ROOT)
    return turnaround


def _taxi_reference(reference: Any, airport_id: Any) -> tuple[Any, Any, Any]:
    if reference is None:
        return None, None, None
    lookup = reference.lookup(airport_id)
    value = getattr(lookup, "value", None)
    support = getattr(getattr(lookup, "support_state", None), "value", None)
    minutes = float(value) if support == "SUPPORTED" and value is not None else None
    return (
        minutes,
        getattr(reference, "reference_id", None),
        getattr(reference, "manifest_freeze_id", None),
    )


def _json_safe(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (value.isoformat() if isinstance(value, datetime) else value)
        for key, value in payload.items()
    }


__all__ = [
    "FINAL_TEST_EPISODE_COUNT",
    "LOCAL_INPUT_ROOT_ENV",
    "LOCAL_ONLY_INPUTS",
    "PRODUCTION_RAW_PROFILE",
    "PRODUCTION_RAW_PROFILE_ID",
    "RAW_SOURCE_ADAPTER_ID",
    "RawMaterializationProfile",
    "UNSUPPORTED_REFERENCE_STATE",
    "build_node_records",
    "load_cohort_manifest",
    "load_reference_payloads",
    "materialize_raw_source",
    "missing_local_inputs",
    "production_raw_adapter",
    "publish_pre_states",
    "reconstruct_episodes",
    "resolve_local_input_root",
]
