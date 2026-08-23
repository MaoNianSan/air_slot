"""Materialize the paper-supported M3 action library without effect overclaim."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import yaml

from model.M3.registry import ActionRegistry, PRINCIPAL_IDS
from model.common.identity import content_id


EVIDENCE_PATH = Path("registries/m3_action_scientific_evidence_v1.yaml")
ACTION_PATH = Path("registries/action_templates.yaml")
DESIGN_PATH = Path("registries/m3_v2_action_response_design.json")
M2_PATH = Path("artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json")
M4_PATH = Path("registries/m4_v2_monetary_mapping_design.json")
SAFETY = {
    "M1_TRAINING_RUNS_THIS_MATERIALIZATION": 0,
    "TUNING_RUNS_THIS_MATERIALIZATION": 0,
    "EXP3_RUNS_THIS_MATERIALIZATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M3_ACTION_LIBRARY_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m3_action_library_scientific_materialization_v1").resolve()
    evidence_path, action_path = root / EVIDENCE_PATH, root / ACTION_PATH
    design_path, m2_path, m4_path = root / DESIGN_PATH, root / M2_PATH, root / M4_PATH
    for path in (evidence_path, action_path, design_path, m2_path, m4_path):
        if not path.is_file():
            raise RuntimeError(f"M3_ACTION_LIBRARY_INPUT_MISSING:{path}")

    evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
    registry = ActionRegistry.load(action_path)
    design, m2, m4 = _load_json(design_path), _load_json(m2_path), _load_json(m4_path)
    if registry.digest() != evidence["structural_registry_hash"]:
        raise RuntimeError("M3_ACTION_LIBRARY_STRUCTURAL_HASH_MISMATCH")
    if tuple(evidence["action_evidence"]) != PRINCIPAL_IDS:
        raise RuntimeError("M3_ACTION_LIBRARY_IDENTITY_OR_ORDER_MISMATCH")
    if evidence["formal_support_upgrade"] is not False or design["formal_support_upgrade"] is not False:
        raise RuntimeError("M3_ACTION_LIBRARY_FORMAL_SUPPORT_UPGRADE_FORBIDDEN")

    response_by_id = {row["action_id"]: row for row in design["responses"]}
    rows = []
    for template in registry.templates:
        record = evidence["action_evidence"][template.template_id]
        refs = record["literature_reference"]
        if not refs or any(ref not in evidence["references"] for ref in refs):
            raise RuntimeError(f"M3_ACTION_LIBRARY_REFERENCE_MISSING:{template.template_id}")
        affected = tuple(dict.fromkeys((*template.mitigation, *template.induced, *template.induced_response)))
        response = response_by_id[template.template_id]
        passenger_blocked = any(component in {"P_itinerary", "P_service"} for component in affected)
        blockers = []
        if template.template_id != "A00":
            blockers.append("RESPONSE_EFFECT_SIZE_REMAINS_PURE_SCENARIO")
        if passenger_blocked:
            blockers.append("M2_PASSENGER_COMPONENT_SUPPORT_INCOMPLETE")
        if not m4["production_mapping_enabled"]:
            blockers.append("M4_PRODUCTION_MAPPING_NOT_FROZEN")
        rows.append({
            "action_id": template.template_id,
            "action_name": template.name,
            "category": template.family,
            "description": record["description"],
            "eligibility_condition": record["eligibility_condition"],
            "required_state_variables": record["required_state_variables"],
            "required_facts": list(template.required_facts),
            "authority_capabilities": list(template.authority_capabilities),
            "affected_consequence_components": affected,
            "execution_type": record["execution_type"],
            "provenance": record["provenance"],
            "literature_reference": refs,
            "response_support_state": response["support_state"],
            "response_parameter_source": response["parameter_source"],
            "executable_v2": response["executable_v2"],
            "can_enter_formal_A_t": template.template_id == "A00",
            "can_enter_conditional_scenario_lane": True,
            "can_produce_C_a_CU": template.template_id == "A00" or response["support_state"] == "SCENARIO_ASSUMPTION",
            "can_produce_authoritative_L_a_m": False,
            "m4_compatibility": "SCHEMA_COMPATIBLE_RANKING_BLOCKED" if blockers else "SCHEMA_COMPATIBLE",
            "blockers": blockers,
        })

    counts = Counter(row["execution_type"] for row in rows)
    payload = {
        "schema_version": "M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION_V1",
        "status": "M3_PAPER_SUPPORTED_ACTION_LIBRARY_MATERIALIZED",
        "scientific_scope": evidence["scientific_scope"],
        "action_count": len(rows),
        "action_identity_preserved": tuple(row["action_id"] for row in rows) == PRINCIPAL_IDS,
        "structural_registry_hash": registry.digest(),
        "execution_status_counts": dict(counts),
        "formal_support_upgrade": False,
        "non_a00_v2_execution_enabled": False,
        "action_evidence_table": rows,
        "literature_mapping": evidence["references"],
        "remaining_blockers": [
            "Non-A00 numerical response magnitudes remain versioned scenario assumptions rather than empirical action effects.",
            "P_itinerary and P_service are ABSTAIN in the current M2 artifact, blocking complete passenger-linked action consequences.",
            "M4 production mapping and authoritative residual-risk ranking remain unfrozen.",
            "Data2 contains no observed action log for empirical response validation.",
        ],
        "exp3_readiness_impact": {
            "paper_supported_action_library": "READY",
            "conditional_contract_count": counts.get("conditional", 0),
            "formal_executable_non_a00_count": 0,
            "formal_multi_action_cohort": "STILL_BLOCKED",
            "interpretation": "Literature support closes action-meaning provenance but does not identify action-effect parameters or promote scenario actions to formal evidence.",
        },
        "m2_binding": {"artifact_hash": m2["artifact_hash"], "status": m2["status"]},
        "m4_binding": {"production_mapping_enabled": m4["production_mapping_enabled"], "scientific_status": m4["scientific_status"]},
        "inputs": {
            "scientific_evidence_registry": {"path": EVIDENCE_PATH.as_posix(), "sha256": _hash(evidence_path)},
            "structural_action_registry": {"path": ACTION_PATH.as_posix(), "sha256": _hash(action_path)},
            "response_design": {"path": DESIGN_PATH.as_posix(), "sha256": _hash(design_path)},
            "m2_manifest": {"path": M2_PATH.as_posix(), "sha256": _hash(m2_path)},
            "m4_design": {"path": M4_PATH.as_posix(), "sha256": _hash(m4_path)},
        },
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION_MANIFEST_V1",
        "status": payload["status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "action_count": payload["action_count"],
        "execution_status_counts": payload["execution_status_counts"],
        "formal_executable_non_a00_count": 0,
        "safety": SAFETY,
    }
    manifest_path = output_root / "M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
