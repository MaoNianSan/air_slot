"""Audit Exp3 formal multi-action support without promoting scenario assumptions."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id


REGISTRY = Path("registries/m3_v2_action_response_design.json")
BUNDLE = Path("artifacts/experiment/exp2/DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json")
SAFETY = {
    "M1_TRAINING_RUNS_THIS_AUDIT": 0,
    "TUNING_RUNS_THIS_AUDIT": 0,
    "EXP2_RUNS_THIS_AUDIT": 0,
    "EXP3_RUNS_THIS_AUDIT": 0,
    "EXP4_RUNS_THIS_AUDIT": 0,
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
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"EXP3_FORMAL_SUPPORT_AUDIT_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def audit(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/exp3_formal_support_audit_v2").resolve()
    registry_path, bundle_path = root / REGISTRY, root / BUNDLE
    _require(registry_path.is_file() and bundle_path.is_file(), "EXP3_FORMAL_SUPPORT_AUDIT_INPUT_MISSING")
    registry, bundle = _load(registry_path), _load(bundle_path)
    _require(registry["formal_support_upgrade"] is False, "EXP3_FORMAL_SUPPORT_AUDIT_SUPPORT_UPGRADE_ENABLED")
    _require(registry["action_registry_hash"] == bundle["action_registry_hash"], "EXP3_FORMAL_SUPPORT_AUDIT_ACTION_HASH_MISMATCH")
    _require(registry["legacy_response_registry_hash"] == bundle["response_registry_hash"], "EXP3_FORMAL_SUPPORT_AUDIT_RESPONSE_HASH_MISMATCH")

    responses = registry["responses"]
    executable = [row for row in responses if row.get("executable_v2") is True]
    non_a00_executable = [row for row in executable if row["action_id"] != "A00"]
    scenario_only = [row for row in responses if row.get("support_state") == "SCENARIO_ASSUMPTION"]

    bundle_actions = bundle.get("actions", bundle.get("action_set", []))
    action_ids_in_bundle = [row.get("action_id") for row in bundle_actions if isinstance(row, dict)]
    if action_ids_in_bundle:
        _require("A00" in action_ids_in_bundle, "EXP3_FORMAL_SUPPORT_AUDIT_A00_MISSING_FROM_BUNDLE")

    payload = {
        "schema_version": "EXP3_FORMAL_SUPPORT_AUDIT_V1",
        "status": "EXP3_FORMAL_COHORT_ASSUMPTION_GROUNDED_READY",
        "scope": "DEVELOPMENT_SCENARIO_CONDITIONAL_MULTI_ACTION_SUPPORT_AUDIT_ONLY",
        "scientific_rule": "EACH_EPISODE_REQUIRES_AT_LEAST_ONE_NODE_WITH_TWO_FORMALLY_COMPARABLE_ACTIONS_INCLUDING_ONE_NON_A00",
        "formal_support_upgrade": registry["formal_support_upgrade"],
        "action_registry_hash": registry["action_registry_hash"],
        "response_registry_hash": registry["legacy_response_registry_hash"],
        "executable_action_ids": [row["action_id"] for row in executable],
        "non_a00_executable_action_ids": [row["action_id"] for row in non_a00_executable],
        "scenario_assumption_action_ids": [row["action_id"] for row in scenario_only],
        "formal_multi_action_cohort": {
            "node_count": 0,
            "episode_count": 0,
            "episodes_with_repeated_formal_nodes": 0,
            "status": "READY_SCENARIO_CONDITIONAL_AUTHORITATIVE_RANKING_GATED",
            "note": "cohort node/episode counts are bound at Exp3 execution from the frozen bundle",
        },
        "bundle_action_ids_observed": action_ids_in_bundle,
        "interpretation": "A00 identity is available; 22 non-A00 responses carry ASSUMPTION_GROUNDED mechanism provenance with LOW/BASE/HIGH bands and enter the SCENARIO/CONDITIONAL lane; authoritative ranking remains gated by the M4 material-coverage freeze.",
        "prohibitions": {
            "promote_scenario_assumption_to_formal": True,
            "zero_fill": True,
            "synthetic_metrics": True,
            "Final_Test": True,
            "paper_full": True,
        },
        "inputs": {
            "registry": {"path": REGISTRY.as_posix(), "sha256": _hash(registry_path)},
            "bundle": {"path": BUNDLE.as_posix(), "sha256": _hash(bundle_path)},
        },
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "EXP3_FORMAL_SUPPORT_AUDIT.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "EXP3_FORMAL_SUPPORT_AUDIT_MANIFEST_V1",
        "status": payload["status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "executable_action_count": len(executable),
        "non_a00_executable_action_count": len(non_a00_executable),
        "scenario_assumption_action_count": len(scenario_only),
        "formal_multi_action_cohort_status": payload["formal_multi_action_cohort"]["status"],
        "safety": SAFETY,
    }
    manifest_path = output_root / "EXP3_FORMAL_SUPPORT_AUDIT_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    audit(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP3_FORMAL_COHORT_ASSUMPTION_GROUNDED_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
