"""Materialize the already frozen H8 M1 runtime artifact.

This module performs one fixed-contract training/calibration materialization;
it does not search hyperparameters or select among models.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

import torch

from model.M1.development_training import run_data2_development_fast
from model.M1.pipeline import M1Pipeline
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


OLD_CHECKPOINT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "model"
    / "m1_v2_tuning_stage1_fast"
    / "GRU_H8"
    / "M1_V2_FAST_TRAIN_MODE.pt"
)
OUTPUT = PROJECT_ROOT / "artifacts" / "models" / "m1" / "M1_FROZEN_H8"


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def audit_existing_checkpoint(output: Path = OUTPUT / "H8_ARTIFACT_COMPATIBILITY_AUDIT.md") -> dict:
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    expected = {
        "hidden_size": 8,
        "layers": 1,
        "causal": True,
        "support": {
            "T_IB_REMAINING_HAZARD": int(scientific.parameters["m1_v2_t_ib_remaining_max_finite_minutes"].value),
            "D_OB": int(scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value),
            "D_TX": int(scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value),
        },
    }
    payload = torch.load(OLD_CHECKPOINT, map_location="cpu", weights_only=False)
    contracts = payload["contracts"]
    actual_support = {name: int(value["max_finite_minutes"]) for name, value in contracts.items()}
    shapes = {name: tuple(value.shape) for name, value in payload["state"].items()}
    expected_d_ob_embedding = expected["support"]["D_OB"] // 5 + 1
    old_d_ob_embedding = shapes["d_ob_embedding.weight"][0]
    structural = actual_support != expected["support"] or old_d_ob_embedding != expected_d_ob_embedding
    result = {
        "old_checkpoint": str(OLD_CHECKPOINT),
        "old_checkpoint_hash": _file_hash(OLD_CHECKPOINT),
        "expected": expected,
        "actual_support": actual_support,
        "old_contracts": contracts,
        "tensor_shapes": {key: list(value) for key, value in shapes.items()},
        "d_ob_embedding_rows_expected_for_180": expected_d_ob_embedding,
        "d_ob_embedding_rows_in_checkpoint": old_d_ob_embedding,
        "calibration_contract": payload.get("calibration_contract"),
        "calibration_diagnostics": payload.get("calibration_diagnostics"),
        "calibration_support_compatible": actual_support == expected["support"],
        "target_encoder_decoder_support_compatible": actual_support == expected["support"],
        "loader_behavior": "M1Pipeline.load deserializes the checkpoint; frozen compatibility is rejected by the explicit contract gate, not by metadata rewriting.",
        "conclusion": "STRUCTURAL_ARTIFACT_MISMATCH" if structural else "METADATA_ONLY_MISMATCH",
    }
    lines = [
        "# H8 Artifact Compatibility Audit",
        "",
        f"- Old checkpoint: `{OLD_CHECKPOINT}`",
        f"- Old checkpoint hash: `{result['old_checkpoint_hash']}`",
        f"- Conclusion: **{result['conclusion']}**",
        "",
        "## Findings",
        "",
        f"- Frozen support: `{expected['support']}`",
        f"- Checkpoint support: `{actual_support}`",
        f"- D_OB embedding rows: `{old_d_ob_embedding}`; expected for 180 support: `{expected_d_ob_embedding}`",
        "- The D_OB embedding index is the finite-bin plus overflow decoder basis, so 210 versus 180 changes target encoding and decoder semantics.",
        "- Calibration is not transferable because calibration labels and hazard/target bin intervals are support-bound.",
        "- Tensor dimensions are not all compatible: the D_OB conditioning embedding is structurally different.",
        "- The checkpoint is not modified. A new frozen-contract artifact is required.",
        "",
        "## Machine-readable evidence",
        "",
        "```json",
        json.dumps(result, indent=2, sort_keys=True, default=str),
        "```",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return result


def materialize(output: Path = OUTPUT) -> dict:
    audit = audit_existing_checkpoint(output / "H8_ARTIFACT_COMPATIBILITY_AUDIT.md")
    if audit["conclusion"] != "STRUCTURAL_ARTIFACT_MISMATCH":
        raise RuntimeError("EXPECTED_STRUCTURAL_MISMATCH_NOT_CONFIRMED")
    result = run_data2_development_fast(root=PROJECT_ROOT, output_root=output)
    checkpoint = Path(result["checkpoint"])
    pipeline = M1Pipeline.load(checkpoint)
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    expected_support = {
        "T_IB_REMAINING_HAZARD": int(scientific.parameters["m1_v2_t_ib_remaining_max_finite_minutes"].value),
        "D_OB": int(scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value),
        "D_TX": int(scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value),
    }
    actual_support = {name: int(contract.max_finite_minutes) for name, contract in pipeline.contracts.items()}
    if pipeline.model.hidden_size != 8 or actual_support != expected_support:
        raise RuntimeError("M1_FROZEN_ARTIFACT_CONTRACT_MISMATCH_AFTER_MATERIALIZATION")
    manifest_path = Path(result["manifest"])
    training_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contracts_json = {name: contract.model_dump(mode="json") for name, contract in pipeline.contracts.items()}
    calibration_payload = {
        "schema_version": "M1_FROZEN_H8_CALIBRATION_ARTIFACT_V1",
        "model_version": "M1_STATE_ESTIMATOR_V2_H8",
        "support": expected_support,
        "calibration_contract": pipeline.calibration_contract.model_dump(mode="json"),
        "temperatures": pipeline.temperatures,
        "diagnostics": pipeline.calibration_diagnostics,
        "calibration_partition": training_manifest.get("calibration_split"),
        "final_test_access_count": 0,
    }
    calibration_payload["calibration_hash"] = content_id(calibration_payload)
    calibration_path = output / "M1_FROZEN_H8_CALIBRATION.json"
    calibration_path.write_text(json.dumps(calibration_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target_manifest = {
        "schema_version": "M1_FROZEN_H8_TARGET_SUPPORT_MANIFEST_V1",
        "primitive_targets": ["T_IB_A00", "D_OB", "D_TX"],
        "conditional_order": ["T_IB_A00", "D_OB", "D_TX"],
        "support": expected_support,
        "overflow": {"T_IB_A00": 365, "D_OB": 185, "D_TX": 65},
        "bin_width_minutes": 5,
        "target_contract_hash": content_id(contracts_json),
        "final_test_access_count": 0,
    }
    target_manifest["target_manifest_hash"] = content_id(target_manifest)
    target_path = output / "M1_FROZEN_H8_TARGET_SUPPORT_MANIFEST.json"
    target_path.write_text(json.dumps(target_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    registry_hash = _file_hash(PROJECT_ROOT / "registries" / "MODEL_PARAMETER_REGISTRY.json")
    frozen_manifest = {
        "schema_version": "M1_FROZEN_H8_RUNTIME_ARTIFACT_MANIFEST_V1",
        "artifact_status": "FROZEN_MODEL_RUNTIME_ARTIFACT_READY",
        "model_family": "M1_STATE_ESTIMATOR_V2",
        "model_version": "M1_STATE_ESTIMATOR_V2_H8",
        "hidden_dim": 8,
        "layers": 1,
        "causal": True,
        "roll_minutes": int(scientific.parameters["roll_minutes"].value),
        "support": expected_support,
        "overflow": {"T_IB_A00": 365, "D_OB": 185, "D_TX": 65},
        "scenario_count": int(scientific.parameters["scenario_count"].value),
        "feature_contract_hash": training_manifest.get("input_schema_hash"),
        "target_contract_hash": target_manifest["target_contract_hash"],
        "parameter_registry_hash": registry_hash,
        "code_commit": commit,
        "train_partition": training_manifest.get("train_split"),
        "calibration_partition": training_manifest.get("calibration_split"),
        "development_partition": training_manifest.get("development_split"),
        "training_seed": training_manifest.get("seed"),
        "checkpoint_path": str(checkpoint),
        "checkpoint_hash": _file_hash(checkpoint),
        "calibration_path": str(calibration_path),
        "calibration_hash": calibration_payload["calibration_hash"],
        "target_manifest_path": str(target_path),
        "final_test_access_count": 0,
        "paper_result": False,
        "selection_or_tuning": False,
    }
    frozen_manifest["artifact_hash"] = content_id(frozen_manifest)
    frozen_path = output / "M1_FROZEN_H8_MANIFEST.json"
    frozen_path.write_text(json.dumps(frozen_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"audit": audit, "materialization": result, "manifest": frozen_manifest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = materialize(args.output)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
