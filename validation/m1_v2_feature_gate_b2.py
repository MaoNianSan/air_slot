"""Feature Contract Freeze Gate B2 for the approved B2R candidate."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from model.common.identity import content_id
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.data_usage_contract_audit import run as run_data_usage_audit
from validation.m1_v2_feature_gate_b1r import (
    A2_EXPECTED_CACHE_HASH,
    A2_ROOT,
)
from validation.m1_v2_feature_gate_b2r import (
    DECISIONS as B2R_DECISIONS,
    DEFAULT_OUTPUT as B2R_OUTPUT,
)
from validation.m1_v2_feature_profile import missing_encoding_audit
from validation.m1_v2_feature_redundancy import redundancy_audit
from validation.m1_v2_feature_semantics import history_semantics
from validation.ownership_gate_v2 import build_gate_result

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b2"
DECISIONS = {
    "B1-D01": "REMOVE",
    "B1-D02": "COLLAPSE_OBJECT_LEVEL",
    "B1-D03": "METADATA_ONLY",
    "B1-D04": "REDUCE",
    "B1-D05": "REMOVE",
    "B1-D06": "TRAIN_STANDARDIZED",
    "B1-D07": "PER_FEATURE_MASKED_BLOCK",
    **B2R_DECISIONS,
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
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _load_candidate() -> tuple[M1DevelopmentBaseCache, dict, dict, dict]:
    manifest_path = B2R_OUTPUT / "M1_V2_FEATURE_GATE_B2R_CANDIDATE_CACHE_MANIFEST.json"
    data_path = B2R_OUTPUT / "M1_V2_FEATURE_GATE_B2R_CANDIDATE_CACHE.npz"
    report_path = B2R_OUTPUT / "AIR_SLOT_M1_V2_FEATURE_GATE_B2R.json"
    schema_path = B2R_OUTPUT / "M1_V2_FEATURE_SCHEMA_CANDIDATE_B2R.json"
    manifest = _read_json(manifest_path)
    report = _read_json(report_path)
    schema = _read_json(schema_path)
    cache = M1DevelopmentBaseCache.load(
        data_path, manifest_path, expected_cache_key=manifest["cache_key"]
    )
    if manifest["cache_hash"] != report["cache"]["candidate_cache"]:
        raise ValueError("M1_B2_CANDIDATE_CACHE_REPORT_HASH_MISMATCH")
    if report["FEATURE_GATE_STATUS"] not in {
        "FEATURE_GATE_B2R_PASS_CANDIDATE_READY_FOR_B2",
        "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT",
    }:
        raise ValueError("M1_B2_B2R_NOT_READY")
    if schema["schema_hash"] != report["feature_schema"]["b2r_candidate_schema_hash"]:
        raise ValueError("M1_B2_CANDIDATE_SCHEMA_HASH_MISMATCH")
    if tuple(manifest["feature_names"]) != FEATURE_NAMES_V2:
        raise ValueError("M1_B2_DYNAMIC_ORDER_MISMATCH")
    if tuple(manifest["static_feature_names"]) != STATIC_FEATURE_NAMES:
        raise ValueError("M1_B2_STATIC_ORDER_MISMATCH")
    return cache, manifest, report, schema


def _canonical_feature_content(schema: dict) -> dict:
    return {
        "ordered_dynamic_features": schema["ordered_dynamic_features"],
        "ordered_static_features": schema["ordered_static_features"],
        "features": schema["features"],
        "groups": schema["groups"],
        "removed": schema["removed"],
        "metadata_retained": schema["metadata_retained"],
        "applied_decisions": schema["applied_decisions"],
    }


def _static_artifact(cache: M1DevelopmentBaseCache, report: dict) -> dict:
    normalization = cache.static_normalization
    if normalization is None:
        raise ValueError("M1_B2_STATIC_NORMALIZATION_MISSING")
    a2_result = _read_json(A2_ROOT / "AIR_SLOT_M1_V2_DATA_GATE_A2.json")
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
        "numeric_feature_names": [
            "turnaround_reference_minutes",
            "taxi_reference_minutes",
        ],
        "missing_mask_feature_names": [
            "turnaround_reference_minutes.missing_mask",
            "taxi_reference_minutes.missing_mask",
        ],
        "values": normalization.model_dump(mode="json")["values"],
        "source_a2_cache_hash": A2_EXPECTED_CACHE_HASH,
        "source_candidate_cache_hash": report["cache"]["candidate_cache"],
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
        "source_candidate_static_normalization_hash": content_id(
            normalization.model_dump(mode="json")
        ),
    }
    payload["content_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_CONTENT_HASH"
    payload["content_hash"] = content_id(payload)
    return payload


def _frozen_schema(schema: dict, static_artifact: dict) -> dict:
    content = _canonical_feature_content(schema)
    payload = {
        **content,
        "schema_id": "M1_V2_FEATURE_SCHEMA_FROZEN_B2",
        "schema_version": "M1_V2_FEATURE_SCHEMA_FROZEN_B2_V1",
        "freeze_state": "FROZEN",
        "freeze_gate": "B2",
        "training_frozen": False,
        "source_candidate_schema_hash": schema["schema_hash"],
        "source_candidate_content_hash": content_id(content),
        "static_normalization_artifact": static_artifact["artifact_id"],
        "static_normalization_artifact_hash": static_artifact["content_hash"],
        "human_decisions": DECISIONS,
        "dynamic_feature_count": len(FEATURE_NAMES_V2),
        "static_feature_count": len(STATIC_FEATURE_NAMES),
        "total_feature_count": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES),
    }
    payload["schema_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_SCHEMA_HASH"
    payload["schema_hash"] = content_id(payload)
    return payload


def _equivalence(left, right) -> dict[str, bool]:
    checks = {
        "dynamic_tensors": left.store.values_flat.equal(right.store.values_flat),
        "static_tensors": left.store.static_values.equal(right.store.static_values),
        "labels": all(
            left.store.labels[name].equal(right.store.labels[name])
            for name in left.store.labels
        ),
        "active_masks": all(
            left.store.active[name].equal(right.store.active[name])
            for name in left.store.active
        ),
        "episode_ids": left.store.episode_ids == right.store.episode_ids,
        "decision_node_ids": left.store.sample_decision_node_ids
        == right.store.sample_decision_node_ids,
        "lineage": left.store.static_context_lineages
        == right.store.static_context_lineages,
        "sample_episode_ids": left.store.sample_episode_ids
        == right.store.sample_episode_ids,
        "sample_splits": left.store.sample_splits == right.store.sample_splits,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", **checks}


def _write_packet(path: Path, report: dict) -> None:
    lines = [
        "# M1 V2 Feature Gate B2 Freeze Packet",
        "",
        f"- Status: `{report['FEATURE_GATE_STATUS']}`",
        f"- Dynamic/static/total: {report['feature_counts']['dynamic']} / "
        f"{report['feature_counts']['static']} / {report['feature_counts']['total']}",
        f"- Candidate schema hash: `{report['candidate_schema_hash']}`",
        f"- Contract exact duplicates: `{report['redundancy']['contract_exact_duplicate_count']}`",
        f"- Empirical exact duplicates: `{report['redundancy']['empirical_exact_duplicate_count']}`",
        f"- Train support constants: `{report['redundancy']['train_support_constant_count']}`",
        f"- Deterministic complements: `{report['redundancy']['deterministic_complement_count']}`",
        "",
    ]
    if (
        report["FEATURE_GATE_STATUS"]
        == "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"
    ):
        lines.extend(
            [
                f"- Frozen schema hash: `{report['frozen_schema_hash']}`",
                f"- Frozen cache key: `{report['frozen_cache_key']}`",
                "- Feature content equivalence: `PASS`",
                "- Target support remains the next gate: `M1_TARGET_SUPPORT_GATE_C0`",
            ]
        )
    else:
        lines.extend(
            [
                "- Frozen schema: `NOT_CREATED`",
                "- Frozen cache: `NOT_CREATED`",
                "- Freeze is blocked; no feature was added, removed, reordered, or redefined.",
            ]
        )
    lines.extend(
        [
            "",
            "Training, tuning, Final Test, FULL, paper_full, and C0 were not executed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _clear_freeze_outputs(output_dir: Path) -> None:
    for name in (
        "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json",
        "M1_V2_STATIC_NORMALIZATION_B2.json",
        "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz",
        "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
    ):
        (output_dir / name).unlink(missing_ok=True)


def _link_b2r_freeze(report: dict, output_dir: Path) -> None:
    path = B2R_OUTPUT / "AIR_SLOT_M1_V2_FEATURE_GATE_B2R.json"
    b2r = _read_json(path)
    b2r["FEATURE_GATE_STATUS"] = "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"
    b2r["freeze"] = {
        "status": report["FEATURE_GATE_STATUS"],
        "frozen_schema_hash": report.get("frozen_schema_hash"),
        "frozen_cache_hash": report["cache"].get("frozen"),
        "frozen_cache_key": report.get("frozen_cache_key"),
        "tensor_equivalence": report["cache"]["tensor_equivalence"],
        "GATE_B2_FEATURE_FREEZE": report["safety"]["GATE_B2_FEATURE_FREEZE"],
        "M1_TARGET_SUPPORT_FROZEN": report["safety"]["M1_TARGET_SUPPORT_FROZEN"],
        "HYPERPARAMETER_TUNING_AUTHORIZED": report["safety"][
            "HYPERPARAMETER_TUNING_AUTHORIZED"
        ],
    }
    b2r["safety"]["GATE_B2_FEATURE_FREEZE"] = True
    b2r["artifact_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH"
    basis = json.dumps(
        {key: value for key, value in b2r.items() if key != "artifact_hash"},
        sort_keys=True,
        separators=(",", ":"),
    )
    b2r["artifact_hash"] = f"sha256:{sha256(basis.encode('utf-8')).hexdigest()}"
    _write_json(path, b2r)
    from validation.m1_v2_feature_gate_b2r import _write_packet as write_b2r_packet

    write_b2r_packet(B2R_OUTPUT / "M1_V2_FEATURE_GATE_B2R_PACKET.md", b2r)


def run(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_freeze_outputs(output_dir)
    candidate, candidate_manifest, b2r, candidate_schema = _load_candidate()
    static_artifact = _static_artifact(candidate, b2r)
    redundancy = redundancy_audit(candidate)
    missing = missing_encoding_audit(candidate)
    history = history_semantics()
    data_usage = run_data_usage_audit(output_dir / "data_usage_audit")
    ownership = build_gate_result(ROOT)
    exact_groups = redundancy["exact_duplicate_groups"]
    complement_groups = redundancy["deterministic_complements"]
    structural_constants = redundancy["contract_structural_constants"]
    feature_counts = {
        "dynamic": len(FEATURE_NAMES_V2),
        "static": len(STATIC_FEATURE_NAMES),
        "total": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES),
    }
    gate_checks = {
        "feature_counts": feature_counts == {"dynamic": 39, "static": 4, "total": 43},
        "candidate_ready": b2r["FEATURE_GATE_STATUS"]
        in {
            "FEATURE_GATE_B2R_PASS_CANDIDATE_READY_FOR_B2",
            "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT",
        },
        "missing_invariants": all(
            missing["violation_counts"].get(name, 0) == 0
            for name in (
                "MISSING_NUMERIC_NOT_ZERO",
                "DERIVED_INVALID_NUMERIC_NOT_ZERO",
                "MISSING_MASK_VALUE_VIOLATIONS",
            )
        )
        and missing["static"]["STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"] == 0
        and missing["static"]["PARTIAL_STATIC_OBSERVED_VALUE_LOST"] == 0,
        "history_separation": (
            history["FULL_PREFIX_HISTORY_FEATURE_COUNT"] == 0
            and history["EXP1B_HISTORY_SEPARATION_STATUS"] == "CLEAN"
        ),
        "structural_constants": redundancy["contract_structural_constant_count"] == 0,
        "contract_exact_duplicates": redundancy["contract_exact_duplicate_count"] == 0,
        "deterministic_complements": len(complement_groups) == 0
        and len(redundancy["contract_affine_redundancy"]) == 0,
        "data_usage": data_usage["status"] == "DATA_USAGE_CONTRACT_AUDIT_PASS",
        "pre_ownership": ownership["PRE_OWNERSHIP_GATE"] == "PASS",
        "static_volume": ownership["STATIC_VOLUME_GATE"] == "PASS",
        "a2_provenance": candidate_manifest["provenance"]["a2_cache_hash"]
        == A2_EXPECTED_CACHE_HASH,
        "safety": candidate_manifest["final_test_access_count"] == 0,
    }
    freeze_allowed = all(gate_checks.values())
    frozen_schema = None
    frozen_cache = None
    frozen_cache_manifest = None
    equivalence = {"status": "NOT_CREATED"}
    frozen_schema_path = output_dir / "M1_V2_FEATURE_SCHEMA_FROZEN_B2.json"
    frozen_data_path = output_dir / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
    frozen_manifest_path = output_dir / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    if freeze_allowed:
        frozen_schema = _frozen_schema(candidate_schema, static_artifact)
        frozen_contracts = dict(candidate_manifest["contract_hashes"])
        frozen_contracts["feature_contract_hash"] = frozen_schema["schema_hash"]
        frozen_key = content_id(
            {
                "scope": "FEATURE_GATE_B2_FROZEN_DEVELOPMENT",
                "candidate_cache_hash": candidate_manifest["cache_hash"],
                "candidate_cache_key": candidate_manifest["cache_key"],
                "frozen_schema_hash": frozen_schema["schema_hash"],
                "static_artifact_hash": static_artifact["content_hash"],
            }
        )
        frozen_cache = M1DevelopmentBaseCache.from_store(
            store=candidate.store,
            normalization=candidate.normalization,
            static_normalization=candidate.static_normalization,
            audit={
                "scope": "FEATURE_GATE_B2_FROZEN_DEVELOPMENT",
                "candidate_status": "FROZEN_B2",
                "freeze_state": "FROZEN",
                "freeze_gate": "B2",
                "final_test_access_count": 0,
                "gate_b_entered": True,
                "gate_b2_feature_freeze": True,
                "m1_target_support_frozen": False,
                "hyperparameter_tuning_authorized": False,
            },
            cache_key=frozen_key,
            source_manifest_hash=candidate_manifest["source_manifest_hash"],
            contract_hashes=frozen_contracts,
            feature_names=FEATURE_NAMES_V2,
            static_feature_names=STATIC_FEATURE_NAMES,
            provenance={
                "source_candidate_cache_hash": candidate_manifest["cache_hash"],
                "source_candidate_cache_key": candidate_manifest["cache_key"],
                "source_candidate_schema_hash": candidate_schema["schema_hash"],
                "frozen_schema_hash": frozen_schema["schema_hash"],
                "static_normalization_artifact_hash": static_artifact["content_hash"],
                "artifact_classification": "DEVELOPMENT_ARTIFACT",
                "final_test": "NOT_FINAL_TEST",
                "production": "NOT_PRODUCTION_FINAL",
            },
            feature_schema_hash=frozen_schema["schema_hash"],
        )
        frozen_cache_manifest = frozen_cache.save(
            frozen_data_path, frozen_manifest_path
        )
        loaded_frozen = M1DevelopmentBaseCache.load(
            frozen_data_path, frozen_manifest_path, expected_cache_key=frozen_key
        )
        equivalence = _equivalence(candidate, loaded_frozen)
        if equivalence["status"] == "PASS":
            _write_json(
                output_dir / "M1_V2_STATIC_NORMALIZATION_B2.json", static_artifact
            )
            _write_json(frozen_schema_path, frozen_schema)
        else:
            frozen_data_path.unlink(missing_ok=True)
            frozen_manifest_path.unlink(missing_ok=True)
            frozen_cache_manifest = None
    freeze_complete = freeze_allowed and equivalence["status"] == "PASS"
    status = (
        "FEATURE_GATE_B2_PASS_TARGET_SUPPORT_REVIEW_NEXT"
        if freeze_complete
        else "FEATURE_GATE_B2_CONTRACT_FAILURE"
    )
    report = {
        "schema_version": "AIR_SLOT_M1_V2_FEATURE_GATE_B2_V1",
        "FEATURE_GATE_STATUS": status,
        "repository_head": _head(),
        "candidate_schema_hash": candidate_schema["schema_hash"],
        "candidate_cache_hash": candidate_manifest["cache_hash"],
        "frozen_schema_hash": (
            frozen_schema["schema_hash"] if freeze_complete else None
        ),
        "frozen_cache_key": (
            frozen_cache_manifest["cache_key"] if freeze_complete else None
        ),
        "feature_counts": feature_counts,
        "decisions": DECISIONS,
        "information_architecture": {
            "r_fast": "CURRENT_STATE + CURRENT_SCHEDULE + CURRENT_WEATHER + PREVIOUS_NODE_LOCAL_DELTA + VALIDITY + OBJECT_WEATHER_QUALITY_SUPPORT",
            "h": "GRU_FULL_CAUSAL_HISTORY",
            "c_static": "TRAIN_STANDARDIZED_REFERENCE_VALUES_PLUS_PER_FEATURE_MISSING_MASKS",
            "FULL_PREFIX_HISTORY_FEATURE_COUNT": history[
                "FULL_PREFIX_HISTORY_FEATURE_COUNT"
            ],
            "EXP1B_HISTORY_SEPARATION_STATUS": history[
                "EXP1B_HISTORY_SEPARATION_STATUS"
            ],
        },
        "static_normalization": {
            "artifact_id": static_artifact["artifact_id"],
            "artifact_hash": static_artifact["content_hash"],
            "fit_split": static_artifact["fitted_split"],
            "fitting_unit": static_artifact["fitting_unit"],
            "episode_count": static_artifact["episode_count"],
            "turnaround": static_artifact["values"]["turnaround_reference_minutes"],
            "taxi": static_artifact["values"]["taxi_reference_minutes"],
            "source_a2_reference_ids": static_artifact["source_a2_reference_ids"],
        },
        "cache": {
            "candidate": candidate_manifest["cache_hash"],
            "frozen": (
                None
                if frozen_cache_manifest is None
                else frozen_cache_manifest["cache_hash"]
            ),
            "frozen_cache_key": (
                None
                if frozen_cache_manifest is None
                else frozen_cache_manifest["cache_key"]
            ),
            "schema_version": candidate_manifest["cache_schema_version"],
            "candidate_status": candidate_manifest["candidate_status"],
            "frozen_status": (
                None
                if frozen_cache_manifest is None
                else frozen_cache_manifest["candidate_status"]
            ),
            "tensor_equivalence": equivalence,
        },
        "redundancy": {
            "contract_structural_constants": structural_constants,
            "contract_structural_constant_count": redundancy[
                "contract_structural_constant_count"
            ],
            "contract_exact_duplicate_count": redundancy[
                "contract_exact_duplicate_count"
            ],
            "contract_exact_duplicate_groups": redundancy[
                "contract_exact_duplicate_groups"
            ],
            "empirical_exact_duplicate_count": redundancy[
                "empirical_exact_duplicate_count"
            ],
            "empirical_exact_duplicate_groups": redundancy[
                "empirical_exact_duplicate_groups"
            ],
            "train_support_constant_count": redundancy["train_support_constant_count"],
            "train_support_constants": redundancy["train_support_constants"],
            "exact_duplicate_count": len(exact_groups),
            "exact_duplicate_groups": exact_groups,
            "deterministic_complement_count": len(complement_groups),
            "deterministic_complements": complement_groups,
            "contract_affine_redundancy": redundancy["contract_affine_redundancy"],
            "near_linear_pairs_report_only": redundancy["near_linear_pairs"],
        },
        "missing_invariants": {
            "MISSING_NUMERIC_NOT_ZERO": missing["violation_counts"].get(
                "MISSING_NUMERIC_NOT_ZERO", 0
            ),
            "DERIVED_INVALID_NUMERIC_NOT_ZERO": missing["violation_counts"].get(
                "DERIVED_INVALID_NUMERIC_NOT_ZERO", 0
            ),
            "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK": missing["static"][
                "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"
            ],
            "PARTIAL_STATIC_OBSERVED_VALUE_LOST": missing["static"][
                "PARTIAL_STATIC_OBSERVED_VALUE_LOST"
            ],
            "MISSING_MASK_VALUE_VIOLATIONS": missing["violation_counts"].get(
                "MISSING_MASK_VALUE_VIOLATIONS", 0
            ),
        },
        "labels": {
            "unchanged": b2r["labels"]["unchanged"],
            "overflow": b2r["labels"]["overflow"],
            "TARGET_SUPPORT_REVIEW_REQUIRED": "YES",
        },
        "gate_checks": gate_checks,
        "validation_gates": {
            "data_usage_status": data_usage["status"],
            "data_usage_artifact_hash": data_usage["artifact_hash"],
            "PRE_OWNERSHIP_GATE": ownership["PRE_OWNERSHIP_GATE"],
            "STATIC_VOLUME_GATE": ownership["STATIC_VOLUME_GATE"],
            "ownership_findings": ownership["findings"],
        },
        "safety": {
            **SAFETY_BASE,
            "GATE_B2_FEATURE_FREEZE": freeze_complete,
        },
    }
    report["artifact_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH"
    report_basis = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["artifact_hash"] = (
        f"sha256:{sha256(report_basis.encode('utf-8')).hexdigest()}"
    )
    _write_json(output_dir / "AIR_SLOT_M1_V2_FEATURE_GATE_B2.json", report)
    _write_json(output_dir / "B2_GATE_CHECKS.json", gate_checks)
    _write_packet(output_dir / "M1_V2_FEATURE_GATE_B2_FREEZE_PACKET.md", report)
    if freeze_complete:
        _link_b2r_freeze(report, output_dir)
    return report


def main() -> None:
    report = run()
    print(
        json.dumps(
            {
                "FEATURE_GATE_STATUS": report["FEATURE_GATE_STATUS"],
                "artifact_hash": report["artifact_hash"],
                "contract_exact_duplicate_count": report["redundancy"][
                    "contract_exact_duplicate_count"
                ],
                "empirical_exact_duplicate_count": report["redundancy"][
                    "empirical_exact_duplicate_count"
                ],
                "frozen_schema_hash": report.get("frozen_schema_hash"),
                "safety": report["safety"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
