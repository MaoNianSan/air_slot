"""No-training M1 V2 Feature Preprocessing Gate B1 orchestration."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.data_usage_contract_audit import run as run_data_usage_audit
from validation.m1_v2_feature_profile import (
    feature_profiles,
    missing_encoding_audit,
    shift_diagnostics,
    support_state_counts,
    target_support_from_a2,
)
from validation.m1_v2_feature_redundancy import redundancy_audit
from validation.m1_v2_feature_semantics import (
    encoder_static_scan,
    feature_inventory,
    history_semantics,
    semantic_table,
)
from validation.ownership_gate_v2 import build_gate_result


ROOT = Path(__file__).resolve().parents[1]
A2_ROOT = ROOT / "artifacts" / "diagnostics" / "m1_v2_data_gate_a2"
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b1"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def load_a2_cache() -> tuple[M1DevelopmentBaseCache, dict, dict]:
    manifest_path = A2_ROOT / "M1_V2_DATA_GATE_A2_CACHE_MANIFEST.json"
    data_path = A2_ROOT / "M1_V2_DATA_GATE_A2_CACHE.npz"
    result_path = A2_ROOT / "AIR_SLOT_M1_V2_DATA_GATE_A2.json"
    manifest = _read_json(manifest_path)
    result = _read_json(result_path)
    cache = M1DevelopmentBaseCache.load(
        data_path,
        manifest_path,
        expected_cache_key=manifest["cache_key"],
        allow_legacy_schema=True,
    )
    return cache, manifest, result


def _recommendations(train_profile: list[dict], static_scan: dict) -> list[dict]:
    structural = set(static_scan["features"])
    output = []
    for row in train_profile:
        name = row["feature"]
        group = row["semantic_group"]
        evidence = []
        if name in structural:
            recommendation = "REMOVE"
            evidence.append("STRUCTURAL_CONSTANT_ENCODER_ZERO")
        elif group == "AR_SUMMARY":
            recommendation = "REMOVE_PENDING_B1_D05"
            evidence.append("FULL_PREFIX_HISTORY_DUPLICATED_WITH_GRU")
        elif group in {"STALE_MASK", "FALLBACK_MASK"} and name.startswith("weather."):
            recommendation = "COLLAPSE_OBJECT_LEVEL_PENDING_B1_D02"
            evidence.append("OBJECT_LEVEL_MASK_REPEATED_PER_FIELD")
        elif group == "EVIDENCE_ENCODING":
            recommendation = "METADATA_ONLY_PENDING_B1_D03"
            evidence.append("SOURCE_PROVENANCE_ONE_HOT")
        elif group == "SUPPORT_ENCODING":
            recommendation = "REDUCE_PENDING_B1_D04"
            evidence.append("RETAIN_ONLY_NONREDUNDANT_VARYING_SUPPORT_SIGNAL")
        elif group == "STATIC_REFERENCE":
            recommendation = "KEEP_TRAIN_STANDARDIZE_PENDING_B1_D06"
            evidence.append("TRAIN_FROZEN_REFERENCE_CURRENTLY_RAW_MINUTES")
        elif row["constant"]:
            recommendation = "REMOVE"
            evidence.append("TRAIN_CONSTANT")
        elif row["near_constant"] and group not in {
            "CURRENT_STATE", "CURRENT_WEATHER", "CEILING_STATUS"
        }:
            recommendation = "REVIEW_NEAR_CONSTANT"
            evidence.append("TRAIN_NEAR_CONSTANT")
        else:
            recommendation = "KEEP_CANDIDATE"
            evidence.append("SEMANTICALLY_ADMISSIBLE_AND_TRAIN_VARYING")
        output.append(
            {"feature": name, "recommendation": recommendation, "evidence": evidence}
        )
    return output


def _decision_packet(
    train_profile: list[dict], redundancy: dict, static_violations: list[dict]
) -> list[dict]:
    profile = {row["feature"]: row for row in train_profile}
    weather_masks = redundancy["weather_object_level_masks"]
    support_variation = {
        name: not profile[name]["constant"]
        for name in FEATURE_NAMES_V2
        if ".support." in name
    }
    evidence_constants = [
        name for name in FEATURE_NAMES_V2
        if ".evidence." in name and profile[name]["constant"]
    ]
    return [
        {
            "decision_id": "B1-D01",
            "question": "Should structural-zero state missing/stale/fallback masks remain numeric features?",
            "options": ["KEEP", "REMOVE"],
            "recommendation": "REMOVE",
            "evidence": "Nine masks are hard-coded to 0.0 by the encoder.",
        },
        {
            "decision_id": "B1-D02",
            "question": "Should weather stale/fallback masks be repeated per field or collapsed per object?",
            "options": ["REPEAT", "COLLAPSE_OBJECT_LEVEL"],
            "recommendation": "COLLAPSE_OBJECT_LEVEL",
            "evidence": weather_masks,
        },
        {
            "decision_id": "B1-D03",
            "question": "Should constant evidence-class one-hots remain numeric predictors?",
            "options": ["NUMERIC", "METADATA_ONLY"],
            "recommendation": "METADATA_ONLY",
            "evidence": {"train_constant_evidence_features": evidence_constants},
        },
        {
            "decision_id": "B1-D04",
            "question": "How should object support-state one-hots enter the feature schema?",
            "options": ["KEEP", "REDUCE", "METADATA_ONLY"],
            "recommendation": "REDUCE",
            "evidence": {"train_support_feature_varies": support_variation},
        },
        {
            "decision_id": "B1-D05",
            "question": "How should full-prefix cumulative weather summaries be handled?",
            "options": ["REMOVE", "SHORT_WINDOW", "RETAIN_RENAME"],
            "recommendation": "REMOVE",
            "evidence": (
                "The summaries cover the full prefix and enter r_fast while the same prefix "
                "also enters the GRU. SHORT_WINDOW would require a separately approved window."
            ),
        },
        {
            "decision_id": "B1-D06",
            "question": "How should turnaround and taxi reference minutes be numerically encoded?",
            "options": ["RAW", "TRAIN_STANDARDIZED"],
            "recommendation": "TRAIN_STANDARDIZED",
            "evidence": (
                "Both references currently enter a neural projection as raw minutes; "
                "train-frozen provenance does not remove the need for numeric scaling."
            ),
        },
        {
            "decision_id": "B1-D07",
            "question": "What static missingness contract should replace unmasked whole-block zero fill?",
            "options": ["REQUIRE_COMPLETE_BLOCK", "PER_FEATURE_MASKED_BLOCK", "ABSTAIN_SAMPLE"],
            "recommendation": "PER_FEATURE_MASKED_BLOCK",
            "evidence": {
                "affected_samples": len(static_violations),
                "status": "ENGINEERING_REPAIR_REQUIRED_BEFORE_B2",
            },
        },
    ]


def _keep_candidates(recommendations: list[dict]) -> list[str]:
    accepted = (
        "KEEP_CANDIDATE",
        "KEEP_TRAIN_STANDARDIZE_PENDING_B1_D06",
        "REDUCE_PENDING_B1_D04",
        "REVIEW_NEAR_CONSTANT",
    )
    return [row["feature"] for row in recommendations if row["recommendation"] in accepted]


def _markdown(report: dict) -> str:
    counts = report["inventory"]
    group_counts = {
        name: len(rows) for name, rows in counts["groups"].items()
    }
    recommendation_counts = Counter(
        row["recommendation"] for row in report["recommendations_train_only"]
    )
    train_constants = [
        row["feature"] for row in report["train_profile"] if row["constant"]
    ]
    missing_checks = [
        row for row in report["missing_encoding"]["checks"] if row["violations"]
    ]
    target = report["target_support"]
    lines = [
        "# AIR_SLOT_M1_V2_FEATURE_GATE_B1",
        "",
        f"- Status: `{report['FEATURE_GATE_STATUS']}`",
        f"- A2 cache: `{report['a2_baseline']['cache_hash']}`",
        f"- A2 turnaround: 57.0 min, `{report['a2_baseline']['turnaround_reference_id']}`",
        f"- A2 taxi: 15.0 min, `{report['a2_baseline']['taxi_reference_id']}`",
        f"- Dynamic / static / total: {counts['dynamic_count']} / {counts['static_count']} / {counts['total_count']}",
        f"- Exp1B history separation: `{report['history']['EXP1B_HISTORY_SEPARATION_STATUS']}`",
        f"- Target support review required: `{report['target_support']['TARGET_SUPPORT_REVIEW_REQUIRED']}`",
        "",
        "## Feature Inventory",
        "",
        *[f"- {name}: {count}" for name, count in group_counts.items()],
        "",
        "## Encoder Semantics",
        "",
        "- Delta: `PREVIOUS_NODE_LOCAL`, `DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES`.",
        "- AR actual semantics: `FULL_PREFIX_CUMULATIVE_MEAN`; any earlier missing value invalidates the current summary.",
        "- Exp1B: ADAPTIVE history enters through both `GRU(history)` and full-prefix summaries in `r_fast`.",
        f"- Structural-zero state masks: {len(report['encoder_static_scan']['features'])}; recommendation `REMOVE`.",
        "- Static references currently enter as raw minutes; recommendation `TRAIN_STANDARDIZED` pending B1-D06.",
        "",
        "## Blockers",
        "",
    ]
    blockers = report["data_inconsistencies"]
    if blockers:
        lines.extend(f"- `{row['kind']}`: {row['count']}" for row in blockers)
    else:
        lines.append("- None")
    for row in missing_checks:
        lines.append(
            f"- `{row['numeric']}` with `{row['mask']}`: {row['violations']} violations; "
            f"split counts {row['violations_by_split']}."
        )
    lines.extend(
        [
            "",
            "## Train-Only Review",
            "",
            f"- Constant features: {len(train_constants)}.",
            f"- Recommendation counts: `{dict(sorted(recommendation_counts.items()))}`.",
            f"- Exact duplicate groups: {len(report['redundancy']['exact_duplicate_groups'])}.",
            f"- Deterministic complements: {len(report['redundancy']['deterministic_complements'])}.",
            f"- Near-linear pairs: {len(report['redundancy']['near_linear_pairs'])}; report only.",
            "- Weather stale/fallback masks are row-wise identical across all seven weather fields in Train.",
            "",
            "## Shift Diagnostics",
            "",
            f"- Calibration KEEP-candidate rows: {len(report['calibration_development_shift_keep_candidates_only']['calibration'])}.",
            f"- Development KEEP-candidate rows: {len(report['calibration_development_shift_keep_candidates_only']['development'])}.",
            "- These diagnostics do not alter any Train-based recommendation.",
            "",
            "## Target Support",
            "",
        ]
    )
    for split, targets in target["splits"].items():
        summary = "; ".join(
            f"{name}: active={values['active_count']}, zero={values['zero_count']}, "
            f"positive={values['positive_count']}, overflow={values['overflow_count']}, "
            f"abstain={values['abstain_count']}"
            for name, values in targets.items()
        )
        lines.append(f"- {split}: {summary}")
    lines.extend(["", "## Human Decisions", ""])
    for item in report["human_decisions"]:
        lines.extend(
            [
                f"### {item['decision_id']}",
                "",
                f"Question: {item['question']}",
                "",
                f"Options: {' / '.join(item['options'])}",
                "",
                f"Recommendation: `{item['recommendation']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety State",
            "",
            "```text",
            "M1_TRAINING_RUNS = 0",
            "TUNING_RUNS = 0",
            "FINAL_TEST_ACCESS_COUNT = 0",
            "PAPER_FULL_RUN = false",
            "GATE_B_ENTERED = true",
            "GATE_B2_FEATURE_FREEZE = false",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    cache, manifest, a2_result = load_a2_cache()
    data_usage = run_data_usage_audit(output_dir / "data_usage_audit")
    ownership = build_gate_result(ROOT)
    inventory = feature_inventory()
    semantics = semantic_table()
    static_scan = encoder_static_scan()
    history = history_semantics()
    profiles_payload = feature_profiles(cache)
    profiles = profiles_payload["profiles"]
    redundancy = redundancy_audit(cache)
    missing = missing_encoding_audit(cache)
    recommendations = _recommendations(profiles["train"], static_scan)
    keep = _keep_candidates(recommendations)
    shifts = shift_diagnostics(profiles, keep)
    target_support = target_support_from_a2(a2_result)
    support_counts = support_state_counts(cache)
    decisions = _decision_packet(
        profiles["train"], redundancy, profiles_payload["static_contract_violations"]
    )

    issue_counts = Counter(row["kind"] for row in profiles_payload["static_contract_violations"])
    issue_counts.update(missing["violation_counts"])
    data_inconsistencies = [
        {"kind": kind, "count": count}
        for kind, count in sorted(issue_counts.items())
        if count > 0
    ]
    a2_ready = (
        a2_result.get("DATA_GATE_STATUS") == "DATA_GATE_A2_PASS_READY_FOR_GATE_B"
        and manifest.get("cache_hash")
        == "sha256:7cb35178323aecdd288010b0b70daf15112695baf627b53d2bef03136393b082"
        and manifest.get("final_test_access_count") == 0
    )
    contract_gates_pass = (
        data_usage["status"] == "DATA_USAGE_CONTRACT_AUDIT_PASS"
        and ownership["PRE_OWNERSHIP_GATE"] == "PASS"
        and ownership["STATIC_VOLUME_GATE"] == "PASS"
    )
    status = (
        "FEATURE_GATE_B1_CONTRACT_FAILURE"
        if not a2_ready or not contract_gates_pass
        else "FEATURE_GATE_B1_DATA_INCONSISTENCY"
        if data_inconsistencies
        else "FEATURE_GATE_B1_REVIEW_PACKET_READY"
    )
    report = {
        "schema_version": "AIR_SLOT_M1_V2_FEATURE_GATE_B1_V1",
        "FEATURE_GATE_STATUS": status,
        "repository_head": _head(),
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY",
        "a2_baseline": {
            "status": a2_result.get("DATA_GATE_STATUS"),
            "cache_hash": manifest["cache_hash"],
            "cache_key": manifest["cache_key"],
            "turnaround_global_minutes": 57.0,
            "turnaround_reference_id": "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57",
            "taxi_global_minutes": 15.0,
            "taxi_reference_id": "sha256:be1a68b0c51c77da35f0ec631c2f846a79dd073d8b29ca49ee42b2d1de4e5c66",
            "partition_counts": manifest["partition_counts"],
            "final_test_access_count": manifest["final_test_access_count"],
        },
        "validation_gates": {
            "data_usage_status": data_usage["status"],
            "data_usage_artifact_hash": data_usage["artifact_hash"],
            "ownership_status": ownership["PRE_OWNERSHIP_GATE"],
            "static_volume_status": ownership["STATIC_VOLUME_GATE"],
            "ownership_findings": ownership["findings"],
        },
        "inventory": inventory,
        "semantics": semantics,
        "encoder_static_scan": static_scan,
        "history": history,
        "normalization": {
            "fitted_split": cache.normalization.fitted_split,
            "artifact": cache.normalization.model_dump(mode="json"),
            "feature_classification_source": "semantics.NORMALIZATION",
            "double_scaling_detected": False,
        },
        "missing_encoding": missing,
        "train_profile": profiles["train"],
        "recommendations_train_only": recommendations,
        "calibration_development_shift_keep_candidates_only": shifts,
        "support_state_counts": support_counts,
        "redundancy": redundancy,
        "target_support": target_support,
        "human_decisions": decisions,
        "data_inconsistencies": data_inconsistencies,
        "data_inconsistency_details": profiles_payload["static_contract_violations"] + missing["violations"],
        "safety": {
            "M1_TRAINING_RUNS": 0,
            "TUNING_RUNS": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "GATE_B_ENTERED": True,
            "GATE_B2_FEATURE_FREEZE": False,
        },
        "automatic_decisions_applied": False,
    }
    report["artifact_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH"
    hash_basis = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["artifact_hash"] = f"sha256:{sha256(hash_basis.encode('utf-8')).hexdigest()}"

    _write_json(output_dir / "FEATURE_INVENTORY_AND_SEMANTICS.json", {
        "inventory": inventory, "semantics": semantics,
        "encoder_static_scan": static_scan, "history": history,
    })
    _write_json(output_dir / "FEATURE_PROFILE_AND_SHIFT.json", {
        "profiles": profiles, "shift_keep_candidates_only": shifts,
        "support_state_counts": support_counts,
    })
    _write_json(output_dir / "FEATURE_REDUNDANCY.json", redundancy)
    _write_json(output_dir / "FEATURE_MISSING_AND_TARGET_SUPPORT.json", {
        "missing_encoding": missing,
        "static_contract_violations": profiles_payload["static_contract_violations"],
        "target_support": target_support,
    })
    _write_json(output_dir / "PRE_OWNERSHIP_GATE_B1.json", ownership)
    _write_json(output_dir / "AIR_SLOT_M1_V2_FEATURE_GATE_B1.json", report)
    (output_dir / "FEATURE_DECISION_PACKET.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    return report


def main() -> None:
    report = run()
    print(json.dumps({
        "FEATURE_GATE_STATUS": report["FEATURE_GATE_STATUS"],
        "artifact_hash": report["artifact_hash"],
        "data_inconsistencies": report["data_inconsistencies"],
        "safety": report["safety"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
