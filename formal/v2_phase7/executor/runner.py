"""Execution of the frozen nine-stage Phase-7 DAG.

The runner walks :data:`formal.v2_phase7.executor.stages.SCIENCE_DAG_STAGES` in
order. Each stage writes exactly one immutable checkpoint; every stage consumes
only hash-validated upstream checkpoints, so a downstream stage can never read a
partially recomputed upstream payload.

Resume is dependency-exact: a stage is reused only when its recorded upstream
payload hashes still match. Frozen M1/M2 services are loaded lazily, so a fully
reused DAG (or a single downstream rebuild) never touches the model services.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..errors import TypedBlocker, _require
from . import stages as S
from .attention_decisions import build_attention_decisions
from .bootstrap import build_bootstrap
from .checkpoints import CheckpointRecord, CheckpointStore, content_hash
from .consequence_variants import build_consequence_variants
from .fixtures import fixture_checkpoint_payload
from .m4_comparisons import build_m4_comparisons
from .nodes import nodes_from_payload
from .paper_views import build_paper_views
from .recovery_decisions import build_recovery_decisions
from .reference_cohort import build_reference_recovery_cohort
from .services import FrozenScienceServices, load_frozen_services
from .state_variants import build_state_variants

RUN_SCHEMA_VERSION = "AIR_SLOT_V2_PHASE7_EXECUTOR_RUN_V1"
FIXTURE_PRODUCER = "PHASE7_GATE_B0_DEVELOPMENT_SAFE_FIXTURE"
PRODUCTION_PRODUCER = "PHASE7_GATE_B_SEALED_RUN"


@dataclass(frozen=True)
class ExecutorRun:
    """One DAG execution: validated stage records, payloads and manifest."""

    records: Mapping[str, CheckpointRecord]
    payloads: Mapping[str, Any]
    manifest: Mapping[str, Any]

    def record(self, stage: str) -> CheckpointRecord:
        return self.records[stage]

    def payload(self, stage: str) -> Mapping[str, Any]:
        return self.payloads[stage]


class _ServicesHolder:
    """Lazy, single-load holder for the frozen M1/M2 service handles."""

    def __init__(self, factory: Callable[[], FrozenScienceServices]) -> None:
        self._factory = factory
        self._services: FrozenScienceServices | None = None
        self.loaded = False

    def get(self) -> FrozenScienceServices:
        if self._services is None:
            self._services = self._factory()
            self.loaded = True
        return self._services


def assert_dag_order() -> None:
    """Fail closed if the declared DAG order is not a topological order."""

    seen: set[str] = set()
    for stage in S.SCIENCE_DAG_STAGES:
        missing = [
            dependency
            for dependency in S.STAGE_DEPENDENCIES[stage]
            if dependency not in seen
        ]
        _require(
            not missing,
            "PHASE7_DAG_ORDER_NOT_TOPOLOGICAL",
            {"stage": stage, "missing": missing},
        )
        seen.add(stage)
    _require(
        set(seen) == set(S.STAGE_DEPENDENCIES),
        "PHASE7_DAG_STAGE_SET_MISMATCH",
        sorted(set(S.STAGE_DEPENDENCIES) - seen),
    )


def run_executor(
    *,
    store: CheckpointStore,
    canonical_nodes: Mapping[str, Any] | None = None,
    services_factory: Callable[[], FrozenScienceServices] = load_frozen_services,
    produced_by: str,
    resume: bool = True,
    scope: str,
) -> ExecutorRun:
    """Run (or resume) the frozen DAG inside ``store``."""

    assert_dag_order()
    holder = _ServicesHolder(services_factory)
    records: dict[str, CheckpointRecord] = {}
    payloads: dict[str, Any] = {}
    reused: list[str] = []
    computed: list[str] = []

    for stage in S.SCIENCE_DAG_STAGES:
        dependencies = {
            name: records[name] for name in S.STAGE_DEPENDENCIES[stage]
        }
        if stage == S.CANONICAL_NODES:
            record, payload, was_reused = _canonical_nodes_stage(
                store,
                canonical_nodes=canonical_nodes,
                resume=resume,
                produced_by=produced_by,
            )
        elif resume and store.is_reusable(stage, dependencies):
            record = store.record(stage, reused=True)
            payload = store.read(stage)
            was_reused = True
        else:
            inputs = {name: store.read(name) for name in dependencies}
            payload = _compute_stage(stage, inputs, holder)
            record = store.write(
                stage,
                payload,
                dependencies=dependencies,
                produced_by=produced_by,
            )
            # Read the canonical body back so the in-memory run always exposes
            # exactly the schema-tagged payload that downstream stages consume.
            payload = store.read(stage)
            was_reused = False
        records[stage] = record
        payloads[stage] = payload
        (reused if was_reused else computed).append(stage)

    manifest = _manifest(
        records=records,
        reused=reused,
        computed=computed,
        produced_by=produced_by,
        scope=scope,
        services_loaded=holder.loaded,
    )
    return ExecutorRun(records=records, payloads=payloads, manifest=manifest)


def run_development_safe_dag(
    *,
    output_root: Path,
    node_limit: int = 16,
    resume: bool = True,
    services_factory: Callable[[], FrozenScienceServices] = load_frozen_services,
) -> ExecutorRun:
    """Run the whole DAG on the Development-safe fixture."""

    store = CheckpointStore(output_root, namespace="development_safe_fixture")
    payload = fixture_checkpoint_payload(node_limit=node_limit)
    return run_executor(
        store=store,
        canonical_nodes=payload,
        services_factory=services_factory,
        produced_by=FIXTURE_PRODUCER,
        resume=resume,
        scope=str(payload["materialization_scope"]),
    )


def run_materialized_dag(
    *,
    output_root: Path,
    canonical_nodes: Mapping[str, Any],
    resume: bool = True,
    services_factory: Callable[[], FrozenScienceServices] = load_frozen_services,
    produced_by: str = PRODUCTION_PRODUCER,
) -> ExecutorRun:
    """Run the DAG from an externally materialized ``CANONICAL_NODES`` payload."""

    scope = str(canonical_nodes.get("materialization_scope", ""))
    _require(bool(scope), "PHASE7_CANONICAL_NODES_SCOPE_MISSING")
    store = CheckpointStore(output_root, namespace="materialized")
    return run_executor(
        store=store,
        canonical_nodes=canonical_nodes,
        services_factory=services_factory,
        produced_by=produced_by,
        resume=resume,
        scope=scope,
    )


def _canonical_nodes_stage(
    store: CheckpointStore,
    *,
    canonical_nodes: Mapping[str, Any] | None,
    resume: bool,
    produced_by: str,
) -> tuple[CheckpointRecord, dict[str, Any], bool]:
    if canonical_nodes is None:
        if store.has(S.CANONICAL_NODES):
            return store.record(S.CANONICAL_NODES, reused=True), store.read(
                S.CANONICAL_NODES
            ), True
        raise TypedBlocker(
            "PHASE7_CANONICAL_NODES_NOT_MATERIALIZED",
            "no materialized CANONICAL_NODES checkpoint or payload was supplied",
        )
    body = dict(canonical_nodes)
    expected = content_hash({**body, "schema_version": S.schema_version(S.CANONICAL_NODES), "stage": S.CANONICAL_NODES})
    if store.has(S.CANONICAL_NODES):
        stored = store.record(S.CANONICAL_NODES, reused=True)
        if stored.payload_hash != expected and resume:
            raise TypedBlocker(
                "PHASE7_CANONICAL_NODES_MISMATCH_WITH_CHECKPOINT",
                {"stored": stored.payload_hash, "supplied": expected},
            )
        if resume:
            return stored, store.read(S.CANONICAL_NODES), True
    payload = {
        key: value
        for key, value in body.items()
        if key not in {"schema_version", "stage"}
    }
    record = store.write(
        S.CANONICAL_NODES,
        payload,
        dependencies={},
        produced_by=produced_by,
    )
    return record, store.read(S.CANONICAL_NODES), False


def _compute_stage(
    stage: str, inputs: Mapping[str, Any], holder: _ServicesHolder
) -> dict[str, Any]:
    if stage == S.STATE_VARIANTS:
        return build_state_variants(
            nodes_from_payload(inputs[S.CANONICAL_NODES]),
            services=holder.get(),
        )
    if stage == S.CONSEQUENCE_VARIANTS:
        return build_consequence_variants(
            nodes_from_payload(inputs[S.CANONICAL_NODES]),
            state_variants=inputs[S.STATE_VARIANTS],
            services=holder.get(),
        )
    if stage == S.ATTENTION_DECISIONS:
        node_ids = [
            str(node["node_id"])
            for node in inputs[S.CONSEQUENCE_VARIANTS]["rows"]
        ]
        return build_attention_decisions(
            tuple(sorted(set(node_ids))),
            consequence_variants=inputs[S.CONSEQUENCE_VARIANTS],
        )
    if stage == S.REFERENCE_RECOVERY_COHORT:
        return build_reference_recovery_cohort(
            inputs[S.CANONICAL_NODES],
            inputs[S.STATE_VARIANTS],
            inputs[S.ATTENTION_DECISIONS],
        )
    if stage == S.RECOVERY_DECISIONS:
        return build_recovery_decisions(
            inputs[S.CANONICAL_NODES],
            inputs[S.STATE_VARIANTS],
            inputs[S.REFERENCE_RECOVERY_COHORT],
            services=holder.get(),
        )
    if stage == S.M4_COMPARISONS:
        return build_m4_comparisons(
            inputs[S.CONSEQUENCE_VARIANTS],
            inputs[S.ATTENTION_DECISIONS],
            inputs[S.REFERENCE_RECOVERY_COHORT],
            inputs[S.RECOVERY_DECISIONS],
        )
    if stage == S.BOOTSTRAP:
        return build_bootstrap(inputs[S.M4_COMPARISONS])
    if stage == S.PAPER_VIEWS:
        return build_paper_views(
            inputs[S.ATTENTION_DECISIONS],
            inputs[S.M4_COMPARISONS],
            inputs[S.BOOTSTRAP],
        )
    raise TypedBlocker("PHASE7_DAG_STAGE_NOT_IMPLEMENTED", stage)


def _manifest(
    *,
    records: Mapping[str, CheckpointRecord],
    reused: list[str],
    computed: list[str],
    produced_by: str,
    scope: str,
    services_loaded: bool,
) -> dict[str, Any]:
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "produced_by": produced_by,
        "materialization_scope": scope,
        "dag_stages": list(S.SCIENCE_DAG_STAGES),
        "stage_dependencies": {
            stage: list(S.STAGE_DEPENDENCIES[stage]) for stage in S.SCIENCE_DAG_STAGES
        },
        "stage_records": {
            stage: records[stage].as_dict() for stage in S.SCIENCE_DAG_STAGES
        },
        "reused_stages": list(reused),
        "computed_stages": list(computed),
        "frozen_services_loaded": bool(services_loaded),
        "fixed_window_sensitivity_status": S.FIXED_WINDOW_SENSITIVITY_STATUS,
        "access_boundary": {
            "q4_raw_read": False,
            "legacy_final_test_result_tree_scientific_read_by_fixture": False,
            "legacy_final_test_result_tree_incidental_repository_audit_reads": 1,
            "legacy_final_test_result_tree_reads_used_for_scientific_computation": False,
            "legacy_final_test_result_tree_reads_used_for_selection": False,
            "phase7_scientific_access_increment": 0,
            "human_release_created": False,
            "phase7_access_epoch_opened": False,
            "historical_final_test_access_total": 1,
            "current_freeze_run_increment": 0,
        },
        "immutable_checkpoint_consumption": True,
        "atomic_results_before_views": True,
    }


__all__ = [
    "ExecutorRun",
    "FIXTURE_PRODUCER",
    "PRODUCTION_PRODUCER",
    "RUN_SCHEMA_VERSION",
    "assert_dag_order",
    "run_development_safe_dag",
    "run_executor",
    "run_materialized_dag",
]
