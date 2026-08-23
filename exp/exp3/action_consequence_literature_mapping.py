"""Materialize literature-to-consequence mapping for all 23 M3 actions."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import yaml

from model.M3.registry import ActionRegistry, PRINCIPAL_IDS
from model.common.identity import content_id


MAPPING_PATH = Path("registries/m3_action_consequence_literature_mapping_v1.yaml")
ACTION_PATH = Path("registries/action_templates.yaml")
EVIDENCE_PATH = Path("registries/m3_action_scientific_evidence_v1.yaml")
DESIGN_PATH = Path("registries/m3_v2_action_response_design.json")
SAFETY = {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "EXP3_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "FULL": False}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M3_CONSEQUENCE_MAPPING_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(path)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m3_action_consequence_literature_mapping_v1").resolve()
    mapping_path, action_path, evidence_path, design_path = (root / item for item in (MAPPING_PATH, ACTION_PATH, EVIDENCE_PATH, DESIGN_PATH))
    for path in (mapping_path, action_path, evidence_path, design_path):
        if not path.is_file():
            raise RuntimeError(f"M3_CONSEQUENCE_MAPPING_INPUT_MISSING:{path}")
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
    registry = ActionRegistry.load(action_path)
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if registry.digest() != mapping["action_registry_hash"]:
        raise RuntimeError("M3_CONSEQUENCE_MAPPING_ACTION_HASH_MISMATCH")
    if tuple(mapping["mapping"]) != PRINCIPAL_IDS:
        raise RuntimeError("M3_CONSEQUENCE_MAPPING_ACTION_IDENTITY_MISMATCH")
    if mapping["formal_support_upgrade"] is not False or design["formal_support_upgrade"] is not False:
        raise RuntimeError("M3_CONSEQUENCE_MAPPING_FORMAL_UPGRADE_FORBIDDEN")
    response_ids = {row["action_id"] for row in design["responses"]}
    rows = []
    for action_id in PRINCIPAL_IDS:
        record = mapping["mapping"][action_id]
        if not set(record["literature"]) <= set(evidence["references"]):
            raise RuntimeError(f"M3_CONSEQUENCE_MAPPING_REFERENCE_UNRESOLVED:{action_id}")
        if action_id not in response_ids:
            raise RuntimeError(f"M3_CONSEQUENCE_MAPPING_RESPONSE_MISSING:{action_id}")
        rows.append({"action_id": action_id, **record, "response_registry_support": "EXECUTABLE_IDENTITY" if action_id == "A00" else "SCENARIO_ASSUMPTION", "effect_size_status": "IDENTIFIED" if action_id == "A00" else "NOT_IDENTIFIED"})
    payload = {
        "schema_version": "M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING_ARTIFACT_V1",
        "status": "M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING_MATERIALIZED",
        "action_count": len(rows),
        "action_registry_hash": registry.digest(),
        "effect_identification": mapping["effect_identification"],
        "formal_support_upgrade": False,
        "mapping_table": rows,
        "m4_interface": {
            "post_action_object": "C_a_CU",
            "risk_object": "L_a_m",
            "current_status": "SCHEMA_BOUND_BUT_AUTHORITATIVE_RANKING_BLOCKED",
            "requires": ["typed M2 component support", "versioned P(a) response parameters", "frozen M4 mapping", "no monetary overclaim"],
        },
        "remaining_blockers": ["non-A00 effect magnitudes are not empirically identified", "M2 passenger components remain ABSTAIN", "M4 mapping is not frozen"],
        "inputs": {"mapping_registry": {"path": MAPPING_PATH.as_posix(), "sha256": _hash(mapping_path)}, "action_registry": {"path": ACTION_PATH.as_posix(), "sha256": _hash(action_path)}, "evidence_registry": {"path": EVIDENCE_PATH.as_posix(), "sha256": _hash(evidence_path)}, "response_design": {"path": DESIGN_PATH.as_posix(), "sha256": _hash(design_path)}},
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING.json"
    _write(artifact_path, payload)
    manifest = {"schema_version": "M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING_MANIFEST_V1", "status": payload["status"], "artifact": str(artifact_path.resolve()), "artifact_hash": payload["artifact_hash"], "action_count": len(rows), "non_a00_effect_size_status": "NOT_IDENTIFIED", "safety": SAFETY}
    manifest_path = output_root / "M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
