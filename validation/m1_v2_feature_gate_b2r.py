"""B2R semantic redundancy repair and candidate-cache materialization."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from model.common.identity import content_id
from model.M1.cache import CACHE_SCHEMA_VERSION, M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.data_usage_contract_audit import run as run_data_usage_audit
from validation.m1_v2_feature_gate_b1r import A2_EXPECTED_CACHE_HASH, DEFAULT_OUTPUT as B1R_OUTPUT
from validation.m1_v2_feature_profile import feature_profiles, missing_encoding_audit, shift_diagnostics
from validation.m1_v2_feature_redundancy import redundancy_audit
from validation.m1_v2_feature_semantics import history_semantics
from validation.ownership_gate_v2 import build_gate_result


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b2r"
B1R_CACHE_HASH = "sha256:57c668b687bf08b9aa0ebfbd60c0b6792d970a38e39e5a5d104294aa44f3153e"
B1R_SCHEMA_HASH = "sha256:0fa54b2b5d2db31ed15b10c6a4f3eba8dd1b3e3e82300cc70f6417266057930b"
REMOVED_SCHEDULE_DELTA = (
    "delta.schedule.signed_minutes_to_crs_departure",
    "delta.schedule.signed_minutes_to_crs_departure.derived_missing_mask",
)
DECISIONS = {
    "B2R-D01": "EMPIRICAL_EQUALITY_NOT_CONTRACT_REDUNDANCY",
    "B2R-D02": "RETAIN_EMPIRICAL_DUPLICATES",
    "B2R-D03": "REMOVE_FIXED_GRID_SCHEDULE_DELTA_PAIR",
}
SAFETY_BASE = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "GATE_B_ENTERED": True,
    "M1_TARGET_SUPPORT_FROZEN": False,
    "HYPERPARAMETER_TUNING_AUTHORIZED": False,
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _load_b1r() -> tuple[M1DevelopmentBaseCache, dict, dict, dict]:
    manifest_path = B1R_OUTPUT / "M1_V2_FEATURE_GATE_B1R_CANDIDATE_CACHE_MANIFEST.json"
    data_path = B1R_OUTPUT / "M1_V2_FEATURE_GATE_B1R_CANDIDATE_CACHE.npz"
    report = _read_json(B1R_OUTPUT / "AIR_SLOT_M1_V2_FEATURE_GATE_B1R.json")
    schema = _read_json(B1R_OUTPUT / "M1_V2_FEATURE_SCHEMA_CANDIDATE_B1R.json")
    manifest = _read_json(manifest_path)
    cache = M1DevelopmentBaseCache.load(data_path, manifest_path, expected_cache_key=manifest["cache_key"])
    if manifest["cache_hash"] != B1R_CACHE_HASH or report["cache"]["candidate_cache_hash"] != B1R_CACHE_HASH:
        raise ValueError("M1_B2R_B1R_CACHE_HASH_MISMATCH")
    if schema["schema_hash"] != B1R_SCHEMA_HASH or report["feature_schema"]["schema_hash"] != B1R_SCHEMA_HASH:
        raise ValueError("M1_B2R_B1R_SCHEMA_HASH_MISMATCH")
    if report["FEATURE_GATE_STATUS"] != "FEATURE_GATE_B1R_PASS_CANDIDATE_READY_FOR_B2":
        raise ValueError("M1_B2R_B1R_NOT_READY")
    if tuple(manifest["feature_names"]) != tuple(schema["ordered_dynamic_features"]):
        raise ValueError("M1_B2R_B1R_FEATURE_ORDER_MISMATCH")
    return cache, manifest, report, schema


def _candidate_schema(b1r_schema: dict) -> dict:
    removed = set(REMOVED_SCHEDULE_DELTA)
    payload = deepcopy(b1r_schema)
    payload["schema_version"] = "M1_V2_FEATURE_SCHEMA_CANDIDATE_B2R_V1"
    payload["schema_id"] = "M1_V2_FEATURE_SCHEMA_CANDIDATE_B2R"
    payload["schema_status"] = "CANDIDATE_NOT_FROZEN"
    payload["training_frozen"] = False
    payload["ordered_dynamic_features"] = [name for name in b1r_schema["ordered_dynamic_features"] if name not in removed]
    payload["dynamic_feature_count"] = len(payload["ordered_dynamic_features"])
    payload["static_feature_count"] = len(payload["ordered_static_features"])
    payload["total_feature_count"] = payload["dynamic_feature_count"] + payload["static_feature_count"]
    payload["features"] = [row for row in b1r_schema["features"] if row["FEATURE"] not in removed]
    payload["groups"] = {
        group: [row for row in rows if row["feature"] not in removed]
        for group, rows in b1r_schema["groups"].items()
    }
    payload["removed"] = deepcopy(b1r_schema["removed"])
    payload["removed"].setdefault("b2r_fixed_grid_schedule_delta", [])
    payload["removed"]["b2r_fixed_grid_schedule_delta"] = list(REMOVED_SCHEDULE_DELTA)
    payload["removed"]["all_exact_removed_feature_names"] = list(
        dict.fromkeys(payload["removed"].get("all_exact_removed_feature_names", []) + list(REMOVED_SCHEDULE_DELTA))
    )
    payload["applied_decisions"] = {**b1r_schema["applied_decisions"], **DECISIONS}
    payload["source_b1r_schema_hash"] = b1r_schema["schema_hash"]
    payload["source_b1r_candidate_feature_count"] = len(b1r_schema["ordered_dynamic_features"])
    payload.pop("schema_hash", None)
    payload.pop("schema_hash_basis", None)
    payload["schema_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_SCHEMA_HASH"
    payload["schema_hash"] = content_id(payload)
    return payload


def _identity_equal(left, right) -> dict[str, bool]:
    return {
        "labels": all(left.store.labels[name].equal(right.store.labels[name]) for name in left.store.labels),
        "active": all(left.store.active[name].equal(right.store.active[name]) for name in left.store.active),
        "episode_ids": left.store.episode_ids == right.store.episode_ids,
        "episode_offsets": left.store.episode_offsets.equal(right.store.episode_offsets),
        "sample_episode_indices": left.store.sample_episode_indices.equal(right.store.sample_episode_indices),
        "sample_start_offsets": left.store.sample_start_offsets.equal(right.store.sample_start_offsets),
        "sample_end_offsets": left.store.sample_end_offsets.equal(right.store.sample_end_offsets),
        "sample_episode_ids": left.store.sample_episode_ids == right.store.sample_episode_ids,
        "sample_decision_node_ids": left.store.sample_decision_node_ids == right.store.sample_decision_node_ids,
        "sample_episode_dates": left.store.sample_episode_dates == right.store.sample_episode_dates,
        "sample_splits": left.store.sample_splits == right.store.sample_splits,
        "static_context_lineages": left.store.static_context_lineages == right.store.static_context_lineages,
    }


def _roundtrip_equal(left, right) -> dict[str, Any]:
    checks = {
        "dynamic_tensor": left.store.values_flat.equal(right.store.values_flat),
        "static_tensor": left.store.static_values.equal(right.store.static_values),
        **_identity_equal(left, right),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _write_packet(path: Path, report: dict) -> None:
    lines = [
        "# M1 V2 Feature Gate B2R Redundancy Semantics Packet",
        "",
        f"- Status: `{report['FEATURE_GATE_STATUS']}`",
        f"- Dynamic/static/total: {report['feature_counts']['dynamic']} / {report['feature_counts']['static']} / {report['feature_counts']['total']}",
        f"- B1R schema hash: `{report['feature_schema']['b1r_schema_hash']}`",
        f"- B2R candidate schema hash: `{report['feature_schema']['b2r_candidate_schema_hash']}`",
        f"- Contract exact duplicates: `{report['redundancy']['contract_exact_duplicate_count']}`",
        f"- Empirical exact duplicates: `{report['redundancy']['empirical_exact_duplicate_count']}`",
        f"- Train support constants: `{report['redundancy']['train_support_constant_count']}`",
        f"- Fixed-grid schedule delta removed: `{report['schedule_delta']['numeric_removed']}`",
        f"- Frozen schema hash: `{report.get('frozen_schema_hash')}`",
        f"- Frozen cache hash: `{report.get('frozen_cache_hash')}`",
        f"- Frozen tensor equivalence: `{report.get('tensor_equivalence', {}).get('status')}`",
        "",
        "No training, tuning, target-support change, C0, Final Test, FULL, or paper_full action was executed.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _static_artifact(cache: M1DevelopmentBaseCache) -> dict:
    normalization = cache.static_normalization
    if normalization is None:
        raise ValueError("M1_B2R_STATIC_NORMALIZATION_MISSING")
    a2_result = _read_json(ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a2" / "AIR_SLOT_M1_V2_DATA_GATE_A2.json")
    references = a2_result["downstream"]["references"]
    payload = {
        "artifact_id": "M1_V2_STATIC_NORMALIZATION_B2",
        "schema_version": "M1_V2_STATIC_NORMALIZATION_B2_V1",
        "freeze_state": "FROZEN",
        "freeze_gate": "B2",
        "fitted_split": normalization.fitted_split,
        "fitting_unit": "UNIQUE_TRAIN_EPISODE_STATIC_CONTEXTS",
        "episode_level_fit": normalization.episode_level_fit,
        "episode_count": normalization.episode_count,
        "episode_ids_hash": normalization.episode_ids_hash,
        "ordered_feature_names": list(STATIC_FEATURE_NAMES),
        "numeric_feature_names": ["turnaround_reference_minutes", "taxi_reference_minutes"],
        "missing_mask_feature_names": ["turnaround_reference_minutes.missing_mask", "taxi_reference_minutes.missing_mask"],
        "values": normalization.model_dump(mode="json")["values"],
        "source_a2_cache_hash": A2_EXPECTED_CACHE_HASH,
        "source_candidate_cache_hash": cache.manifest["cache_hash"],
        "source_a2_reference_ids": {
            "turnaround": references["turnaround"]["new_reference_id"],
            "taxi": references["taxi"]["new_reference_id"],
        },
        "normalization_rule": {
            "observed": "z=(value-train_mean)/train_std; missing_mask=0",
            "missing": "numeric=0; missing_mask=1",
            "calibration_fit": False,
            "development_fit": False,
            "final_test_fit": False,
        },
    }
    payload["content_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_CONTENT_HASH"
    payload["content_hash"] = content_id(payload)
    return payload


def _frozen_schema(candidate_schema: dict, static_artifact: dict) -> dict:
    payload = {
        **candidate_schema,
        "schema_id": "M1_V2_FEATURE_SCHEMA_FROZEN_B2",
        "schema_version": "M1_V2_FEATURE_SCHEMA_FROZEN_B2_V1",
        "freeze_state": "FROZEN",
        "freeze_gate": "B2",
        "training_frozen": False,
        "source_candidate_schema_hash": candidate_schema["schema_hash"],
        "static_normalization_artifact": static_artifact["artifact_id"],
        "static_normalization_artifact_hash": static_artifact["content_hash"],
        "dynamic_feature_count": len(FEATURE_NAMES_V2),
        "static_feature_count": len(STATIC_FEATURE_NAMES),
        "total_feature_count": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES),
    }
    payload.pop("schema_hash", None)
    payload.pop("schema_hash_basis", None)
    payload["schema_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_SCHEMA_HASH"
    payload["schema_hash"] = content_id(payload)
    return payload


def _equivalence(left, right) -> dict:
    checks = {
        "dynamic_tensors": left.store.values_flat.equal(right.store.values_flat),
        "static_tensors": left.store.static_values.equal(right.store.static_values),
        "labels": all(left.store.labels[name].equal(right.store.labels[name]) for name in left.store.labels),
        "active_masks": all(left.store.active[name].equal(right.store.active[name]) for name in left.store.active),
        "episode_ids": left.store.episode_ids == right.store.episode_ids,
        "decision_node_ids": left.store.sample_decision_node_ids == right.store.sample_decision_node_ids,
        "lineage": left.store.static_context_lineages == right.store.static_context_lineages,
        "sample_episode_ids": left.store.sample_episode_ids == right.store.sample_episode_ids,
        "sample_splits": left.store.sample_splits == right.store.sample_splits,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", **checks}


def run(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    b1r_cache, b1r_manifest, b1r_report, b1r_schema = _load_b1r()
    schema = _candidate_schema(b1r_schema)
    old_names = tuple(b1r_manifest["feature_names"])
    keep_indices = [index for index, name in enumerate(old_names) if name not in REMOVED_SCHEDULE_DELTA]
    if tuple(name for name in old_names if name not in REMOVED_SCHEDULE_DELTA) != tuple(FEATURE_NAMES_V2):
        raise ValueError("M1_B2R_MODEL_SCHEMA_ORDER_MISMATCH")
    candidate_store = replace(b1r_cache.store, values_flat=b1r_cache.store.values_flat[:, keep_indices].contiguous())
    contract_hashes = dict(b1r_manifest["contract_hashes"])
    contract_hashes["feature_contract_hash"] = schema["schema_hash"]
    candidate_key = content_id({
        "scope": "FEATURE_GATE_B2R_CANDIDATE",
        "b1r_cache_hash": b1r_manifest["cache_hash"],
        "b1r_cache_key": b1r_manifest["cache_key"],
        "b1r_schema_hash": b1r_schema["schema_hash"],
        "candidate_schema_hash": schema["schema_hash"],
        "removed_features": list(REMOVED_SCHEDULE_DELTA),
    })
    candidate = M1DevelopmentBaseCache.from_store(
        store=candidate_store,
        normalization=b1r_cache.normalization,
        static_normalization=b1r_cache.static_normalization,
        audit={
            "scope": "FEATURE_GATE_B2R_CANDIDATE",
            "candidate_status": "NOT_TRAINING_FROZEN",
            "final_test_access_count": 0,
            "gate_b_entered": True,
            "gate_b2_feature_freeze": False,
            "source_b1r_cache_hash": b1r_manifest["cache_hash"],
            "source_b1r_schema_hash": b1r_schema["schema_hash"],
        },
        cache_key=candidate_key,
        source_manifest_hash=b1r_manifest["source_manifest_hash"],
        contract_hashes=contract_hashes,
        feature_names=FEATURE_NAMES_V2,
        static_feature_names=STATIC_FEATURE_NAMES,
        provenance={
            "a2_cache_hash": A2_EXPECTED_CACHE_HASH,
            "source_b1r_cache_hash": b1r_manifest["cache_hash"],
            "source_b1r_cache_key": b1r_manifest["cache_key"],
            "source_b1r_schema_hash": b1r_schema["schema_hash"],
            "removed_features": list(REMOVED_SCHEDULE_DELTA),
            "artifact_classification": "DEVELOPMENT_CANDIDATE",
        },
        feature_schema_hash=schema["schema_hash"],
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "M1_V2_FEATURE_GATE_B2R_CANDIDATE_CACHE.npz"
    manifest_path = output_dir / "M1_V2_FEATURE_GATE_B2R_CANDIDATE_CACHE_MANIFEST.json"
    saved_manifest = candidate.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(data_path, manifest_path, expected_cache_key=candidate_key)
    roundtrip = _roundtrip_equal(candidate, loaded)
    identity = _identity_equal(b1r_cache, candidate)
    profiles = feature_profiles(candidate)
    missing = missing_encoding_audit(candidate)
    redundancy = redundancy_audit(candidate)
    history = history_semantics()
    data_usage = run_data_usage_audit(output_dir / "data_usage_audit")
    ownership = build_gate_result(ROOT)
    labels_unchanged = identity["labels"] and identity["active"]
    static_unchanged = candidate.static_normalization.model_dump(mode="json") == b1r_cache.static_normalization.model_dump(mode="json")
    partial_cases = missing["static"]["partial_missing_cases"]
    missing_pass = (
        missing["all_checked_encodings_exact"]
        and missing["static"]["STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"] == 0
        and missing["static"]["PARTIAL_STATIC_OBSERVED_VALUE_LOST"] == 0
    )
    gate_checks = {
        "feature_counts": {"dynamic": len(FEATURE_NAMES_V2), "static": len(STATIC_FEATURE_NAMES), "total": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES)} == {"dynamic": 39, "static": 4, "total": 43},
        "candidate_ready": roundtrip["status"] == "PASS",
        "missing_invariants": missing_pass,
        "history_separation": history["FULL_PREFIX_HISTORY_FEATURE_COUNT"] == 0 and history["EXP1B_HISTORY_SEPARATION_STATUS"] == "CLEAN",
        "contract_structural_constants": redundancy["contract_structural_constant_count"] == 0,
        "contract_exact_duplicates": redundancy["contract_exact_duplicate_count"] == 0,
        "deterministic_contract_redundancy": len(redundancy["deterministic_complements"]) == 0 and len(redundancy["contract_affine_redundancy"]) == 0,
        "data_usage": data_usage["status"] == "DATA_USAGE_CONTRACT_AUDIT_PASS",
        "pre_ownership": ownership["PRE_OWNERSHIP_GATE"] == "PASS",
        "static_volume": ownership["STATIC_VOLUME_GATE"] == "PASS",
        "a2_provenance": b1r_manifest["provenance"]["a2_cache_hash"] == A2_EXPECTED_CACHE_HASH,
        "static_normalization_unchanged": static_unchanged and candidate.static_normalization.episode_count == 128,
        "labels_unchanged": labels_unchanged,
        "safety": saved_manifest["final_test_access_count"] == 0,
    }
    status = "FEATURE_GATE_B2R_PASS_CANDIDATE_READY_FOR_B2" if all(gate_checks.values()) else "FEATURE_GATE_B2R_CONTRACT_FAILURE"
    static_values = candidate.static_normalization.values
    report = {
        "schema_version": "AIR_SLOT_M1_V2_FEATURE_GATE_B2R_V1",
        "FEATURE_GATE_STATUS": status,
        "repository_head": _head(),
        "b2_failure_diagnosis": {"old_exact_duplicate_gate": "TRAIN_CURRENT_ROWS_ANY_EXACT_DUPLICATE_BLOCKED", "new_semantic_duplicate_gate": "CONTRACT_EXACT_DUPLICATE_AND_CONTRACT_STRUCTURAL_CONSTANT_ONLY"},
        "decisions": DECISIONS,
        "feature_counts": {"dynamic": len(FEATURE_NAMES_V2), "static": len(STATIC_FEATURE_NAMES), "total": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES)},
        "feature_schema": {"before_dynamic": len(old_names), "dynamic_candidate": len(FEATURE_NAMES_V2), "static_candidate": len(STATIC_FEATURE_NAMES), "total_candidate": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES), "b1r_schema_hash": b1r_schema["schema_hash"], "b2r_candidate_schema_hash": schema["schema_hash"], "schema_artifact": "M1_V2_FEATURE_SCHEMA_CANDIDATE_B2R.json"},
        "schedule_delta": {"fixed_grid_proof": "VALID_PREVIOUS_NODE_TRANSITION_ON_FIVE_MINUTE_GRID_HAS_FIXED_COUNTDOWN_DELTA", "numeric_removed": list(REMOVED_SCHEDULE_DELTA)[0], "mask_removed": list(REMOVED_SCHEDULE_DELTA)[1], "remaining_current_position": "schedule.signed_minutes_to_crs_departure", "present_in_candidate": any(name in FEATURE_NAMES_V2 for name in REMOVED_SCHEDULE_DELTA)},
        "redundancy": {"contract_exact_duplicate_count": redundancy["contract_exact_duplicate_count"], "contract_exact_duplicate_groups": redundancy["contract_exact_duplicate_groups"], "empirical_exact_duplicate_count": redundancy["empirical_exact_duplicate_count"], "empirical_exact_duplicate_groups": redundancy["empirical_exact_duplicate_groups"], "train_support_constant_count": redundancy["train_support_constant_count"], "train_support_constants": redundancy["train_support_constants"], "contract_structural_constant_count": redundancy["contract_structural_constant_count"], "contract_structural_constants": redundancy["contract_structural_constants"], "deterministic_complements": redundancy["deterministic_complements"], "contract_affine_redundancy": redundancy["contract_affine_redundancy"], "near_linear_pairs_report_only": redundancy["near_linear_pairs"], "cross_split_equality": redundancy["empirical_exact_duplicate_groups"]},
        "static": {"normalization_unchanged": static_unchanged, "fitting_unit": "UNIQUE_TRAIN_EPISODE_STATIC_CONTEXTS", "episode_count": candidate.static_normalization.episode_count, "turnaround": static_values["turnaround_reference_minutes"].model_dump(mode="json"), "taxi": static_values["taxi_reference_minutes"].model_dump(mode="json"), "partial_missing_preserved": partial_cases == 4, "partial_missing_cases": partial_cases},
        "missing_invariants": {"MISSING_NUMERIC_NOT_ZERO": missing["violation_counts"].get("MISSING_NUMERIC_NOT_ZERO", 0), "DERIVED_INVALID_NUMERIC_NOT_ZERO": missing["violation_counts"].get("DERIVED_INVALID_NUMERIC_NOT_ZERO", 0), "MISSING_MASK_VALUE_VIOLATIONS": missing["violation_counts"].get("MISSING_MASK_VALUE_VIOLATIONS", 0), "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK": missing["static"]["STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"], "PARTIAL_STATIC_OBSERVED_VALUE_LOST": missing["static"]["PARTIAL_STATIC_OBSERVED_VALUE_LOST"]},
        "exp1b": history,
        "labels": {"unchanged": labels_unchanged, "overflow": b1r_report["target"]["overflow"], "TARGET_SUPPORT_REVIEW_REQUIRED": "YES"},
        "cache": {"b1r_candidate_cache": b1r_manifest["cache_hash"], "candidate_cache": saved_manifest["cache_hash"], "candidate_cache_key": candidate_key, "schema_version": CACHE_SCHEMA_VERSION, "roundtrip": roundtrip, "a2_identity_labels_active_lineage_ids_unchanged": identity},
        "profiles": {"train": profiles["profiles"]["train"], "shift_report_only": shift_diagnostics(profiles["profiles"], list(FEATURE_NAMES_V2) + list(STATIC_FEATURE_NAMES))},
        "gate_checks": gate_checks,
        "validation_gates": {"data_usage_status": data_usage["status"], "data_usage_artifact_hash": data_usage["artifact_hash"], "PRE_OWNERSHIP_GATE": ownership["PRE_OWNERSHIP_GATE"], "STATIC_VOLUME_GATE": ownership["STATIC_VOLUME_GATE"], "ownership_findings": ownership["findings"]},
        "safety": {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "GATE_B_ENTERED": True, "GATE_B2_FEATURE_FREEZE": False, "M1_TARGET_SUPPORT_FROZEN": False, "HYPERPARAMETER_TUNING_AUTHORIZED": False},
    }
    report["artifact_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH"
    report_basis = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["artifact_hash"] = f"sha256:{sha256(report_basis.encode('utf-8')).hexdigest()}"
    _write_json(output_dir / "M1_V2_FEATURE_SCHEMA_CANDIDATE_B2R.json", schema)
    _write_json(output_dir / "FEATURE_REDUNDANCY_B2R.json", redundancy)
    _write_json(output_dir / "AIR_SLOT_M1_V2_FEATURE_GATE_B2R.json", report)
    _write_packet(output_dir / "M1_V2_FEATURE_GATE_B2R_PACKET.md", report)
    return report


def main() -> None:
    report = run()
    print(json.dumps({"FEATURE_GATE_STATUS": report["FEATURE_GATE_STATUS"], "artifact_hash": report["artifact_hash"], "candidate_schema_hash": report["feature_schema"]["b2r_candidate_schema_hash"], "candidate_cache_hash": report["cache"]["candidate_cache"], "feature_counts": report["feature_counts"], "safety": report["safety"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
