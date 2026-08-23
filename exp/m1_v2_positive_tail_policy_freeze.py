"""Freeze the M1 positive-tail representation without changing model weights.

The frozen representation is categorical at the support boundary: finite
support bins plus an explicit overflow tail class.  Raw observed values are
carried alongside the class identity; no scalar extrapolation is introduced.
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

from model.common.identity import content_id


OUTPUT_DIRECTORY = Path("artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2")
MANIFEST_NAME = "M1_V2_POSITIVE_TAIL_POLICY_FREEZE_MANIFEST.json"
SUPPORT_NAME = "M1_V2_TARGET_SUPPORT_MANIFEST.json"
LINEAGE_NAME = "M1_V2_POSITIVE_TAIL_LINEAGE.json"
POLICY = "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
TAIL_CLASS_ID = "OVERFLOW_TAIL"
SUPPORT = {
    "T_IB_A00": 360,
    "D_OB": 210,
    "D_TX": 60,
}
BIN_WIDTH_MINUTES = 5
_SAFETY = {
    "M1_TRAINING_RUNS_THIS_FREEZE": 0,
    "TUNING_RUNS_THIS_FREEZE": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_POSITIVE_TAIL_FREEZE_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _target_contract(target: str, q_max: int) -> dict[str, Any]:
    finite_bin_count = q_max // BIN_WIDTH_MINUTES
    return {
        "target": target,
        "q_max_minutes": q_max,
        "bin_width_minutes": BIN_WIDTH_MINUTES,
        "finite_support_interval": "[0, q_max)",
        "finite_bin_count": finite_bin_count,
        "tail_class": {
            "class_id": TAIL_CLASS_ID,
            "index": finite_bin_count,
            "interval": "[q_max, +inf)",
            "explicit": True,
            "observable": True,
            "raw_value_preserved": True,
            "overflow_flag_preserved": True,
        },
        "class_count": finite_bin_count + 1,
        "no_truncation": True,
        "no_deletion": True,
        "no_winsorization": True,
    }


def freeze_positive_tail_policy(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / OUTPUT_DIRECTORY).resolve()
    paths = {
        "foundation": root / "configs/scientific/foundation.yaml",
        "binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "freeze": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "checkpoint": root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
        "b2_schema": root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_FEATURE_SCHEMA_FROZEN_B2.json",
        "b2_cache_manifest": root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
        "refreeze": root / "artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3/M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json",
        "cohort": root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V3.json",
        "prior_packet": root / "artifacts/diagnostics/m1_v2_positive_tail_decision/M1_V2_CURRENT_STAGE_POSITIVE_TAIL_HUMAN_DECISION_PACKET.json",
        "c0a": root / "artifacts/diagnostics/m1_v2_target_support_gate_c0a/AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0A.json",
    }
    _require(all(path.is_file() for path in paths.values()), "M1_V2_POSITIVE_TAIL_FREEZE_INPUT_MISSING")
    foundation = yaml.safe_load(paths["foundation"].read_text(encoding="utf-8"))
    parameters = foundation["parameters"]
    policy = parameters["m1_v2_positive_tail_policy"]
    binding = _load(paths["binding"])
    freeze = _load(paths["freeze"])
    b2_schema = _load(paths["b2_schema"])
    b2_cache = _load(paths["b2_cache_manifest"])
    refreeze = _load(paths["refreeze"])
    cohort = _load(paths["cohort"])
    prior_packet = _load(paths["prior_packet"])
    c0a = _load(paths["c0a"])
    checkpoint_hash_before = _hash(paths["checkpoint"])

    _require(policy["freeze_state"] == "FROZEN", "M1_V2_POSITIVE_TAIL_FREEZE_CONFIG_NOT_FROZEN")
    _require(policy["value"] == POLICY, "M1_V2_POSITIVE_TAIL_FREEZE_POLICY_MISMATCH")
    provenance = policy["provenance"]
    _require(provenance["decision_id"] == "AIR_SLOT_M1_POSITIVE_TAIL_POLICY_FREEZE", "M1_V2_POSITIVE_TAIL_FREEZE_DECISION_ID_INVALID")
    _require(provenance["target_q_max_minutes"] == SUPPORT, "M1_V2_POSITIVE_TAIL_FREEZE_QMAX_MISMATCH")
    _require(provenance["representation"] == POLICY, "M1_V2_POSITIVE_TAIL_FREEZE_REPRESENTATION_INVALID")
    _require(provenance["tail_class_id"] == TAIL_CLASS_ID, "M1_V2_POSITIVE_TAIL_FREEZE_TAIL_CLASS_INVALID")
    _require(provenance["threshold_tuning"]["development_based_threshold_tuning"] is False, "M1_V2_POSITIVE_TAIL_FREEZE_DEVELOPMENT_TUNING_FORBIDDEN")
    _require(binding["status"] == "BOUND_FROZEN_M1_V2", "M1_V2_POSITIVE_TAIL_FREEZE_M1_BINDING_INVALID")
    _require(binding["frozen_contracts"]["support"] == {"T_IB": 360, "D_OB": 210, "D_TX": 60, "bin_width_minutes": 5}, "M1_V2_POSITIVE_TAIL_FREEZE_SUPPORT_DRIFT")
    _require(binding["frozen_contracts"]["feature_schema_hash"] == b2_cache["feature_schema_hash"], "M1_V2_POSITIVE_TAIL_FREEZE_FEATURE_HASH_DRIFT")
    _require(binding["frozen_contracts"]["cache_hash"] == b2_cache["cache_hash"], "M1_V2_POSITIVE_TAIL_FREEZE_CACHE_HASH_DRIFT")
    _require(b2_schema["schema_hash"] == binding["frozen_contracts"]["feature_schema_hash"], "M1_V2_POSITIVE_TAIL_FREEZE_B2_SCHEMA_HASH_DRIFT")
    _require(b2_schema["dynamic_feature_count"] == 39 and b2_schema["static_feature_count"] == 4 and b2_schema["total_feature_count"] == 43, "M1_V2_POSITIVE_TAIL_FREEZE_B2_FEATURE_COUNT_DRIFT")
    _require(refreeze["status"] == "NEW_DEVELOPMENT_COHORT_REFROZEN", "M1_V2_POSITIVE_TAIL_FREEZE_REFREEZE_INVALID")
    _require(cohort["cohort_hash"] == refreeze["new_cohort"]["cohort_hash"], "M1_V2_POSITIVE_TAIL_FREEZE_COHORT_HASH_DRIFT")
    _require(prior_packet["status"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED", "M1_V2_POSITIVE_TAIL_FREEZE_PRIOR_PACKET_NOT_PRESERVED")
    _require(c0a["b2_immutability"]["schema_unchanged"] is True and c0a["b2_immutability"]["cache_unchanged"] is True, "M1_V2_POSITIVE_TAIL_FREEZE_B2_IMMUTABILITY_INVALID")

    target_contracts = {target: _target_contract(target, q_max) for target, q_max in SUPPORT.items()}
    support_payload = _artifact({
        "schema_version": "M1_V2_TARGET_SUPPORT_MANIFEST_V2",
        "status": "M1_POSITIVE_TAIL_POLICY_FROZEN",
        "decision_id": "AIR_SLOT_M1_POSITIVE_TAIL_POLICY_FREEZE",
        "representation": POLICY,
        "tail_class_id": TAIL_CLASS_ID,
        "target_contracts": target_contracts,
        "support_hash": binding["frozen_contracts"]["support_hash"],
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "cache_hash": binding["frozen_contracts"]["cache_hash"],
        "checkpoint_sha256": binding["checkpoint"]["sha256"],
        "source_support_provenance": "V2_SUPPORT_REFROZEN_AFTER_A2_B2",
        "threshold_tuning": {
            "development_based_threshold_tuning": False,
            "q_max_values_are_not_reestimated": True,
        },
        "observation_policy": {
            "tail_events_observable": True,
            "raw_observed_value_required": True,
            "tail_class_required_at_or_above_q_max": True,
            "no_truncation": True,
            "no_deletion": True,
            "no_winsorization": True,
            "continuous_tail_extrapolation": False,
            "continuous_quantile_above_q_max": "ABSTAIN_EXPLICIT_TAIL_CLASS_REQUIRED",
        },
        "safety": dict(_SAFETY),
    })
    support_path = output_root / SUPPORT_NAME
    _write(support_path, support_payload)

    lineage_payload = _artifact({
        "schema_version": "M1_V2_POSITIVE_TAIL_LINEAGE_V1",
        "status": "M1_POSITIVE_TAIL_POLICY_FROZEN",
        "decision_id": "AIR_SLOT_M1_POSITIVE_TAIL_POLICY_FREEZE",
        "policy": POLICY,
        "support_manifest": {"path": _relative(support_path, root), "sha256": _hash(support_path), "artifact_hash": support_payload["artifact_hash"]},
        "prior_human_decision_packet": {"path": _relative(paths["prior_packet"], root), "sha256": _hash(paths["prior_packet"]), "status": prior_packet["status"]},
        "current_stage_refreeze": {"path": _relative(paths["refreeze"], root), "sha256": _hash(paths["refreeze"]), "cohort_hash": cohort["cohort_hash"]},
        "m1_binding": {"path": _relative(paths["binding"], root), "sha256": _hash(paths["binding"]), "model_id": binding["model_id"], "checkpoint_sha256": binding["checkpoint"]["sha256"]},
        "b2": {"schema_path": _relative(paths["b2_schema"], root), "schema_sha256": _hash(paths["b2_schema"]), "schema_hash": b2_schema["schema_hash"], "cache_manifest_path": _relative(paths["b2_cache_manifest"], root), "cache_hash": b2_cache["cache_hash"]},
        "support": SUPPORT,
        "tail_class": {"class_id": TAIL_CLASS_ID, "raw_value_preserved": True, "observable": True},
        "checkpoint_hash_before": checkpoint_hash_before,
        "checkpoint_hash_after": _hash(paths["checkpoint"]),
        "checkpoint_unchanged": checkpoint_hash_before == _hash(paths["checkpoint"]),
        "feature_schema_unchanged": True,
        "support_boundaries_unchanged": True,
        "safety": dict(_SAFETY),
    })
    lineage_path = output_root / LINEAGE_NAME
    _write(lineage_path, lineage_payload)

    manifest_payload = _artifact({
        "schema_version": "M1_V2_POSITIVE_TAIL_POLICY_FREEZE_MANIFEST_V1",
        "status": "M1_POSITIVE_TAIL_POLICY_FROZEN",
        "decision_id": "AIR_SLOT_M1_POSITIVE_TAIL_POLICY_FREEZE",
        "representation": POLICY,
        "target_support_manifest": _relative(support_path, root),
        "target_support_manifest_sha256": _hash(support_path),
        "target_support_manifest_artifact_hash": support_payload["artifact_hash"],
        "lineage": _relative(lineage_path, root),
        "lineage_sha256": _hash(lineage_path),
        "lineage_artifact_hash": lineage_payload["artifact_hash"],
        "current_stage_cohort_hash": cohort["cohort_hash"],
        "stage_distribution": refreeze["stage_audit"],
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "cache_hash": binding["frozen_contracts"]["cache_hash"],
        "support_hash": binding["frozen_contracts"]["support_hash"],
        "checkpoint_sha256": binding["checkpoint"]["sha256"],
        "model_id": binding["model_id"],
        "b2_schema_unchanged": True,
        "feature_unchanged": True,
        "checkpoint_unchanged": True,
        "downstream_status": "READY_FOR_EXP2_EXP3_EXP4_REBIND_SCENARIOS_REMAIN_SEPARATE",
        "next_gate": "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_REQUIRED",
        "safety": dict(_SAFETY),
    })
    manifest_path = output_root / MANIFEST_NAME
    _write(manifest_path, manifest_payload)
    return {"manifest": manifest_path, "support": support_path, "lineage": lineage_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    outputs = freeze_positive_tail_policy(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    payload = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    print(json.dumps({"status": payload["status"], "manifest": str(outputs["manifest"]), **_SAFETY}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
