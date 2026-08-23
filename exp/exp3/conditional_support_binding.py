"""Bind accepted conditional M3 support into the Exp3 Development lane."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.common.identity import content_id

CONDITIONAL = Path("artifacts/diagnostics/m3_conditional_action_support_v1/M3_CONDITIONAL_ACTION_SUPPORT.json")
EXP3 = Path("artifacts/diagnostics/exp3_formal_execution_preparation_v10/EXP3_FORMAL_EXECUTION_MANIFEST.json")
LIBRARY = Path("artifacts/diagnostics/m3_action_library_scientific_materialization_v2/M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION.json")
RESPONSE = Path("registries/m3_v2_action_response_design.json")
M2 = Path("artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json")
RMB_INTERFACE = Path("artifacts/diagnostics/m2_cu_rmb_interface_correction_v2/M2_CU_RMB_INTERFACE.json")
SAFETY = {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "EXP2_RUNS": 0, "EXP3_RUNS": 0, "EXP4_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "FULL": False, "PAPER_FULL_RUN": False}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M3_CONDITIONAL_BINDING_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def bind(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/exp3_conditional_support_binding_v4").resolve()
    paths = {"conditional_support": root / CONDITIONAL, "exp3_manifest": root / EXP3, "action_library": root / LIBRARY, "response_registry": root / RESPONSE, "m2_manifest": root / M2, "rmb_interface": root / RMB_INTERFACE}
    if not all(path.is_file() for path in paths.values()):
        raise RuntimeError("M3_CONDITIONAL_BINDING_INPUT_MISSING")
    conditional = json.loads(paths["conditional_support"].read_text(encoding="utf-8"))
    exp3 = json.loads(paths["exp3_manifest"].read_text(encoding="utf-8"))
    library = json.loads(paths["action_library"].read_text(encoding="utf-8"))
    rmb_interface = json.loads(paths["rmb_interface"].read_text(encoding="utf-8"))
    if conditional["status"] != "M3_CONDITIONAL_HYBRID_SUPPORT_MATERIALIZED" or conditional["conditional_action_count"] != 22:
        raise RuntimeError("M3_CONDITIONAL_BINDING_SUPPORT_NOT_READY")
    if exp3["status"] != "EXP3_FORMAL_EXECUTION_READY":
        raise RuntimeError("M3_CONDITIONAL_BINDING_EXP3_NOT_READY")
    if library["action_count"] != 23 or library["formal_support_upgrade"]:
        raise RuntimeError("M3_CONDITIONAL_BINDING_LIBRARY_INVALID")
    if rmb_interface["status"] != "M2_C_TO_CU_INTERFACE_BOUND":
        raise RuntimeError("M3_CONDITIONAL_BINDING_RMB_INTERFACE_INVALID")
    if rmb_interface["rmb_mapping_contract"]["formula"] != "RMB_k = f_k(CU_k)":
        raise RuntimeError("M3_CONDITIONAL_BINDING_RMB_FORMULA_INVALID")
    payload = {
        "schema_version": "EXP3_CONDITIONAL_SUPPORT_BINDING_V2",
        "status": "EXP3_CONDITIONAL_SCENARIO_LANE_BOUND",
        "conditional_support_artifact_hash": conditional["artifact_hash"],
        "conditional_action_count": conditional["conditional_action_count"],
        "interpretation_scope": "SCENARIO_CONDITIONED_NON_AUTHORITATIVE",
        "formal_multi_action_status": "BLOCKED_UNCHANGED",
        "authoritative_ranking_allowed": False,
        "causal_effect_claim_allowed": False,
        "monetary_chain": "C^a -> CU^a -> RMB^a -> risk",
        "rmb_interface_artifact_hash": rmb_interface["artifact_hash"],
        "bindings": {name: {"path": path.as_posix(), "sha256": _hash(path)} for name, path in paths.items()},
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "EXP3_CONDITIONAL_SUPPORT_BINDING.json"
    _write(artifact_path, payload)
    manifest = {"schema_version": "EXP3_CONDITIONAL_SUPPORT_BINDING_MANIFEST_V2", "status": payload["status"], "artifact": str(artifact_path.resolve()), "artifact_hash": payload["artifact_hash"], "conditional_action_count": 22, "formal_multi_action_status": "BLOCKED_UNCHANGED", "monetary_chain": "C^a -> CU^a -> RMB^a -> risk", "safety": dict(SAFETY)}
    manifest_path = output_root / "EXP3_CONDITIONAL_SUPPORT_BINDING_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    bind(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP3_CONDITIONAL_SCENARIO_LANE_BOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
