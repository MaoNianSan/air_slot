"""Frozen M1/M2 scientific service handles for the Phase-7 DAG.

Every handle is loaded from a frozen artifact and hash-validated before use.
The executor never re-implements an M1 sampling rule, an M2 consequence
formula, an M3 selection/solve rule or an M4 evaluation rule: it calls the
frozen services with the frozen inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from model.common.decision_contracts import HeadroomSummary

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..materialization import _file_sha256, _read_json

H16_ROOT = C.ROOT / "artifacts" / "models" / "m1" / "M1_H16_HISTORY_PRIMARY"
H16_CHECKPOINT = H16_ROOT / "M1_H16_HISTORY_PRIMARY.pt"
H16_MANIFEST = H16_ROOT / "M1_H16_HISTORY_PRIMARY_MANIFEST.json"
CURRENT_ROOT = C.ROOT / "artifacts" / "models" / "m1" / "M1_H16_CURRENT_COMPARATOR"
CURRENT_CHECKPOINT = CURRENT_ROOT / "M1_H16_CURRENT_COMPARATOR.pt"
CURRENT_MANIFEST = CURRENT_ROOT / "M1_H16_CURRENT_COMPARATOR_MANIFEST.json"
TAIL_MANIFEST_PATH = (
    C.ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_positive_tail_continuation_v1"
    / "M1_POSITIVE_TAIL_CONTINUATION_V1.json"
)
M2_REGISTRY_PATH = C.ROOT / "registries" / "m2_data2_formal_cu_v5.json"

H16_HISTORY_MODE = "FULL_ADAPTIVE_CAUSAL_PREFIX"
CURRENT_HISTORY_MODE = "NO_HISTORY_CURRENT_OBSERVATION"
M2_REGISTRY_ID = "M2_DATA2_FORMAL_CU_V5"


@dataclass(frozen=True)
class FrozenScienceServices:
    """Loaded frozen services plus their provenance record."""

    h16_pipeline: Any
    current_pipeline: Any
    tail_continuations: Any
    registry: Any
    headroom_summary: HeadroomSummary
    taxi_reference: Any
    scenario_seed: int
    scenario_count: int
    provenance: Mapping[str, Any]

    def consequence_service(self, bindings: Mapping[str, Any]):
        from model.M2.consequence_service import M2ConsequenceService

        return M2ConsequenceService(self.registry, dict(bindings))


def load_frozen_services() -> FrozenScienceServices:
    """Load and validate the frozen M1/M2 services used by every DAG stage."""

    from model.M1.pipeline import M1Pipeline
    from model.M1.tail import load_tail_continuations
    from model.M2.scientific_registry import load_active_v2_cu_registry

    for path in (
        H16_CHECKPOINT,
        H16_MANIFEST,
        CURRENT_CHECKPOINT,
        CURRENT_MANIFEST,
        TAIL_MANIFEST_PATH,
        M2_REGISTRY_PATH,
        C.TRAIN_SUPPORT_SUMMARY_PATH,
    ):
        if not Path(path).is_file():
            raise TypedBlocker("PHASE7_FROZEN_SERVICE_INPUT_MISSING", str(path))

    h16_manifest = _read_json(H16_MANIFEST)
    current_manifest = _read_json(CURRENT_MANIFEST)
    _require(
        h16_manifest.get("history_mode") == H16_HISTORY_MODE,
        "PHASE7_H16_HISTORY_MODE_MISMATCH",
        h16_manifest.get("history_mode"),
    )
    _require(
        current_manifest.get("history_mode") == CURRENT_HISTORY_MODE,
        "PHASE7_CURRENT_HISTORY_MODE_MISMATCH",
        current_manifest.get("history_mode"),
    )
    _require(
        _file_sha256(H16_CHECKPOINT) == h16_manifest.get("checkpoint_hash"),
        "PHASE7_H16_CHECKPOINT_HASH_MISMATCH",
    )
    _require(
        _file_sha256(CURRENT_CHECKPOINT) == current_manifest.get("checkpoint_hash"),
        "PHASE7_CURRENT_CHECKPOINT_HASH_MISMATCH",
    )
    for label, payload in (
        ("h16_manifest", h16_manifest),
        ("current_manifest", current_manifest),
    ):
        _require(
            int(payload.get("final_test_access_count", -1)) == 0,
            "PHASE7_FROZEN_SERVICE_FINAL_TEST_ACCESS_VIOLATION",
            label,
        )
    scenario_count = int(h16_manifest.get("scenario_count", -1))
    _require(
        scenario_count == 64,
        "PHASE7_SCENARIO_COUNT_MISMATCH",
        scenario_count,
    )

    registry = load_active_v2_cu_registry(M2_REGISTRY_PATH)
    _require(
        int(getattr(registry, "final_test_access_count", -1)) == 0,
        "PHASE7_REGISTRY_FINAL_TEST_ACCESS_VIOLATION",
    )
    _require(
        str(getattr(registry, "registry_id", "")) == M2_REGISTRY_ID,
        "PHASE7_REGISTRY_ID_MISMATCH",
        getattr(registry, "registry_id", None),
    )

    tail_manifest = _read_json(TAIL_MANIFEST_PATH)
    tail_continuations = load_tail_continuations(TAIL_MANIFEST_PATH)

    train_support = _read_json(C.TRAIN_SUPPORT_SUMMARY_PATH)
    _require(
        train_support.get("status") == "PASS",
        "PHASE7_TRAIN_SUPPORT_STATUS_INVALID",
        train_support.get("status"),
    )
    _require(
        int(train_support.get("final_test_access_count", -1)) == 0,
        "PHASE7_TRAIN_SUPPORT_FINAL_TEST_ACCESS_VIOLATION",
    )
    headroom_block = train_support["factual_headroom"]["headroom_summary"]
    u_max_block = train_support["u_max"]
    turnaround_block = train_support["stage2_turnaround_lower_bound"]
    headroom_summary = HeadroomSummary(
        u_max=float(u_max_block["nominal_minutes"]),
        turnaround_lower_bound_q=float(turnaround_block["value_minutes"]),
        turnaround_quantile=float(train_support["turnaround"]["nominal_quantile"]),
        headroom_quantile=float(headroom_block["headroom_quantile"]),
        headroom_positive_n=int(headroom_block["headroom_positive_n"]),
        source_id=str(headroom_block["source_id"]),
        floor_to_minutes=float(u_max_block["floor_to_minutes"]),
    )
    _require(
        headroom_summary.u_max == C.NOMINAL_U_MAX
        and headroom_summary.turnaround_lower_bound_q == C.NOMINAL_TURNAROUND_Q20,
        "PHASE7_NOMINAL_STAGE2_SUPPORT_MISMATCH",
        {
            "u_max": headroom_summary.u_max,
            "turnaround_lower_bound_q": headroom_summary.turnaround_lower_bound_q,
        },
    )

    h16_pipeline = M1Pipeline.load(H16_CHECKPOINT)
    current_pipeline = M1Pipeline.load(CURRENT_CHECKPOINT)
    from model.M1.development_training import _load_references

    taxi_reference, _, reference_audit = _load_references(C.ROOT)
    h16_pipeline.tail_continuations = tail_continuations
    current_pipeline.tail_continuations = tail_continuations

    provenance = {
        "h16_manifest_path": str(H16_MANIFEST.relative_to(C.ROOT)),
        "h16_manifest_hash": _file_sha256(H16_MANIFEST),
        "h16_checkpoint_hash": h16_manifest.get("checkpoint_hash"),
        "h16_model_id": h16_manifest.get("model_id"),
        "h16_training_seed": h16_manifest.get("training_seed"),
        "current_manifest_path": str(CURRENT_MANIFEST.relative_to(C.ROOT)),
        "current_manifest_hash": _file_sha256(CURRENT_MANIFEST),
        "current_checkpoint_hash": current_manifest.get("checkpoint_hash"),
        "current_model_id": current_manifest.get("model_id"),
        "tail_manifest_path": str(TAIL_MANIFEST_PATH.relative_to(C.ROOT)),
        "tail_manifest_hash": _file_sha256(TAIL_MANIFEST_PATH),
        "tail_manifest_artifact_hash": tail_manifest.get("artifact_hash"),
        "taxi_reference_id": reference_audit.get("taxi_reference_id"),
        "taxi_reference_hash": reference_audit.get("taxi_reference_hash"),
        "taxi_reference_artifact_hash": reference_audit.get(
            "taxi_artifact_hash"
        ),
        "m2_registry_path": str(M2_REGISTRY_PATH.relative_to(C.ROOT)),
        "m2_registry_id": str(getattr(registry, "registry_id", "")),
        "m2_registry_hash": str(getattr(registry, "registry_hash", "")),
        "m2_registry_file_hash": _file_sha256(M2_REGISTRY_PATH),
        "train_support_summary_path": str(
            C.TRAIN_SUPPORT_SUMMARY_PATH.relative_to(C.ROOT)
        ),
        "train_support_summary_file_hash": _file_sha256(C.TRAIN_SUPPORT_SUMMARY_PATH),
        "train_support_artifact_hash": train_support.get("artifact_hash"),
        "scenario_count": scenario_count,
        "scenario_generator_seed": int(h16_manifest.get("training_seed", -1)),
        "headroom_summary": {
            "u_max": headroom_summary.u_max,
            "turnaround_lower_bound_q": headroom_summary.turnaround_lower_bound_q,
            "source_id": headroom_summary.source_id,
        },
        "final_test_access_count": 0,
    }
    return FrozenScienceServices(
        h16_pipeline=h16_pipeline,
        current_pipeline=current_pipeline,
        tail_continuations=tail_continuations,
        registry=registry,
        headroom_summary=headroom_summary,
        taxi_reference=taxi_reference,
        scenario_seed=int(h16_manifest.get("training_seed", -1)),
        scenario_count=scenario_count,
        provenance=provenance,
    )


def binding_from_node(node: Any):
    """Build the frozen M2 reference binding for one canonical node."""

    from model.M2.consequence_service import ConsequenceReferenceBinding

    binding = dict(node.binding)
    return ConsequenceReferenceBinding(
        reference_id=node.node_id,
        turnaround_reference_minutes=float(binding["turnaround_reference_minutes"]),
        taxi_reference_minutes=float(binding.get("taxi_reference_minutes", 0.0)),
        expected_pax=float(binding["expected_pax"]),
        connection_share=float(binding["connection_share"]),
        downstream_exposure=float(binding["downstream_exposure"]),
    )


__all__ = [
    "CURRENT_CHECKPOINT",
    "CURRENT_MANIFEST",
    "FrozenScienceServices",
    "H16_CHECKPOINT",
    "H16_MANIFEST",
    "M2_REGISTRY_PATH",
    "TAIL_MANIFEST_PATH",
    "binding_from_node",
    "load_frozen_services",
]
