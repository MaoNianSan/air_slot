"""Audit the canonical CU -> constructed RMB scientific boundary.

This stage is deliberately non-executing.  It validates that the current M2
interface, M4 design registry, and safety counters describe the paper-aligned
chain ``C -> CU -> RMB -> risk``.  It never synthesizes mapping parameters,
freezes a mapping, or emits downstream metrics.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id


M2_INTERFACE = Path(
    "artifacts/diagnostics/m2_cu_rmb_interface_correction_v2/M2_CU_RMB_INTERFACE.json"
)
M4_DESIGN = Path("registries/m4_cu_rmb_mapping_design_v2.json")
M4_POLICY = Path("artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json")
SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP2_RUNS": 0,
    "EXP3_RUNS": 0,
    "EXP4_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "FULL": False,
    "PAPER_FULL_RUN": False,
}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M4_CU_RMB_AUDIT_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _safety(payload: dict[str, Any], label: str) -> None:
    safety = payload.get("safety", payload)
    if safety.get("FINAL_TEST_ACCESS_COUNT", 0) != 0:
        raise RuntimeError(f"M4_CU_RMB_AUDIT_FINAL_TEST_NONZERO:{label}")
    if safety.get("FULL", False) is not False:
        raise RuntimeError(f"M4_CU_RMB_AUDIT_FULL_TRUE:{label}")
    if safety.get("PAPER_FULL_RUN", False) is not False:
        raise RuntimeError(f"M4_CU_RMB_AUDIT_PAPER_FULL_TRUE:{label}")
    for key, value in safety.items():
        if key.endswith("RUNS") and isinstance(value, (int, float)) and value != 0:
            raise RuntimeError(f"M4_CU_RMB_AUDIT_EXECUTION_NONZERO:{label}:{key}")


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (
        output_root
        or root / "artifacts/diagnostics/m4_cu_rmb_readiness_audit_v2"
    ).resolve()
    interface_path, design_path, policy_path = (
        root / M2_INTERFACE,
        root / M4_DESIGN,
        root / M4_POLICY,
    )
    if not all(path.is_file() for path in (interface_path, design_path, policy_path)):
        raise RuntimeError("M4_CU_RMB_AUDIT_INPUT_MISSING")
    interface = _load(interface_path)
    design = _load(design_path)
    policy = _load(policy_path)
    _safety(interface, "m2_interface")
    _safety(design, "m4_design")
    _safety(policy, "m4_policy")

    m2_contract = interface.get("m2_output_contract", {})
    rmb_contract = interface.get("rmb_mapping_contract", {})
    checks = {
        "canonical_action_chain": interface.get("action_chain")
        == "A -> C^a -> CU^a -> RMB^a -> risk",
        "exact_seven_component_order": tuple(interface.get("component_order", ()))
        == CONSEQUENCE_COMPONENTS
        and tuple(design.get("component_order", ())) == CONSEQUENCE_COMPONENTS,
        "m2_c_to_cu_boundary": m2_contract.get("input_object") == "C"
        and m2_contract.get("intermediate_object") == "CU"
        and m2_contract.get("mapping") == "CU_k = g_k(C_k)",
        "rmb_cu_to_rmb_boundary": rmb_contract.get("input_object") == "CU"
        and rmb_contract.get("output_object") == "RMB"
        and rmb_contract.get("formula") == "RMB_k = f_k(CU_k)",
        "no_direct_c_to_rmb_mapping": "C_k" not in rmb_contract.get("input_object", "")
        and "C_k" not in rmb_contract.get("formula", "").split("CU_k")[0],
        "mapping_not_frozen": rmb_contract.get("mapping_status") == "NOT_FROZEN"
        and design.get("scientific_status") == "SCIENTIFIC_DECISION_REQUIRED"
        and design.get("production_mapping_enabled") is False,
        "constructed_not_real_currency": rmb_contract.get("real_currency_claim") is False
        and rmb_contract.get("monetary_ground_truth_claim") is False
        and design.get("real_currency_claim") is False,
        "abstention_and_no_zero_fill": m2_contract.get("abstain_preserved") is True
        and m2_contract.get("no_zero_fill") is True,
        "no_automatic_parameter_synthesis": design.get("production_mapping_enabled") is False
        and "rmb_per_cu" in design.get("mapping_contract", {}).get(
            "required_linear_parameter_name", ""
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError("M4_CU_RMB_AUDIT_CHECK_FAILED:" + ",".join(failed))

    inputs = {
        "m2_interface": {"path": M2_INTERFACE.as_posix(), "sha256": _hash(interface_path)},
        "m4_design": {"path": M4_DESIGN.as_posix(), "sha256": _hash(design_path)},
        "m4_policy": {"path": M4_POLICY.as_posix(), "sha256": _hash(policy_path)},
    }
    payload = {
        "schema_version": "M4_CU_RMB_READINESS_AUDIT_V1",
        "status": "M4_CU_RMB_READINESS_AUDITED",
        "readiness_status": "BLOCKED_M4_RMB_MAPPING_SCIENTIFIC_DECISION_REQUIRED",
        "scope": "INTERFACE_AND_SCIENTIFIC_GATE_AUDIT_ONLY",
        "chain": "C -> CU -> RMB -> risk",
        "component_order": list(CONSEQUENCE_COMPONENTS),
        "checks": checks,
        "mapping_gate": {
            "status": "HUMAN_SCIENTIFIC_DECISION_REQUIRED",
            "required_decisions": [
                "mapping_function_per_component",
                "rmb_per_cu_or_explicit_function_parameters",
                "source_reference_and_provenance",
                "parameter_version_and_freeze_id",
                "scenario_dependence_policy",
            ],
            "prohibited_automatic_actions": [
                "synthesize_rmb_parameters",
                "fit_mapping_from_development_outcomes",
                "freeze_mapping_without_scientific_authorization",
                "emit_authoritative_m4_ranking",
            ],
        },
        "inputs": inputs,
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M4_CU_RMB_READINESS_AUDIT.json"
    _write(artifact_path, payload)
    decision = {
        "schema_version": "M4_CU_RMB_SCIENTIFIC_DECISION_PACKET_V1",
        "status": payload["readiness_status"],
        "audit_artifact": str(artifact_path.resolve()),
        "audit_artifact_hash": payload["artifact_hash"],
        "decision_required": payload["mapping_gate"],
        "claim_boundary": design["claim_boundary"],
        "safety": dict(SAFETY),
    }
    decision["artifact_hash"] = content_id(decision)
    decision_path = output_root / "M4_CU_RMB_SCIENTIFIC_DECISION_PACKET.json"
    _write(decision_path, decision)
    manifest = {
        "schema_version": "M4_CU_RMB_READINESS_AUDIT_MANIFEST_V1",
        "status": payload["status"],
        "readiness_status": payload["readiness_status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "decision_packet": str(decision_path.resolve()),
        "decision_packet_hash": decision["artifact_hash"],
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "M4_CU_RMB_READINESS_AUDIT_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "decision_packet": decision_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the CU-to-RMB scientific gate.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("M4_CU_RMB_READINESS_AUDITED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
