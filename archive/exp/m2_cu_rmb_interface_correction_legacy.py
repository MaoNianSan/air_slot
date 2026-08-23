"""Materialize the corrected C -> CU -> RMB interface binding."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id

SOURCE = Path("artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json")
SOURCE_ARTIFACT = Path("artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCES.json")
DESIGN = Path("registries/m4_cu_rmb_mapping_design_v2.json")
SAFETY = {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "EXP2_RUNS": 0, "EXP3_RUNS": 0, "EXP4_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "FULL": False, "PAPER_FULL_RUN": False}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M2_CU_RMB_CORRECTION_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m2_cu_rmb_interface_correction_v2").resolve()
    source_path, source_artifact_path, design_path = root / SOURCE, root / SOURCE_ARTIFACT, root / DESIGN
    if not all(path.is_file() for path in (source_path, source_artifact_path, design_path)):
        raise RuntimeError("M2_CU_RMB_CORRECTION_INPUT_MISSING")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_artifact = json.loads(source_artifact_path.read_text(encoding="utf-8"))
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if source["status"] != "M2_V2_CONSEQUENCE_ARTIFACT_MATERIALIZED":
        raise RuntimeError("M2_CU_RMB_CORRECTION_SOURCE_STATUS_INVALID")
    if tuple(source_artifact["component_order"]) != CONSEQUENCE_COMPONENTS:
        raise RuntimeError("M2_CU_RMB_CORRECTION_COMPONENT_ORDER_INVALID")
    payload = {
        "schema_version": "M2_CU_RMB_INTERFACE_ARTIFACT_V2",
        "status": "M2_C_TO_CU_INTERFACE_BOUND",
        "component_order": list(CONSEQUENCE_COMPONENTS),
        "m2_output_contract": {
            "input_object": "C",
            "intermediate_object": "CU",
            "mapping": "CU_k = g_k(C_k)",
            "component_source_field": "native_quantity",
            "constructed_value_field": "constructed_value_cu",
            "cu_status_field": "cu_status",
            "cu_lineage_field": "cu_artifact_id",
            "channels": {"Flight": ["F_continuity", "F_execution", "F_propagation"], "Passenger": ["P_time", "P_itinerary", "P_service"], "Resource": ["R_operating"]},
            "no_zero_fill": True,
            "abstain_preserved": True,
        },
        "rmb_mapping_contract": {
            "input_object": "CU",
            "output_object": "RMB",
            "formula": "RMB_k = f_k(CU_k)",
            "aggregation": "RMB = SUM_k RMB_k",
            "mapping_status": "NOT_FROZEN",
            "scenario_dependent": True,
            "real_currency_claim": False,
            "monetary_ground_truth_claim": False,
        },
        "action_chain": "A -> C^a -> CU^a -> RMB^a -> risk",
        "previous_v1_status": "SUPERSEDED_BY_CU_RMB_CORRECTION",
        "inputs": {"m2_manifest": {"path": SOURCE.as_posix(), "sha256": _hash(source_path)}, "m2_artifact": {"path": SOURCE_ARTIFACT.as_posix(), "sha256": _hash(source_artifact_path)}, "cu_rmb_design": {"path": DESIGN.as_posix(), "sha256": _hash(design_path)}},
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M2_CU_RMB_INTERFACE.json"
    _write(artifact_path, payload)
    manifest = {"schema_version": "M2_CU_RMB_INTERFACE_MANIFEST_V2", "status": payload["status"], "artifact": str(artifact_path.resolve()), "artifact_hash": payload["artifact_hash"], "component_count": 7, "mapping_status": "NOT_FROZEN", "action_chain": payload["action_chain"], "safety": dict(SAFETY)}
    manifest_path = output_root / "M2_CU_RMB_INTERFACE_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("M2_C_TO_CU_TO_RMB_INTERFACE_BOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
