"""Freeze the approved signed-M1 warning model without retraining or inference."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

from model.M1.contracts import STOCHASTIC_TARGETS
from model.M1.pipeline import M1Pipeline
from model.M1.warning import (
    PRINCIPAL_WARNING_EVENT,
    PRINCIPAL_WARNING_THRESHOLD_MINUTES,
)
from model.common.config import load_config_layers
from model.common.identity import content_id


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
H_EVIDENCE = OUT / "m1_signed_hstar_evidence.json"
W_EVIDENCE = OUT / "m1_signed_wstar_evidence.json"
SOURCE_CHECKPOINT = OUT / "runs_signed_wstar" / "W30_H32_seed20260813.pt"
SOURCE_MANIFEST = SOURCE_CHECKPOINT.with_suffix(".json")
FROZEN_CHECKPOINT = OUT / "M1_SIGNED_WARNING_MODEL_V1.pt"
FROZEN_MANIFEST = OUT / "M1_SIGNED_WARNING_MODEL_V1_MANIFEST.json"
APPROVAL_TOKEN = "D3_SIGNED_M1_PERMANENT_FREEZE"


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _repository_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _validate_approved_freeze(scientific, h_evidence: dict, w_evidence: dict) -> None:
    hidden = scientific.parameters["m1_hidden_size"]
    window = scientific.parameters["m1_fixed_history_window_minutes"]
    targets = scientific.parameters["m1_stochastic_targets"]
    artifact = scientific.parameters["m1_warning_model_artifact"]
    for parameter, expected in ((hidden, 32), (window, 30)):
        if parameter.value != expected:
            raise RuntimeError("SIGNED_M1_PERMANENT_FREEZE_VALUE_MISMATCH")
        if parameter.provenance.get("decision_id") != "D3_SIGNED_M1_H_W_REFREEZE":
            raise RuntimeError("SIGNED_M1_PERMANENT_FREEZE_PROVENANCE_MISMATCH")
        if parameter.provenance.get("final_test_access_count") != 0:
            raise RuntimeError("SIGNED_M1_PERMANENT_FREEZE_FINAL_TEST_VIOLATION")
    if tuple(targets.value) != STOCHASTIC_TARGETS:
        raise RuntimeError("SIGNED_M1_TARGET_CONTRACT_MISMATCH")
    if artifact.value != str(FROZEN_CHECKPOINT.relative_to(ROOT)).replace("\\", "/"):
        raise RuntimeError("SIGNED_M1_WARNING_ARTIFACT_PATH_MISMATCH")
    if h_evidence.get("provisional_signed_h_star") != 32:
        raise RuntimeError("SIGNED_H_EVIDENCE_MISMATCH")
    if w_evidence.get("provisional_signed_h_star") != 32 \
            or w_evidence.get("provisional_signed_w_star") != 30:
        raise RuntimeError("SIGNED_W_EVIDENCE_MISMATCH")
    if h_evidence.get("final_test_access_count") != 0 \
            or w_evidence.get("final_test_access_count") != 0:
        raise RuntimeError("SIGNED_EVIDENCE_FINAL_TEST_VIOLATION")


def _validate_source(source_manifest: dict, source_hash: str, w_evidence: dict) -> None:
    expected = {
        "completion_status": "PASS",
        "development_only": True,
        "paper_result": False,
        "hidden_size": 32,
        "fixed_history_window_minutes": 30,
        "training_seed": 20260813,
        "final_test_access_count": 0,
    }
    if any(source_manifest.get(key) != value for key, value in expected.items()):
        raise RuntimeError("SIGNED_WARNING_SOURCE_MANIFEST_MISMATCH")
    if tuple(source_manifest.get("target_contract", ())) != STOCHASTIC_TARGETS:
        raise RuntimeError("SIGNED_WARNING_SOURCE_TARGET_MISMATCH")
    if source_manifest.get("checkpoint_hash") != source_hash:
        raise RuntimeError("SIGNED_WARNING_SOURCE_CHECKPOINT_HASH_MISMATCH")
    w30_seeds = sorted(
        row["training_seed"]
        for row in w_evidence.get("per_w_run", ())
        if row.get("fixed_history_window_minutes") == 30
    )
    if not w30_seeds or source_manifest["training_seed"] != w30_seeds[0]:
        raise RuntimeError("SIGNED_WARNING_SOURCE_NOT_FIRST_PRE_REGISTERED_W_SEED")


def _freeze_checkpoint(source_hash: str) -> None:
    if FROZEN_CHECKPOINT.exists():
        if _hash_file(FROZEN_CHECKPOINT) != source_hash:
            raise RuntimeError("SIGNED_WARNING_FROZEN_ARTIFACT_HASH_MISMATCH")
        return
    temporary = FROZEN_CHECKPOINT.with_suffix(".pt.tmp")
    shutil.copyfile(SOURCE_CHECKPOINT, temporary)
    if _hash_file(temporary) != source_hash:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("SIGNED_WARNING_ARTIFACT_COPY_HASH_MISMATCH")
    temporary.replace(FROZEN_CHECKPOINT)


def _validate_frozen_checkpoint() -> None:
    pipeline = M1Pipeline.load(FROZEN_CHECKPOINT)
    if pipeline.model.hidden_size != 32:
        raise RuntimeError("SIGNED_WARNING_FROZEN_HIDDEN_SIZE_MISMATCH")
    if set(pipeline.bins) != set(STOCHASTIC_TARGETS):
        raise RuntimeError("SIGNED_WARNING_FROZEN_TARGET_SET_MISMATCH")
    if not all(hasattr(pipeline.model, name) for name in (
        "ib_head", "delta_ob_head", "tx_head", "ib_embedding", "delta_ob_embedding"
    )):
        raise RuntimeError("SIGNED_WARNING_FROZEN_ORDERED_NETWORK_MISMATCH")
    delta = pipeline.bins["DELTA_OB"]
    if not delta.signed or delta.min_finite_minutes != -180 or delta.max_finite_minutes != 180:
        raise RuntimeError("SIGNED_WARNING_FROZEN_BIN_CONTRACT_MISMATCH")


def _manifest_payload(*, source_manifest: dict, source_hash: str,
                      h_evidence: dict, w_evidence: dict) -> dict:
    payload = {
        "schema_version": "M1_SIGNED_WARNING_MODEL_V1",
        "status": "FROZEN",
        "decision_id": "D3_SIGNED_M1_H_W_REFREEZE",
        "decision_date": "2026-08-17",
        "target_contract": list(STOCHASTIC_TARGETS),
        "derived_scenario_values": ["R_OB", "T_OB", "T_TO", "D_TO"],
        "hidden_size": 32,
        "fixed_history_window_minutes": 30,
        "training_seed": 20260813,
        "artifact_selection_rule": "FIRST_PRE_REGISTERED_W_SEED",
        "development_metric_not_used_for_seed_selection": True,
        "source_checkpoint": str(SOURCE_CHECKPOINT.relative_to(ROOT)),
        "source_checkpoint_hash": source_hash,
        "source_checkpoint_manifest": str(SOURCE_MANIFEST.relative_to(ROOT)),
        "source_checkpoint_manifest_hash": _hash_file(SOURCE_MANIFEST),
        "frozen_checkpoint": str(FROZEN_CHECKPOINT.relative_to(ROOT)),
        "frozen_checkpoint_hash": _hash_file(FROZEN_CHECKPOINT),
        "source_training_repository_sha": source_manifest["repository_sha"],
        "freeze_sync_repository_sha": _repository_sha(),
        "signed_h_evidence": str(H_EVIDENCE.relative_to(ROOT)),
        "signed_h_evidence_hash": h_evidence["evidence_hash"],
        "signed_h_evidence_byte_hash": _hash_file(H_EVIDENCE),
        "signed_w_evidence": str(W_EVIDENCE.relative_to(ROOT)),
        "signed_w_evidence_hash": w_evidence["evidence_hash"],
        "signed_w_evidence_byte_hash": _hash_file(W_EVIDENCE),
        "signed_cache_hash": source_manifest["cache_hash"],
        "warning_probability_contract": {
            "principal_event": PRINCIPAL_WARNING_EVENT,
            "strict_operator": ">",
            "delay_threshold_minutes": PRINCIPAL_WARNING_THRESHOLD_MINUTES,
            "derived_quantity": "max(0, DELTA_OB + T_TX - train_frozen_taxi_reference)",
            "estimator": "WEIGHTED_ALIGNED_SCENARIO_FREQUENCY",
            "tail_value_policy": "TARGET_BIN_REPRESENTATIVE",
            "missing_taxi_reference": "ABSTAIN",
        },
        "warning_probability_implementation_status": "READY",
        "warning_operating_point_status": "NOT_FROZEN",
        "full_development_warning_inference": "NOT_RUN",
        "final_test_access_count": 0,
        "paper_full_run": False,
        "h_w_rerun": False,
    }
    return {**payload, "manifest_hash": content_id(payload)}


def freeze() -> dict:
    h_evidence = _read_json(H_EVIDENCE)
    w_evidence = _read_json(W_EVIDENCE)
    source_manifest = _read_json(SOURCE_MANIFEST)
    scientific = load_config_layers(ROOT / "configs").scientific
    source_hash = _hash_file(SOURCE_CHECKPOINT)
    _validate_approved_freeze(scientific, h_evidence, w_evidence)
    _validate_source(source_manifest, source_hash, w_evidence)
    _freeze_checkpoint(source_hash)
    _validate_frozen_checkpoint()
    manifest = _manifest_payload(
        source_manifest=source_manifest,
        source_hash=source_hash,
        h_evidence=h_evidence,
        w_evidence=w_evidence,
    )
    serialized = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if FROZEN_MANIFEST.exists():
        if FROZEN_MANIFEST.read_text(encoding="utf-8") != serialized:
            raise RuntimeError("SIGNED_WARNING_FROZEN_MANIFEST_MISMATCH")
        return manifest
    temporary = FROZEN_MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(FROZEN_MANIFEST)
    return manifest


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Freeze approved signed-M1 warning artifact")
    parser.add_argument("--approval-token", required=True)
    args = parser.parse_args(argv)
    if args.approval_token != APPROVAL_TOKEN:
        raise RuntimeError("SIGNED_WARNING_FREEZE_REQUIRES_APPROVAL")
    manifest = freeze()
    print(json.dumps({
        "status": manifest["status"],
        "artifact": manifest["frozen_checkpoint"],
        "artifact_hash": manifest["frozen_checkpoint_hash"],
        "full_development_warning_inference": "NOT_RUN",
        "final_test_access_count": 0,
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
