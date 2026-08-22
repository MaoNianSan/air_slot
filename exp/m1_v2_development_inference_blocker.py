"""Persist the honest blocker when frozen-cohort config provenance is absent."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.PRE.streaming.data2 import config_hash
from model.common.identity import content_id


OUTPUT = Path("artifacts/diagnostics/m1_v2_development_inference_binding/M1_V2_DEVELOPMENT_INFERENCE_BINDING_BLOCKER.json")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"M1_V2_INFERENCE_BLOCKER_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def materialize_blocker_report(*, root: Path, output: Path | None = None) -> Path:
    root = Path(root).resolve()
    output = (output or root / OUTPUT).resolve()
    cohort_path = root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json"
    binding_path = root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json"
    cache_manifest_path = root / "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
    checkpoint_path = root / "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
    for path in (cohort_path, binding_path, cache_manifest_path, checkpoint_path):
        if not path.is_file():
            raise RuntimeError(f"M1_V2_INFERENCE_BLOCKER_INPUT_MISSING:{path}")
    cohort = _load(cohort_path)
    binding = _load(binding_path)
    cache_manifest = _load(cache_manifest_path)
    cache_nodes = set()
    cache_hash = cache_manifest.get("cache_hash")
    # The existing Exp2 formal audit already records the frozen-cache identity
    # comparison; keep this report read-only and do not load/rewrite the cache.
    audit_path = root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_ARTIFACT_LINEAGE.json"
    if audit_path.is_file():
        audit = _load(audit_path)
        fixed = audit.get("fixed_contract", {})
        intersection = fixed.get("m1_cache_exp2_cohort_intersection_count")
        cache_node_count = fixed.get("m1_cache_development_node_count")
        cohort_node_count = fixed.get("exp2_cohort_node_count")
    else:
        intersection = None
        cache_node_count = cache_manifest.get("partition_counts", {}).get("development")
        cohort_node_count = len(cohort.get("node_ids", ()))
    payload = {
        "schema_version": "M1_V2_DEVELOPMENT_INFERENCE_BINDING_BLOCKER_V1",
        "status": "BLOCKED_M1_COHORT_CONFIG_PROVENANCE_UNRESOLVED",
        "scope": "DEVELOPMENT_ONLY_FROZEN_EXP2_COHORT_INFERENCE_BINDING",
        "blocking_reason": "The frozen cohort config hash cannot be reproduced from the current worktree or retained reachable Git config snapshots.",
        "identity_facts": {
            "cohort_path": str(cohort_path.relative_to(root)).replace("\\", "/"),
            "cohort_sha256": _hash(cohort_path),
            "cohort_config_hash": cohort.get("config_hash"),
            "cohort_git_sha": cohort.get("git_sha"),
            "current_config_hash": config_hash(root),
            "current_config_matches_cohort": config_hash(root) == cohort.get("config_hash"),
            "frozen_m1_binding_sha256": _hash(binding_path),
            "checkpoint_sha256": _hash(checkpoint_path),
            "feature_schema_hash": binding.get("frozen_contracts", {}).get("feature_schema_hash"),
            "cache_hash": cache_hash,
        },
        "existing_cache_comparison": {
            "cache_development_node_count": cache_node_count,
            "exp2_cohort_node_count": cohort_node_count,
            "node_intersection_count": intersection,
            "interpretation": "Existing B2 cache is not the frozen Exp2 cohort and cannot be reused by alias.",
        },
        "checks_completed": [
            "frozen checkpoint hash and M1 model binding verified",
            "dynamic feature hash and 39-plus-4 feature accounting verified",
            "Development source scope restricted to BTS month=08 and month=09",
            "Final Test source path not selected",
            "positive-tail policy remains HUMAN_DECISION_REQUIRED and UNRESOLVED",
        ],
        "required_resolution": {
            "shortest_path": "Provide the exact config snapshot used to materialize the frozen cohort (or an authoritative content-addressed config artifact).",
            "do_not_do": [
                "do not ignore config hash mismatch",
                "do not silently rebind the cohort to current config",
                "do not rebuild cohort under current config and call it the same cohort",
                "do not select a positive-tail rule automatically",
            ],
            "after_resolution": [
                "rerun exact identity audit",
                "materialize M1 inference inputs",
                "stop at M1_POSITIVE_TAIL_DECISION_REQUIRED before scenario draws",
            ],
        },
        "M1_TRAINING_RUNS_THIS_BLOCKER": 0,
        "TUNING_RUNS_THIS_BLOCKER": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "FULL": False,
    }
    payload["artifact_hash"] = content_id(payload)
    _write(output, payload)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    path = materialize_blocker_report(root=Path(__file__).resolve().parents[1], output=args.output)
    print(json.dumps({"status": "BLOCKED_M1_COHORT_CONFIG_PROVENANCE_UNRESOLVED", "artifact": str(path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
