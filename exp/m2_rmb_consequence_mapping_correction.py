"""Bind the corrected M2 consequence -> RMB interface without rewriting data.

The existing seven-component artifact is preserved as historical provenance.
This manifest declares that M2 emits C_k component values and that any RMB
conversion is downstream, component-wise, scenario-dependent, and currently
unfrozen.
"""

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
DESIGN = Path("registries/m4_rmb_mapping_design_v1.json")
SAFETY = {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "EXP2_RUNS": 0, "EXP3_RUNS": 0, "EXP4_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "FULL": False, "PAPER_FULL_RUN": False}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M2_RMB_CORRECTION_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m2_rmb_consequence_mapping_correction_v1").resolve()
    source_path, source_artifact_path, design_path = root / SOURCE, root / SOURCE_ARTIFACT, root / DESIGN
    if not all(path.is_file() for path in (source_path, source_artifact_path, design_path)):
        raise RuntimeError("M2_RMB_CORRECTION_INPUT_MISSING")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_artifact = json.loads(source_artifact_path.read_text(encoding="utf-8"))
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if source["status"] != "M2_V2_CONSEQUENCE_ARTIFACT_MATERIALIZED":
        raise RuntimeError("M2_RMB_CORRECTION_SOURCE_STATUS_INVALID")
    if tuple(source_artifact["component_order"]) != CONSEQUENCE_COMPONENTS:
        raise RuntimeError("M2_RMB_CORRECTION_COMPONENT_ORDER_INVALID")
    payload = {
        "schema_version": "M2_RMB_CONSEQUENCE_INTERFACE_ARTIFACT_V1",
        "status": "M2_CONSEQUENCE_TO_RMB_INTERFACE_MATERIALIZED",
        "source_m2_artifact_status": source["status"],
        "component_order": list(CONSEQUENCE_COMPONENTS),
        "m2_output_contract": {
            "object": "C",
            "components": list(CONSEQUENCE_COMPONENTS),
            "source_field": "native_quantity",
            "support_field": "support_state",
            "lineage_fields": ["native_artifact_id", "reference_lineage"],
            "channels": {"Flight": ["F_continuity", "F_execution", "F_propagation"], "Passenger": ["P_time", "P_itinerary", "P_service"], "Resource": ["R_operating"]},
            "no_zero_fill": True,
            "abstain_preserved": True,
        },
        "monetary_mapping_contract": {
            "formula": "RMB_k = f_k(C_k)",
            "aggregation": "RMB = SUM_k RMB_k",
            "constructed_unit_id": "RMB",
            "mapping_status": "NOT_FROZEN",
            "scenario_dependent": True,
            "real_currency_claim": False,
            "monetary_ground_truth_claim": False,
        },
        "action_chain": "A -> C^a -> RMB^a -> risk",
        "legacy_cu_boundary": {"status": "HISTORICAL_COMPATIBILITY_ONLY", "monetary_interface": False, "source_artifact_preserved": True},
        "inputs": {"m2_manifest": {"path": SOURCE.as_posix(), "sha256": _hash(source_path)}, "m2_artifact": {"path": SOURCE_ARTIFACT.as_posix(), "sha256": _hash(source_artifact_path)}, "rmb_design": {"path": DESIGN.as_posix(), "sha256": _hash(design_path)}},
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M2_RMB_CONSEQUENCE_INTERFACE.json"
    _write(artifact_path, payload)
    manifest = {"schema_version": "M2_RMB_CONSEQUENCE_INTERFACE_MANIFEST_V1", "status": payload["status"], "artifact": str(artifact_path.resolve()), "artifact_hash": payload["artifact_hash"], "component_count": 7, "mapping_status": "NOT_FROZEN", "safety": dict(SAFETY)}
    manifest_path = output_root / "M2_RMB_CONSEQUENCE_INTERFACE_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("M2_CONSEQUENCE_TO_RMB_INTERFACE_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
