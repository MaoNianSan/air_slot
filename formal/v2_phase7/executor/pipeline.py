"""The bound Phase-7 scientific pipeline behind the Gate-B callback boundary.

``execute_gate_b`` validates the human release, opens the single access epoch and
then calls exactly one pipeline callback. This module is the body of that
callback for the real frozen executor:

1. materialize ``CANONICAL_NODES`` through the one-shot authorized raw entry,
2. run the frozen nine-stage DAG from that immutable checkpoint, and
3. return the run manifest with the persisted atomic results.

The pipeline never creates the release, never opens the epoch and never reads
raw data by itself - those transitions belong to the caller. With no activated
raw adapter it fails closed with ``PHASE7_FINAL_TEST_RAW_ADAPTER_NOT_ACTIVATED``;
the production callback binds :func:`.raw_source.production_raw_adapter`,
which materializes only after the authorized raw entry accepts the release.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .. import constants as C
from ..errors import TypedBlocker, _require
from . import stages as S
from .raw_entry import materialize_canonical_nodes
from .runner import FIXTURE_PRODUCER, PRODUCTION_PRODUCER, run_materialized_dag
from .services import FrozenScienceServices, load_frozen_services

PIPELINE_SCHEMA_VERSION = "AIR_SLOT_V2_PHASE7_SEALED_PIPELINE_V1"
CHECKPOINT_ROOT_NAME = "checkpoints"


def run_sealed_pipeline(
    context: Mapping[str, Any],
    *,
    output_root: Path | None = None,
    adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    services_factory: Callable[[], FrozenScienceServices] = load_frozen_services,
    resume: bool = True,
) -> dict[str, Any]:
    """Materialize once, then run the frozen DAG from the checkpoint."""

    _require(
        isinstance(context, Mapping),
        "PHASE7_SEALED_PIPELINE_CONTEXT_REQUIRED",
    )
    release = context.get("release")
    epoch = context.get("access_epoch")
    _require(
        isinstance(release, Mapping) and isinstance(epoch, Mapping),
        "PHASE7_SEALED_PIPELINE_RELEASE_OR_EPOCH_MISSING",
    )
    root = (
        Path(output_root)
        if output_root is not None
        else C.stage_matched_epoch_paths().root
    )
    canonical_nodes = materialize_canonical_nodes(
        authorization={
            "authorization_id": "GATE_B_HUMAN_RELEASE",
            "release": release,
            "access_epoch": epoch,
        },
        output_root=root,
        adapter=adapter,
    )
    run = run_materialized_dag(
        output_root=root / CHECKPOINT_ROOT_NAME,
        canonical_nodes=canonical_nodes,
        resume=resume,
        services_factory=services_factory,
        produced_by=PRODUCTION_PRODUCER,
    )
    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "status": "PASS",
        "produced_by": PRODUCTION_PRODUCER,
        "materialization_scope": str(canonical_nodes["materialization_scope"]),
        "dag_stages": list(S.SCIENCE_DAG_STAGES),
        "stage_records": {
            stage: run.record(stage).as_dict() for stage in S.SCIENCE_DAG_STAGES
        },
        "manifest": dict(run.manifest),
        "paper_views_status": "PERSISTED_AS_IMMUTABLE_CHECKPOINT",
    }


__all__ = [
    "CHECKPOINT_ROOT_NAME",
    "FIXTURE_PRODUCER",
    "PIPELINE_SCHEMA_VERSION",
    "PRODUCTION_PRODUCER",
    "TypedBlocker",
    "run_sealed_pipeline",
]
