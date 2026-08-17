from __future__ import annotations

import json
from pathlib import Path

from model.PRE.streaming.development import pre_contract_hash


OLD_EPISODES = 951359
OLD_NODES = 13721540


def build_development_delta_manifest(
    *,
    root: Path,
    old_manifest_path: Path,
    audit_path: Path,
    output_path: Path,
) -> dict:
    old = json.loads(old_manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    old_counts = old["counts"]
    if (
        old_counts["pre_eligible_episodes"] != OLD_EPISODES
        or old_counts["pre_eligible_nodes"] != OLD_NODES
    ):
        raise RuntimeError("OLD_PRE_DEVELOPMENT_COUNTS_MISMATCH")
    if audit["final_test_access_count"] != 0:
        raise RuntimeError("FINAL_TEST_ACCESS_RECORDED")
    removed_episodes = int(audit["DEVELOPMENT_CROSS_SPLIT_EPISODES"])
    removed_nodes = int(audit["removed_nodes_by_pool"]["development"])
    removed_insufficient = int(
        audit.get("removed_insufficient_history_by_pool", {}).get("development", 0)
    )
    new_episodes = OLD_EPISODES - removed_episodes
    new_nodes = OLD_NODES - removed_nodes
    new_insufficient = int(old_counts["insufficient_history_episodes"]) - removed_insufficient
    manifest = {
        "schema_version": "AIR_SLOT_PRE_DEVELOPMENT_STREAM_MANIFEST_V2",
        "completion_status": "PASS",
        "count_method": "EXACT_BOUNDARY_DELTA_WITH_BOUNDED_PUBLISHER_CONSISTENCY",
        "old_manifest": str(old_manifest_path.relative_to(root)),
        "split_containment_audit": str(audit_path.relative_to(root)),
        "PRE_contract_hash": pre_contract_hash(root),
        "source_hashes": old["source_hashes"],
        "registry_hash": old["registry_hash"],
        "scientific_config_hash": old["scientific_config_hash"],
        "development_date_bounds": old["development_date_bounds"],
        "old_pre_eligible_episodes": OLD_EPISODES,
        "new_pre_eligible_episodes": new_episodes,
        "old_pre_eligible_nodes": OLD_NODES,
        "new_pre_eligible_nodes": new_nodes,
        "cross_split_removed_episodes": removed_episodes,
        "cross_split_removed_nodes": removed_nodes,
        "abstain_episodes": int(old_counts["abstain_episodes"]),
        "insufficient_history_episodes": new_insufficient,
        "removed_insufficient_history_episodes": removed_insufficient,
        "candidate_episodes_before_containment": OLD_EPISODES,
        "published_episodes_after_containment": new_episodes,
        "eligible_nodes_after_containment": new_nodes,
        "same_split_august_to_september_allowed": audit[
            "same_split_august_to_september_allowed"
        ],
        "delta_equivalence_basis": [
            "EPISODE_IDENTITY_UNCHANGED",
            "NODE_GRID_UNCHANGED",
            "PRE_SUPPORT_SEMANTICS_UNCHANGED",
            "ONLY_CROSS_V5_SPLIT_EXCLUSION_ADDED",
        ],
        "D_TO_classification_performed": False,
        "sampling_performed": False,
        "final_test_access_count": 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output_path)
    return manifest
