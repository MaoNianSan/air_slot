"""Apply approved B1 decisions and materialize a no-training candidate cache."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

import torch

from model.common.identity import content_id
from model.M1.cache import (
    CACHE_SCHEMA_VERSION,
    REQUIRED_CONTRACT_HASHES,
    M1DevelopmentBaseCache,
)
from model.M1.data import (
    FEATURE_NAMES_V2,
    M1_V2_FEATURE_SCHEMA_ID,
    M1_V2_FEATURE_SCHEMA_STATUS,
    STATIC_FEATURE_NAMES,
    V2_WEATHER_FIELDS,
)
from model.M1.static_features import (
    STATIC_NUMERIC_FEATURE_NAMES,
    encode_static_values,
    fit_static_normalization,
)
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
B1_ROOT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b1"
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b1r"
A2_EXPECTED_CACHE_HASH = (
    "sha256:7cb35178323aecdd288010b0b70daf15112695baf627b53d2bef03136393b082"
)


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


def load_a2_baseline() -> tuple[M1DevelopmentBaseCache, dict, dict, tuple[str, ...]]:
    manifest_path = A2_ROOT / "M1_V2_DATA_GATE_A2_CACHE_MANIFEST.json"
    data_path = A2_ROOT / "M1_V2_DATA_GATE_A2_CACHE.npz"
    result_path = A2_ROOT / "AIR_SLOT_M1_V2_DATA_GATE_A2.json"
    inventory_path = B1_ROOT / "FEATURE_INVENTORY_AND_SEMANTICS.json"
    manifest = _read_json(manifest_path)
    result = _read_json(result_path)
    inventory = _read_json(inventory_path)["inventory"]
    old_names = tuple(inventory["ordered_dynamic_features"])
    cache = M1DevelopmentBaseCache.load(
        data_path,
        manifest_path,
        expected_cache_key=manifest["cache_key"],
        allow_legacy_schema=True,
    )
    if manifest.get("cache_hash") != A2_EXPECTED_CACHE_HASH:
        raise ValueError("M1_B1R_A2_CACHE_HASH_MISMATCH")
    if len(old_names) != int(cache.store.values_flat.shape[1]):
        raise ValueError("M1_B1R_A2_FEATURE_INVENTORY_WIDTH_MISMATCH")
    return cache, manifest, result, old_names


def _transform_dynamic(
    values: torch.Tensor, old_names: tuple[str, ...]
) -> tuple[torch.Tensor, dict[str, Any]]:
    old_index = {name: index for index, name in enumerate(old_names)}
    columns = []
    collapsed = {}
    for name in FEATURE_NAMES_V2:
        if name in old_index:
            columns.append(values[:, old_index[name]].clone())
            continue
        if name not in {"current_weather.stale_mask", "current_weather.fallback_mask"}:
            raise ValueError(f"M1_B1R_DYNAMIC_SOURCE_MISSING:{name}")
        kind = "stale" if ".stale_" in name else "fallback"
        sources = tuple(f"weather.{field}.{kind}_mask" for field in V2_WEATHER_FIELDS)
        source_columns = [values[:, old_index[source]] for source in sources]
        reference = source_columns[0]
        if not all(torch.equal(reference, column) for column in source_columns[1:]):
            raise ValueError(f"M1_B1R_WEATHER_OBJECT_MASK_SOURCE_CONFLICT:{kind}")
        columns.append(reference.clone())
        collapsed[kind] = {
            "sources": list(sources),
            "target": name,
            "all_rows_exactly_equal": True,
        }
    transformed = torch.stack(columns, dim=1).to(dtype=torch.float32).contiguous()
    new_index = {name: index for index, name in enumerate(FEATURE_NAMES_V2)}
    missing = transformed[:, new_index["weather.wind_direction_deg.missing_mask"]] > 0.5
    sin_index = new_index["weather.wind_direction_deg.sin"]
    cos_index = new_index["weather.wind_direction_deg.cos"]
    original_sin_violations = int(torch.count_nonzero(transformed[missing, sin_index]))
    original_cos_violations = int(torch.count_nonzero(transformed[missing, cos_index]))
    transformed[missing, sin_index] = 0.0
    transformed[missing, cos_index] = 0.0
    return transformed, {
        "canonical_missing_rows": int(missing.sum()),
        "pre_repair_sin_violations": original_sin_violations,
        "pre_repair_cos_violations": original_cos_violations,
        "post_repair_sin_violations": int(
            torch.count_nonzero(transformed[missing, sin_index])
        ),
        "post_repair_cos_violations": int(
            torch.count_nonzero(transformed[missing, cos_index])
        ),
        "collapsed_weather_masks": collapsed,
    }


def _fit_and_encode_static(cache: M1DevelopmentBaseCache):
    store = cache.store
    train_rows = [
        (episode_id, lineage)
        for episode_id, lineage, split in zip(
            store.sample_episode_ids,
            store.static_context_lineages,
            store.sample_splits,
        )
        if split == "train"
    ]
    artifact = fit_static_normalization(train_rows, split="train")
    static_values = torch.cat(
        [
            encode_static_values(
                {
                    name: _reference_value(lineage, name)
                    for name in STATIC_NUMERIC_FEATURE_NAMES
                },
                artifact,
            )
            for lineage in store.static_context_lineages
        ],
        dim=0,
    ).contiguous()
    train_ids = {
        episode_id
        for episode_id, split in zip(store.sample_episode_ids, store.sample_splits)
        if split == "train"
    }
    transform_only_ids = {
        episode_id
        for episode_id, split in zip(store.sample_episode_ids, store.sample_splits)
        if split in {"calibration", "development"}
    }
    return (
        artifact,
        static_values,
        {
            "fit_split": artifact.fitted_split,
            "fitting_unit": "UNIQUE_TRAIN_EPISODE_STATIC_CONTEXTS",
            "episode_level_fit": artifact.episode_level_fit,
            "fit_episode_count": len(train_ids),
            "fit_episode_ids_hash": artifact.episode_ids_hash,
            "calibration_development_episode_ids_in_fit": len(
                train_ids & transform_only_ids
            ),
            "STATIC_NORMALIZATION_TRAIN_ONLY": (
                "PASS"
                if artifact.fitted_split == "train"
                and artifact.episode_level_fit
                and artifact.episode_count == len(train_ids)
                and not (train_ids & transform_only_ids)
                else "FAIL"
            ),
            "artifact_hash": content_id(artifact.model_dump(mode="json")),
        },
    )


def _reference_value(lineage: dict[str, object] | None, feature: str) -> float | None:
    key = (
        "turnaround_reference"
        if feature == "turnaround_reference_minutes"
        else "taxi_reference"
    )
    item = (lineage or {}).get(key)
    if not isinstance(item, dict):
        return None
    if not item.get("reference_id") or not item.get("freeze_id"):
        return None
    value = item.get("value")
    return None if value is None else float(value)


def _removed_features(old_names: tuple[str, ...]) -> dict[str, list[str]]:
    removed = [name for name in old_names if name not in FEATURE_NAMES_V2]
    categories = {
        "structural_state_masks": [
            name
            for name in removed
            if name.startswith("state.") and name.endswith("_mask")
        ],
        "weather_duplicated_masks": [
            name
            for name in removed
            if name.startswith("weather.")
            and name.endswith((".stale_mask", ".fallback_mask"))
        ],
        "evidence_numeric": [name for name in removed if ".evidence." in name],
        "support_numeric": [name for name in removed if ".support." in name],
        "full_prefix_ar": [name for name in removed if name.startswith("ar.weather.")],
    }
    categorized = {name for names in categories.values() for name in names}
    categories["other_structural_constants"] = [
        name for name in removed if name not in categorized
    ]
    categories["all_exact_removed_feature_names"] = removed
    categories["added_object_level_features"] = [
        name for name in FEATURE_NAMES_V2 if name not in old_names
    ]
    return categories


def _candidate_schema(old_names: tuple[str, ...]) -> dict[str, Any]:
    inventory = feature_inventory()
    semantics = semantic_table()
    removed = _removed_features(old_names)
    payload = {
        "schema_version": "M1_V2_FEATURE_SCHEMA_CANDIDATE_B1R_V1",
        "schema_id": M1_V2_FEATURE_SCHEMA_ID,
        "schema_status": M1_V2_FEATURE_SCHEMA_STATUS,
        "training_frozen": False,
        "ordered_dynamic_features": list(FEATURE_NAMES_V2),
        "ordered_static_features": list(STATIC_FEATURE_NAMES),
        "dynamic_feature_count": len(FEATURE_NAMES_V2),
        "static_feature_count": len(STATIC_FEATURE_NAMES),
        "total_feature_count": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES),
        "features": semantics,
        "groups": inventory["groups"],
        "removed": removed,
        "metadata_retained": {
            "evidence_class": "PRE_LINEAGE_AND_ARTIFACT_PROVENANCE",
            "full_support_state": "PRE_LINEAGE_AND_ARTIFACT_PROVENANCE",
            "static_context_lineage": "CACHE_ROUNDTRIP_RETAINED",
            "identity_and_reference_ids": "STATIC_CONTEXT_LINEAGE_ONLY_NO_ORDINAL_ENCODING",
        },
        "applied_decisions": {
            "B1-D01": "REMOVE",
            "B1-D02": "COLLAPSE_OBJECT_LEVEL",
            "B1-D03": "METADATA_ONLY",
            "B1-D04": "REDUCE",
            "B1-D05": "REMOVE",
            "B1-D06": "TRAIN_STANDARDIZED",
            "B1-D07": "PER_FEATURE_MASKED_BLOCK",
        },
    }
    payload["schema_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_SCHEMA_HASH"
    payload["schema_hash"] = content_id(payload)
    return payload


def _support_metadata_counts(
    cache: M1DevelopmentBaseCache, old_names: tuple[str, ...]
) -> dict[str, Any]:
    old_index = {name: index for index, name in enumerate(old_names)}
    rows = []
    store = cache.store
    for sample_index in range(len(store.sample_splits)):
        episode_index = int(store.sample_episode_indices[sample_index])
        episode_start = int(store.episode_offsets[episode_index])
        end = int(store.sample_end_offsets[sample_index])
        rows.append(store.values_flat[episode_start + end - 1])
    matrix = torch.stack(rows)
    output = {}
    for split in ("train", "calibration", "development"):
        selected = torch.tensor([value == split for value in store.sample_splits])
        output[split] = {}
        for obj in ("current_weather", "schedule_reference", "current_state"):
            output[split][obj] = {
                level: int(
                    torch.count_nonzero(
                        matrix[selected, old_index[f"{obj}.support.{level}"]]
                    )
                )
                for level in ("SUPPORTED", "DEGRADED", "ABSTAIN")
            }
    return output


def _store_identity_equal(left, right) -> dict[str, bool]:
    return {
        "episode_offsets": torch.equal(left.episode_offsets, right.episode_offsets),
        "episode_ids": left.episode_ids == right.episode_ids,
        "sample_episode_indices": torch.equal(
            left.sample_episode_indices, right.sample_episode_indices
        ),
        "sample_start_offsets": torch.equal(
            left.sample_start_offsets, right.sample_start_offsets
        ),
        "sample_end_offsets": torch.equal(
            left.sample_end_offsets, right.sample_end_offsets
        ),
        "sample_episode_ids": left.sample_episode_ids == right.sample_episode_ids,
        "sample_decision_node_ids": (
            left.sample_decision_node_ids == right.sample_decision_node_ids
        ),
        "sample_episode_dates": left.sample_episode_dates == right.sample_episode_dates,
        "sample_splits": left.sample_splits == right.sample_splits,
        "static_context_lineages": (
            left.static_context_lineages == right.static_context_lineages
        ),
        "labels": all(
            torch.equal(left.labels[name], right.labels[name]) for name in left.labels
        ),
        "active": all(
            torch.equal(left.active[name], right.active[name]) for name in left.active
        ),
    }


def _roundtrip_equal(left, right) -> dict[str, Any]:
    checks = {
        **_store_identity_equal(left, right),
        "dynamic_sequence": torch.equal(left.values_flat, right.values_flat),
        "static_tensor": (
            left.static_values is not None
            and right.static_values is not None
            and torch.equal(left.static_values, right.static_values)
        ),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _write_packet(path: Path, report: dict) -> None:
    static = report["static"]
    lines = [
        "# M1 V2 Feature Gate B2 Candidate Packet",
        "",
        f"- B1R status: `{report['FEATURE_GATE_STATUS']}`",
        "- Candidate status: `NOT_TRAINING_FROZEN`",
        f"- Schema hash: `{report['feature_schema']['schema_hash']}`",
        f"- Candidate cache: `{report['cache']['candidate_cache_hash']}`",
        f"- Dynamic/static width: {report['feature_schema']['dynamic_candidate']} / "
        f"{report['feature_schema']['static_candidate']}",
        "- Exp1B history separation: `CLEAN`",
        "- Final Test access: `0`",
        "",
        "## Human Freeze Checklist",
        "",
        "- [ ] Approve exact ordered dynamic feature names.",
        "- [ ] Approve exact ordered static feature names.",
        "- [ ] Approve Train-only static normalization statistics.",
        "- [ ] Approve removed feature lists and metadata-only provenance treatment.",
        "- [ ] Confirm target-support review remains deferred to Gate C0.",
        "",
        "## Static Normalization",
        "",
        f"- Turnaround mean/std: {static['turnaround']['mean']} / {static['turnaround']['std']}",
        f"- Taxi mean/std: {static['taxi']['mean']} / {static['taxi']['std']}",
        f"- Partial missing cases: {static['partial_missing_cases']}",
        "",
        "No B2 freeze, training, tuning, Final Test, FULL, or paper_full action was executed.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if len(FEATURE_NAMES_V2) != 41:
        raise RuntimeError("M1_B1R_HISTORICAL_CANDIDATE_ONLY_CURRENT_SCHEMA_IS_B2R")
    a2_cache, a2_manifest, a2_result, old_names = load_a2_baseline()
    schema = _candidate_schema(old_names)
    dynamic, dynamic_transform = _transform_dynamic(
        a2_cache.store.values_flat, old_names
    )
    static_normalization, static_values, static_fit = _fit_and_encode_static(a2_cache)
    candidate_store = replace(
        a2_cache.store,
        values_flat=dynamic,
        static_values=static_values,
    )
    contract_hashes = dict(a2_manifest["contract_hashes"])
    contract_hashes["feature_contract_hash"] = schema["schema_hash"]
    contract_hashes["normalization_contract_hash"] = content_id(
        {
            "dynamic_normalization": a2_cache.normalization.model_dump(mode="json"),
            "static_normalization": static_normalization.model_dump(mode="json"),
            "fitted_split": "train",
        }
    )
    if set(REQUIRED_CONTRACT_HASHES) - set(contract_hashes):
        raise ValueError("M1_B1R_REQUIRED_CONTRACT_HASH_MISSING")
    candidate_key = content_id(
        {
            "scope": "FEATURE_GATE_B1R_CANDIDATE",
            "a2_cache_hash": a2_manifest["cache_hash"],
            "a2_cache_key": a2_manifest["cache_key"],
            "candidate_schema_hash": schema["schema_hash"],
            "static_normalization_hash": static_fit["artifact_hash"],
            "partition_counts": a2_manifest["partition_counts"],
        }
    )
    candidate = M1DevelopmentBaseCache.from_store(
        store=candidate_store,
        normalization=a2_cache.normalization,
        static_normalization=static_normalization,
        audit={
            "scope": "FEATURE_GATE_B1R_CANDIDATE",
            "candidate_status": "NOT_TRAINING_FROZEN",
            "final_test_access_count": 0,
            "gate_b_entered": True,
            "gate_b2_feature_freeze": False,
        },
        cache_key=candidate_key,
        source_manifest_hash=a2_manifest["source_manifest_hash"],
        contract_hashes=contract_hashes,
        feature_names=FEATURE_NAMES_V2,
        static_feature_names=STATIC_FEATURE_NAMES,
        provenance={
            "a2_cache_hash": a2_manifest["cache_hash"],
            "a2_cache_key": a2_manifest["cache_key"],
            "a2_cache_schema": a2_manifest["cache_schema_version"],
            "a2_role": "DATA_PRE_BASELINE_PROVENANCE_ONLY",
            "candidate_schema_hash": schema["schema_hash"],
            "static_normalization_hash": static_fit["artifact_hash"],
        },
        feature_schema_hash=schema["schema_hash"],
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "M1_V2_FEATURE_GATE_B1R_CANDIDATE_CACHE.npz"
    manifest_path = output_dir / "M1_V2_FEATURE_GATE_B1R_CANDIDATE_CACHE_MANIFEST.json"
    saved_manifest = candidate.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(
        data_path, manifest_path, expected_cache_key=candidate_key
    )
    roundtrip = _roundtrip_equal(candidate.store, loaded.store)
    a2_identity = _store_identity_equal(a2_cache.store, candidate.store)

    profiles = feature_profiles(candidate)
    missing = missing_encoding_audit(candidate)
    redundancy = redundancy_audit(candidate)
    history = history_semantics()
    shifts = shift_diagnostics(
        profiles["profiles"], list(FEATURE_NAMES_V2) + list(STATIC_FEATURE_NAMES)
    )
    support_numeric = support_state_counts(candidate)
    support_metadata = _support_metadata_counts(a2_cache, old_names)
    target = target_support_from_a2(a2_result)
    removed = schema["removed"]
    static_audit = missing["static"]
    wind_checks = {
        row["numeric"]: row
        for row in missing["checks"]
        if row["numeric"].startswith("weather.wind_direction_deg.")
    }
    train_profile = profiles["profiles"]["train"]
    object_mask_train_constants = [
        row["feature"]
        for row in train_profile
        if row["feature"]
        in {"current_weather.stale_mask", "current_weather.fallback_mask"}
        and row["constant"]
    ]
    structural_scan = encoder_static_scan()
    contract_structural_constants = [
        name for name in structural_scan["features"] if name in FEATURE_NAMES_V2
    ]

    data_usage = run_data_usage_audit(output_dir / "data_usage_audit")
    ownership = build_gate_result(ROOT)
    a2_ready = (
        a2_result.get("DATA_GATE_STATUS") == "DATA_GATE_A2_PASS_READY_FOR_GATE_B"
        and a2_manifest.get("final_test_access_count") == 0
    )
    identity_pass = all(a2_identity.values())
    labels_unchanged = a2_identity["labels"] and a2_identity["active"]
    gates_pass = (
        data_usage["status"] == "DATA_USAGE_CONTRACT_AUDIT_PASS"
        and ownership["PRE_OWNERSHIP_GATE"] == "PASS"
        and ownership["STATIC_VOLUME_GATE"] == "PASS"
    )
    invariant_pass = (
        missing["all_checked_encodings_exact"]
        and static_audit["STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"] == 0
        and static_audit["PARTIAL_STATIC_OBSERVED_VALUE_LOST"] == 0
        and history["FULL_PREFIX_HISTORY_FEATURE_COUNT"] == 0
        and history["EXP1B_HISTORY_SEPARATION_STATUS"] == "CLEAN"
        and static_fit["STATIC_NORMALIZATION_TRAIN_ONLY"] == "PASS"
    )
    contract_pass = (
        a2_ready
        and gates_pass
        and identity_pass
        and labels_unchanged
        and roundtrip["status"] == "PASS"
        and saved_manifest["final_test_access_count"] == 0
    )
    status = (
        "CONTRACT_FAILURE"
        if not contract_pass
        else (
            "FEATURE_GATE_B1R_DATA_INCONSISTENCY"
            if not invariant_pass
            else (
                "FEATURE_GATE_B1R_REVIEW_REMAINS"
                if contract_structural_constants
                else "FEATURE_GATE_B1R_PASS_CANDIDATE_READY_FOR_B2"
            )
        )
    )
    static_values_payload = static_normalization.values
    report = {
        "schema_version": "AIR_SLOT_M1_V2_FEATURE_GATE_B1R_V1",
        "FEATURE_GATE_STATUS": status,
        "repository_head": _head(),
        "scope": "TRAIN_CALIBRATION_DEVELOPMENT_ONLY",
        "applied_decisions": schema["applied_decisions"],
        "wind_direction": {
            "missing_rows": wind_checks["weather.wind_direction_deg.sin"][
                "missing_rows"
            ],
            "sin_missing_neutral": (
                wind_checks["weather.wind_direction_deg.sin"]["violations"] == 0
            ),
            "cos_missing_neutral": (
                wind_checks["weather.wind_direction_deg.cos"]["violations"] == 0
            ),
            "violations": sum(row["violations"] for row in wind_checks.values()),
            "canonical_transform": dynamic_transform,
        },
        "feature_schema": {
            "dynamic_before": len(old_names),
            "dynamic_candidate": len(FEATURE_NAMES_V2),
            "static_before": int(a2_manifest["static_feature_count"]),
            "static_candidate": len(STATIC_FEATURE_NAMES),
            "total_candidate": len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES),
            "schema_hash": schema["schema_hash"],
            "schema_status": M1_V2_FEATURE_SCHEMA_STATUS,
            "schema_artifact": "M1_V2_FEATURE_SCHEMA_CANDIDATE_B1R.json",
        },
        "removed": removed,
        "support": {
            "numeric_retained": ["current_weather.support.ABSTAIN"],
            "metadata_retained": "FULL_SUPPORT_STATE_IN_PRE_LINEAGE_AND_ARTIFACT_PROVENANCE",
            "numeric_counts": support_numeric,
            "a2_full_state_counts_before_reduction": support_metadata,
            "OUT_OF_TRAIN_SUPPORT_STATE": "DEGRADED_NOT_LEARNED_BY_DATA2_CANDIDATE",
        },
        "exp1b": history,
        "static": {
            "normalization_fitting_unit": static_fit["fitting_unit"],
            "train_only": static_fit["STATIC_NORMALIZATION_TRAIN_ONLY"],
            "normalization_artifact_hash": static_fit["artifact_hash"],
            "fit_episode_count": static_fit["fit_episode_count"],
            "fit_episode_ids_hash": static_fit["fit_episode_ids_hash"],
            "turnaround": static_values_payload[
                "turnaround_reference_minutes"
            ].model_dump(mode="json"),
            "taxi": static_values_payload["taxi_reference_minutes"].model_dump(
                mode="json"
            ),
            "partial_missing_cases": static_audit["partial_missing_cases"],
            "partial_missing_case_details": static_audit[
                "partial_missing_case_details"
            ],
            "observed_counterpart_retained": (
                static_audit["PARTIAL_STATIC_OBSERVED_VALUE_LOST"] == 0
            ),
        },
        "cache": {
            "a2_provenance_cache": a2_manifest["cache_hash"],
            "a2_cache_schema": a2_manifest["cache_schema_version"],
            "candidate_cache_hash": saved_manifest["cache_hash"],
            "candidate_cache_key": candidate_key,
            "candidate_cache_schema": CACHE_SCHEMA_VERSION,
            "candidate_status": "NOT_TRAINING_FROZEN",
            "roundtrip": roundtrip,
            "a2_identity_labels_active_lineage_ids_unchanged": a2_identity,
        },
        "missing_invariants": {
            "MISSING_NUMERIC_NOT_ZERO": missing["violation_counts"].get(
                "MISSING_NUMERIC_NOT_ZERO", 0
            ),
            "DERIVED_INVALID_NUMERIC_NOT_ZERO": missing["violation_counts"].get(
                "DERIVED_INVALID_NUMERIC_NOT_ZERO", 0
            ),
            "MISSING_MASK_VALUE_VIOLATIONS": missing["violation_counts"].get(
                "MISSING_MASK_VALUE_VIOLATIONS", 0
            ),
            "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK": static_audit[
                "STATIC_MISSING_BLOCK_ZERO_FILLED_WITHOUT_MASK"
            ],
            "PARTIAL_STATIC_OBSERVED_VALUE_LOST": static_audit[
                "PARTIAL_STATIC_OBSERVED_VALUE_LOST"
            ],
        },
        "target": {
            "label_profile_unchanged": labels_unchanged,
            "profile_source": target["source"],
            "profile": target["splits"],
            "overflow": target["overflow_count_all_nonfinal_splits"],
            "TARGET_SUPPORT_REVIEW_REQUIRED": "YES",
        },
        "diagnostics": {
            "train_profile": train_profile,
            "shift_report_only": shifts,
            "redundancy": redundancy,
            "contract_structural_constants": contract_structural_constants,
            "ordinary_train_constants_report_only": [
                row["feature"] for row in train_profile if row["constant"]
            ],
            "object_mask_train_constants_report_only": object_mask_train_constants,
            "missing": missing,
        },
        "validation_gates": {
            "a2_ready": a2_ready,
            "data_usage_status": data_usage["status"],
            "data_usage_artifact_hash": data_usage["artifact_hash"],
            "PRE_OWNERSHIP_GATE": ownership["PRE_OWNERSHIP_GATE"],
            "STATIC_VOLUME_GATE": ownership["STATIC_VOLUME_GATE"],
            "ownership_findings": ownership["findings"],
        },
        "safety": {
            "M1_TRAINING_RUNS": 0,
            "TUNING_RUNS": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "GATE_B_ENTERED": True,
            "GATE_B2_FEATURE_FREEZE": False,
        },
    }
    report["artifact_hash_basis"] = "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH"
    basis = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["artifact_hash"] = f"sha256:{sha256(basis.encode('utf-8')).hexdigest()}"

    _write_json(output_dir / "M1_V2_FEATURE_SCHEMA_CANDIDATE_B1R.json", schema)
    _write_json(
        output_dir / "FEATURE_PROFILE_AND_SHIFT_B1R.json",
        {
            "profiles": profiles["profiles"],
            "shift_report_only": shifts,
        },
    )
    _write_json(output_dir / "FEATURE_REDUNDANCY_B1R.json", redundancy)
    _write_json(output_dir / "FEATURE_MISSING_INVARIANTS_B1R.json", missing)
    _write_json(output_dir / "AIR_SLOT_M1_V2_FEATURE_GATE_B1R.json", report)
    _write_packet(output_dir / "M1_V2_FEATURE_GATE_B2_CANDIDATE_PACKET.md", report)
    return report


def main() -> None:
    report = run()
    print(
        json.dumps(
            {
                "FEATURE_GATE_STATUS": report["FEATURE_GATE_STATUS"],
                "artifact_hash": report["artifact_hash"],
                "schema_hash": report["feature_schema"]["schema_hash"],
                "candidate_cache_hash": report["cache"]["candidate_cache_hash"],
                "safety": report["safety"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
