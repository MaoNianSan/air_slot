"""Create the positive-tail human gate for the current-stage refrozen cohort."""

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


OUTPUT_DIRECTORY = Path("artifacts/diagnostics/m1_v2_positive_tail_decision")
PACKET_NAME = "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_HUMAN_DECISION_PACKET.json"
_SAFETY = {
    "M1_TRAINING_RUNS_THIS_PACKET": 0,
    "TUNING_RUNS_THIS_PACKET": 0,
    "EXP1_RUNS_THIS_PACKET": 0,
    "EXP2_RUNS_THIS_PACKET": 0,
    "EXP3_RUNS_THIS_PACKET": 0,
    "EXP4_RUNS_THIS_PACKET": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_CURRENT_STAGE_POSITIVE_TAIL_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def create_current_stage_positive_tail_packet(*, root: Path, output_root: Path | None = None) -> Path:
    root = Path(root).resolve()
    output_root = (output_root or root / OUTPUT_DIRECTORY).resolve()
    refreeze_path = root / "artifacts/diagnostics/m1_v2_development_current_stage_refreeze/M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json"
    cohort_path = root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V2.json"
    binding_path = root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json"
    checkpoint_path = root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
    foundation_path = root / "configs/scientific/foundation.yaml"
    _require = lambda value, code: (_ for _ in ()).throw(RuntimeError(code)) if not value else None
    _require(all(path.is_file() for path in (refreeze_path, cohort_path, binding_path, checkpoint_path, foundation_path)), "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_INPUT_MISSING")
    refreeze = _load(refreeze_path)
    cohort = _load(cohort_path)
    binding = _load(binding_path)
    foundation = yaml.safe_load(foundation_path.read_text(encoding="utf-8"))
    parameters = foundation["parameters"]
    tail = parameters["m1_v2_positive_tail_policy"]
    levels = parameters["m1_v2_quantile_levels"]
    _require(refreeze["status"] == "NEW_DEVELOPMENT_COHORT_REFROZEN", "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_REFREEZE_INVALID")
    _require(refreeze["next_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED", "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_NEXT_GATE_INVALID")
    _require(cohort["cohort_hash"] == refreeze["new_cohort"]["cohort_hash"], "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_COHORT_HASH_MISMATCH")
    _require(tail["freeze_state"] == "HUMAN_DECISION_REQUIRED" and tail["value"] == "UNRESOLVED", "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_POLICY_ALREADY_CHANGED")
    _require(tail["provenance"]["human_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED", "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_GATE_CODE_MISMATCH")
    pipeline = M1Pipeline.load(checkpoint_path)
    policies = {name: contract.upper_tail_policy for name, contract in pipeline.contracts.items() if hasattr(contract, "upper_tail_policy")}
    _require(set(policies) == {"D_OB", "D_TX"}, "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_TARGET_MISMATCH")
    _require(set(policies.values()) == {"UNRESOLVED"}, "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_CONTRACT_POLICY_MISMATCH")
    payload = {
        "schema_version": "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_HUMAN_DECISION_PACKET_V1",
        "status": "M1_POSITIVE_TAIL_DECISION_REQUIRED",
        "scope": "CURRENT_STAGE_REFROZEN_DEVELOPMENT_SCENARIO_ENVELOPE_GATE",
        "cohort": {
            "path": str(cohort_path.relative_to(root)).replace("\\", "/"),
            "sha256": _hash(cohort_path),
            "cohort_hash": cohort["cohort_hash"],
            "episode_count": len(cohort["episode_ids"]),
            "node_count": len(cohort["node_ids"]),
        },
        "refreeze_manifest": {
            "path": str(refreeze_path.relative_to(root)).replace("\\", "/"),
            "sha256": _hash(refreeze_path),
            "artifact_hash": refreeze["artifact_hash"],
            "current_replay_policy": refreeze["current_replay_policy"],
            "stage_distribution": refreeze["stage_audit"],
        },
        "frozen_checkpoint": {
            "model_id": binding["model_id"],
            "path": str(checkpoint_path.relative_to(root)).replace("\\", "/"),
            "sha256": binding["checkpoint"]["sha256"],
            "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
            "support_hash": binding["frozen_contracts"]["support_hash"],
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
            "allowed_before_decision": ["current-stage cohort lineage", "43-feature compatibility", "conditional head schema validation"],
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
    }
    payload["artifact_hash"] = content_id(payload)
    output = output_root / PACKET_NAME
    _write(output, payload)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    path = create_current_stage_positive_tail_packet(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print(json.dumps({"status": "M1_POSITIVE_TAIL_DECISION_REQUIRED", "packet": str(path), **_SAFETY}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
