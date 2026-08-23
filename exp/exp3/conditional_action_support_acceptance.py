"""Materialize accepted literature-plus-scenario support for non-A00 actions.

This lane is Development-only and scenario-conditioned. It never upgrades a
scenario response to an empirical effect or authoritative M4 ranking input.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.M3.registry import PRINCIPAL_IDS
from model.common.identity import content_id

SOURCE = Path("artifacts/diagnostics/m3_action_library_scientific_materialization_v2/M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION.json")
RESPONSE = Path("registries/m3_v2_action_response_design.json")
SAFETY = {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "EXP2_RUNS": 0, "EXP3_RUNS": 0, "EXP4_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "FULL": False, "PAPER_FULL_RUN": False}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M3_CONDITIONAL_SUPPORT_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m3_conditional_action_support_v1").resolve()
    source_path, response_path = root / SOURCE, root / RESPONSE
    if not source_path.is_file() or not response_path.is_file():
        raise RuntimeError("M3_CONDITIONAL_SUPPORT_INPUT_MISSING")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    rows = source["action_evidence_table"]
    if tuple(row["action_id"] for row in rows) != PRINCIPAL_IDS:
        raise RuntimeError("M3_CONDITIONAL_SUPPORT_ACTION_IDENTITY_MISMATCH")
    response_by_id = {item["action_id"]: item for item in response["responses"]}
    table = []
    for row in rows:
        action_id = row["action_id"]
        if action_id == "A00":
            support = {
                "support_class": "SUPPORTED_IDENTITY",
                "support_state": "SUPPORTED",
                "evidence_bases": ["OPERATIONAL_RULE"],
                "hybrid": False,
                "interpretation_scope": "BASELINE_IDENTITY",
            }
        else:
            rule = response_by_id[action_id]
            if rule["support_state"] != "SCENARIO_ASSUMPTION":
                raise RuntimeError(f"M3_CONDITIONAL_SUPPORT_STATE_INVALID:{action_id}")
            if not row["literature_reference"] or not row["consequence_literature"]:
                raise RuntimeError(f"M3_CONDITIONAL_SUPPORT_LITERATURE_MISSING:{action_id}")
            support = {
                "support_class": "CONDITIONAL_HYBRID",
                "support_state": "CONDITIONAL",
                "evidence_bases": ["PUBLISHED_EVIDENCE", "SCENARIO_ASSUMPTION"],
                "hybrid": True,
                "interpretation_scope": "SCENARIO_CONDITIONED_NON_AUTHORITATIVE",
                "scenario_parameter_version": rule["parameter_version"],
                "scenario_rule_id": f"{rule['parameter_version']}:{action_id}",
                "effect_identification": "NOT_EMPIRICALLY_IDENTIFIED",
            }
        table.append({
            "action_id": action_id,
            "literature_reference": row["literature_reference"],
            "consequence_literature": row["consequence_literature"],
            "effect_mechanism": row["effect_mechanism"],
            "affected_consequence_components": row["affected_consequence_components"],
            "operational_constraints": row["operational_constraints"],
            "cost_risk_implications": row["cost_risk_implications"],
            "implementation_assumption": row["implementation_assumption"],
            "support": support,
            "m4_lane": "CONDITIONAL" if action_id != "A00" else "IDENTITY_BASELINE",
            "authoritative_ranking_allowed": False,
            "causal_effect_claim_allowed": False,
        })
    payload = {
        "schema_version": "M3_CONDITIONAL_ACTION_SUPPORT_ARTIFACT_V1",
        "status": "M3_CONDITIONAL_HYBRID_SUPPORT_MATERIALIZED",
        "scientific_interpretation": "Published literature supports operational meaning and mechanism; scenario parameters define a conditional Development response model.",
        "action_count": len(table),
        "conditional_action_count": sum(item["action_id"] != "A00" for item in table),
        "formal_support_upgrade": False,
        "non_a00_v2_execution_enabled": False,
        "conditional_scenario_lane": "READY",
        "formal_multi_action_lane": "BLOCKED_UNCHANGED",
        "action_support_table": table,
        "inputs": {"source_artifact": {"path": SOURCE.as_posix(), "sha256": _hash(source_path)}, "response_design": {"path": RESPONSE.as_posix(), "sha256": _hash(response_path)}},
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M3_CONDITIONAL_ACTION_SUPPORT.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "M3_CONDITIONAL_ACTION_SUPPORT_MANIFEST_V1",
        "status": payload["status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "conditional_action_count": payload["conditional_action_count"],
        "conditional_scenario_lane": "READY",
        "formal_multi_action_lane": "BLOCKED_UNCHANGED",
        "interpretation_scope": "SCENARIO_CONDITIONED_NON_AUTHORITATIVE",
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "M3_CONDITIONAL_ACTION_SUPPORT_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("M3_CONDITIONAL_HYBRID_SUPPORT_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
