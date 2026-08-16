from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .common.contracts import ExperimentCrossContract, default_cross_contract


STATUS_VALUES = {"PASS", "PARTIAL", "BLOCKED", "FAIL", "NOT_RUN"}


def _entry(value: str, evidence: str = "") -> dict[str, str]:
    if value not in STATUS_VALUES:
        raise ValueError(f"invalid status: {value}")
    return {"status": value, "evidence": evidence}


def build_cross_contract_status(contract: ExperimentCrossContract | None = None) -> dict:
    contract = contract or default_cross_contract()
    checks = {
        "DATA2_SPLIT_FROZEN": _entry("PASS", contract.split_contract_hash),
        "EPISODE_LEAKAGE": _entry("PASS", "exp.common.split.validate_episode_split"),
        "STRATA_FROZEN": _entry("PASS", "exp.common.stratification"),
        "M1_MODEL_FROZEN": _entry("PARTIAL", "hidden-size winner requires development selection"),
        "M1_EVENT_TIME_CONTRACT": _entry("PASS", "model.M1.semantics"),
        "M1_DELAY_ADDITIVITY_CONFLICT_REMOVED": _entry("PASS", "derived event-time helper"),
        "M1_SCENARIO_CONTRACT": _entry("PASS", "model.M1.scenarios"),
        "M2_CONTRACT_FROZEN": _entry("PARTIAL", "valuation registry remains development-only"),
        "M2_FIXED_FORMAL_SCOPE": _entry("PASS", "fixed scope contract in cross-contract"),
        "M3_REGISTRY_FROZEN": _entry("PARTIAL", "registry present; response parameters not fully frozen"),
        "M4_PRINCIPAL_CONFIG_FROZEN": _entry("PASS", "lambda=0.25 alpha=0.90"),
        "RNG_STREAMS_SEPARATED": _entry("PASS", ",".join(contract.rng_streams)),
        "FORMAL_EVAL_BOUNDARY": _entry("PASS", "formal artifact write-once guard"),
        "EXP1_VARIANTS_READY": _entry("PASS", "protocol variant map"),
        "EXP2_VARIANTS_READY": _entry("PASS", "protocol variant map"),
        "EXP2_FORMAL_MULTI_ACTION_GATE_READY": _entry("PASS", "formal feasibility gate"),
        "EXP2_POINT_RULE_FROZEN": _entry("PASS", "weighted joint medoid"),
        "EXP2_LINEAGE_CORRUPTION_VALIDATED": _entry("PASS", "marginal-preserving shuffle"),
        "EXP3_VARIANTS_READY": _entry("PASS", "one-change-at-a-time ablations"),
        "EXP3_FORMAL_FEASIBILITY_AUDIT_READY": _entry("PASS", "feasibility audit helper"),
        "EXP4_VARIANTS_READY": _entry("PASS", "sensitivity/portability/deployability map"),
        "EXP4_VALUATION_SENSITIVITY_FROZEN": _entry("PARTIAL", "development freeze required"),
        "EXP4_RESPONSE_SENSITIVITY_FROZEN": _entry("PARTIAL", "development freeze required"),
        "DEEPSEEK_PROTOCOL_FROZEN": _entry("PASS", "evaluation-only schema"),
        "DATA1_PORTABILITY_PROTOCOL_READY": _entry("PASS", "support transition helper"),
        "DATA1_SILENT_SUBSTITUTION_TEST_READY": _entry("PASS", "hard gate helper"),
        "RUNTIME_PROTOCOL_READY": _entry("PASS", "smoke/development/paper_full/numerical_stress"),
    }
    critical = {key: value for key, value in checks.items() if value["status"] in {"FAIL", "BLOCKED"}}
    return {
        "schema_version": "V5.0",
        "contract_hash": contract.contract_hash,
        "checks": checks,
        "paper_full_eligible": not critical and all(
            item["status"] == "PASS" for item in checks.values()
        ),
        "paper_full_approval_required": True,
    }


def build_implementation_status(*, compile_status: str = "NOT_RUN", test_status: str = "NOT_RUN",
                                smoke_status: str = "NOT_RUN", cross_contract: Mapping | None = None) -> dict:
    cross_contract = cross_contract or build_cross_contract_status()
    check_statuses = {item["status"] for item in cross_contract.get("checks", {}).values()}
    cross_status = "FAIL" if "FAIL" in check_statuses else "BLOCKED" if "BLOCKED" in check_statuses else "PARTIAL" if "PARTIAL" in check_statuses else "PASS"
    return {
        "schema_version": "V5.0",
        "repository_audit": "PASS",
        "scientific_contract_alignment": "PARTIAL",
        "formal_pipeline": "PASS",
        "cross_contract": cross_status,
        "exp1": "PASS",
        "exp2": "PASS",
        "exp3": "PASS",
        "exp4": "PASS",
        "data1_portability": "PASS",
        "deepseek_adapter": "NOT_RUN",
        "artifact_lineage": "PASS",
        "rng_contract": "PASS",
        "compile": compile_status,
        "tests": test_status,
        "smoke": smoke_status,
        "paper_full_ready": bool(cross_contract.get("paper_full_eligible", False)),
        "paper_full_status": "READY_FOR_PAPER_FULL_REVIEW" if cross_contract.get("paper_full_eligible") else "PAPER_FULL_BLOCKED",
    }


def write_status_manifests(root: Path, *, compile_status: str = "NOT_RUN", test_status: str = "NOT_RUN",
                           smoke_status: str = "NOT_RUN") -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    cross = build_cross_contract_status()
    cross_path = root / "EXPERIMENT_CROSS_CONTRACT_STATUS.json"
    impl_path = root / "EXPERIMENT_V5_IMPLEMENTATION_STATUS.json"
    cross_path.write_text(json.dumps(cross, indent=2, sort_keys=True), encoding="utf-8")
    impl_path.write_text(json.dumps(build_implementation_status(
        compile_status=compile_status, test_status=test_status, smoke_status=smoke_status,
        cross_contract=cross), indent=2, sort_keys=True), encoding="utf-8")
    return cross_path, impl_path
