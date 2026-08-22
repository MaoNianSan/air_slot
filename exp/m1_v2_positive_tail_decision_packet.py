"""Write the explicit human gate for M1 V2 positive-tail scenarios.

No tail rule is selected here.  This packet turns the configured unresolved
state into a durable artifact after the Development inference inputs bind.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.M1.pipeline import M1Pipeline
from model.common.identity import content_id


ARTIFACT_DIRECTORY = Path("artifacts/diagnostics/m1_v2_positive_tail_decision")
PACKET_NAME = "M1_V2_POSITIVE_TAIL_HUMAN_DECISION_PACKET.json"

_SAFETY = {
    "M1_TRAINING_RUNS_THIS_PACKET": 0,
    "TUNING_RUNS_THIS_PACKET": 0,
    "EXP1_RUNS_THIS_PACKET": 0,
    "EXP2_RUNS_THIS_PACKET": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_POSITIVE_TAIL_PACKET_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _safety(payload: dict[str, Any], prefix: str) -> None:
    source = payload.get("safety", payload)
    _require(source.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) == 0, f"{prefix}_FINAL_TEST_ACCESS_NONZERO")
    _require(source.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is False, f"{prefix}_PAPER_FULL_TRUE")
    full = source.get("FULL", payload.get("FULL"))
    if full is not None:
        _require(full is False, f"{prefix}_FULL_TRUE")


def create_positive_tail_decision_packet(*, root: Path, output_root: Path | None = None) -> Path:
    root = Path(root).resolve()
    output_root = (output_root or root / ARTIFACT_DIRECTORY).resolve()
    manifest_path = root / "artifacts/diagnostics/m1_v2_development_inference_binding/M1_V2_DEVELOPMENT_INFERENCE_BINDING_MANIFEST.json"
    binding_path = root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json"
    checkpoint_path = root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
    foundation_path = root / "configs/scientific/foundation.yaml"
    _require(all(path.is_file() for path in (manifest_path, binding_path, checkpoint_path, foundation_path)), "M1_V2_POSITIVE_TAIL_PACKET_INPUT_MISSING")
    manifest, binding = _load(manifest_path), _load(binding_path)
    _require(manifest.get("status") == "M1_V2_DEVELOPMENT_INFERENCE_BINDING_READY", "M1_V2_POSITIVE_TAIL_PACKET_INPUT_BINDING_NOT_READY")
    _require(binding.get("status") == "BOUND_FROZEN_M1_V2", "M1_V2_POSITIVE_TAIL_PACKET_FROZEN_BINDING_INVALID")
    _safety(manifest, "M1_V2_POSITIVE_TAIL_PACKET_BINDING")
    _safety(binding, "M1_V2_POSITIVE_TAIL_PACKET_M1")
    _require(_hash(checkpoint_path) == binding["checkpoint"]["sha256"], "M1_V2_POSITIVE_TAIL_PACKET_CHECKPOINT_HASH_MISMATCH")
    foundation = yaml.safe_load(foundation_path.read_text(encoding="utf-8"))
    parameters = foundation["parameters"]
    tail = parameters["m1_v2_positive_tail_policy"]
    levels = parameters["m1_v2_quantile_levels"]
    _require(tail["freeze_state"] == "HUMAN_DECISION_REQUIRED", "M1_V2_POSITIVE_TAIL_PACKET_GATE_NOT_HUMAN")
    _require(tail["value"] == "UNRESOLVED", "M1_V2_POSITIVE_TAIL_PACKET_POLICY_ALREADY_CHANGED")
    _require(tail["provenance"]["human_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED", "M1_V2_POSITIVE_TAIL_PACKET_GATE_CODE_MISMATCH")
    pipeline = M1Pipeline.load(checkpoint_path)
    policies = {
        name: contract.upper_tail_policy
        for name, contract in pipeline.contracts.items()
        if hasattr(contract, "upper_tail_policy")
    }
    _require(set(policies) == {"D_OB", "D_TX"}, "M1_V2_POSITIVE_TAIL_PACKET_CONTRACT_TARGET_MISMATCH")
    _require(set(policies.values()) == {"UNRESOLVED"}, "M1_V2_POSITIVE_TAIL_PACKET_CONTRACT_POLICY_MISMATCH")
    _require(
        all(tuple(contract.quantile_levels) == tuple(levels["value"]) for contract in pipeline.contracts.values() if hasattr(contract, "quantile_levels")),
        "M1_V2_POSITIVE_TAIL_PACKET_QUANTILE_GRID_MISMATCH",
    )
    payload = _artifact({
        "schema_version": "M1_V2_POSITIVE_TAIL_HUMAN_DECISION_PACKET_V1",
        "status": "M1_POSITIVE_TAIL_DECISION_REQUIRED",
        "scope": "DEVELOPMENT_ONLY_SCENARIO_ENVELOPE_GATE",
        "upstream_inference_binding": {
            "path": str(manifest_path.relative_to(root)).replace("\\", "/"),
            "sha256": _hash(manifest_path),
            "input_artifact": manifest["input_artifact"],
        },
        "frozen_checkpoint": {
            "model_id": binding["model_id"],
            "path": str(checkpoint_path.relative_to(root)).replace("\\", "/"),
            "sha256": binding["checkpoint"]["sha256"],
        },
        "configured_policy": {
            "freeze_state": tail["freeze_state"],
            "value": tail["value"],
            "human_gate": tail["provenance"]["human_gate"],
            "positive_quantile_grid": levels["value"],
            "q_max": max(levels["value"]),
            "cvar_alpha_reference": tail["provenance"]["cvar_alpha_reference"],
            "checkpoint_contract_policies": policies,
        },
        "scenario_envelope": {
            "joint_state_distribution_artifact": "BLOCKED",
            "marginal_distribution_artifact": "BLOCKED_FOR_SCENARIO_DERIVATION",
            "reason": "Q(u) above q_max has no frozen principal-path rule",
            "allowed_before_decision": ["frozen_input_lineage", "conditional_head_schema_validation"],
            "prohibited_without_human_decision": [
                "clamp_to_q_max",
                "implicit_linear_extrapolation",
                "TEST_ONLY_LINEAR",
                "synthetic_tail_completion",
                "Exp2_4_metric_generation",
            ],
        },
        "human_decision_required": [
            "positive_quantile_levels_and_q_max",
            "upper_tail_representation_or_extrapolation_rule",
            "calibration_and_development_freeze_procedure",
            "authorization_to_materialize_joint_scenarios_after_freeze",
        ],
        "no_automatic_fallback": True,
        **_SAFETY,
    })
    path = output_root / PACKET_NAME
    _write(path, payload)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    path = create_positive_tail_decision_packet(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print(json.dumps({"status": "M1_POSITIVE_TAIL_DECISION_REQUIRED", "packet": str(path), **_SAFETY}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
