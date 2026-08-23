"""Official Exp1 Development entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exp.common.official_execution import (
    load_json,
    load_official_frozen_binding,
    repository_root,
    require_active_path,
    require_development_safety,
    require_files,
)
from model.common.errors import ContractError


DEFAULT_OUTPUT = Path("artifacts/experiment/exp1_full_development")
MANIFEST = "EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
REQUIRED_OUTPUTS = (
    "EXP1_FULL_DEVELOPMENT_STATE_METRICS.json",
    "EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON.json",
    "EXP1_FULL_DEVELOPMENT_DECISION_RELEVANCE.json",
    "EXP1_FULL_DEVELOPMENT_ARTIFACT_LINEAGE.json",
)


def validate(root: Path, output_root: Path) -> dict:
    frozen = load_official_frozen_binding(root)
    output_root = require_active_path(output_root, root)
    manifest_path = output_root / MANIFEST
    required = tuple(output_root / name for name in REQUIRED_OUTPUTS)
    require_files((manifest_path, *required), code="EXP1_OFFICIAL_OUTPUT_MISSING")
    manifest = load_json(manifest_path)
    require_development_safety(manifest, label="EXP1_OFFICIAL")
    if manifest.get("status") != "EXP1_FULL_DEVELOPMENT_COMPLETE":
        raise ContractError("EXP1_OFFICIAL_STATUS_INVALID")
    if manifest.get("execution_scope") != "FULL_DEVELOPMENT_NOT_PAPER_FULL":
        raise ContractError("EXP1_OFFICIAL_SCOPE_INVALID")
    if manifest.get("development_node_count") != 1769:
        raise ContractError("EXP1_OFFICIAL_NODE_COUNT_INVALID")
    if tuple(manifest.get("variants", ())) != (
        "NO_HISTORY", "CURRENT_STATE_ONLY", "HISTORY_CONDITIONED_GRU_H32"
    ):
        raise ContractError("EXP1_OFFICIAL_VARIANTS_INVALID")
    expected = {
        "m1_checkpoint_sha256": frozen.model_hash,
        "feature_schema_hash": frozen.schema_hash,
        "cache_hash": frozen.cache_hash,
        "support_hash": frozen.support_hash,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ContractError(f"EXP1_OFFICIAL_FROZEN_HASH_MISMATCH:{key}")
    return {
        "status": "EXP1_OFFICIAL_READY",
        "mode": "VALIDATED_EXISTING_FULL_DEVELOPMENT_RESULT",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "node_count": 1769,
        "frozen_hashes": frozen.as_dict(),
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the frozen full-Development Exp1 result.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = repository_root()
    output_root = (args.output_root or root / DEFAULT_OUTPUT).resolve()
    result = validate(root, output_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
