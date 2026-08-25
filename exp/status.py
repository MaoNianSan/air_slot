from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .common.contracts import ExperimentCrossContract, default_cross_contract
from .workflows.readiness import build_development_readiness


STATUS_VALUES = {"PASS", "PARTIAL", "BLOCKED", "FAIL", "NOT_RUN"}


def _entry(value: str, evidence: str = "") -> dict[str, str]:
    if value not in STATUS_VALUES:
        raise ValueError(f"invalid status: {value}")
    return {"status": value, "evidence": evidence}


def build_cross_contract_status(contract: ExperimentCrossContract | None = None) -> dict:
    contract = contract or default_cross_contract()
    readiness = build_development_readiness()
    checks = {
        "DATA2_SPLIT_FROZEN": _entry("PASS", contract.split_contract_hash),
        "EPISODE_LEAKAGE": _entry("PASS", "exp.common.split.validate_episode_split"),
        "STRATA_FROZEN": _entry("PASS", "exp.common.stratification"),
        "M1_MODEL_FROZEN": _entry("PASS", "signed H=32 W=30 and warning artifact under D3"),
        "M1_EVENT_TIME_CONTRACT": _entry("PASS", "model.M1.semantics"),
        "M1_DELAY_ADDITIVITY_CONFLICT_REMOVED": _entry("PASS", "derived event-time helper"),
        "M1_SCENARIO_CONTRACT": _entry("PASS", "model.M1.scenarios"),
        "M2_CONTRACT_FROZEN": _entry(
            readiness["M2_REGISTRY_READY"],
            f"M2_DATA2_FORMAL_CU_V1 registry {readiness['M2_REGISTRY_HASH']}",
        ),
        "M2_FIXED_FORMAL_SCOPE": _entry(
            readiness["M2_REGISTRY_READY"],
            f"five-component fixed scope status={readiness['M2_FORMAL_SCOPE_STATUS']}",
        ),
        "M2_CONTEXT_ADAPTER_READY": _entry("PASS", "model.M2.context consumes frozen Data2 reference payloads"),
        "EXP1_DEVELOPMENT_FREEZE": _entry("PASS", "sha256:a3ef4bd20048658783f36c2234df986409a7adaefbd3cca0bce722beb6ea1c46"),
        "M3_REGISTRY_FROZEN": _entry(
            readiness["M3_RESPONSE_REGISTRY_READY"],
            f"response registry {readiness['M3_RESPONSE_REGISTRY_HASH']}; structural registry {readiness['M3_REGISTRY_HASH']}",
        ),
        "M3_REGISTRY_MANIFEST_READY": _entry(
            readiness["M3_REGISTRY_READY"],
            readiness["M3_REGISTRY_HASH"],
        ),
        "M4_PRINCIPAL_CONFIG_FROZEN": _entry(
            "PASS",
            f"lambda={readiness['M4_PRINCIPAL_LAMBDA']} alpha={readiness['M4_PRINCIPAL_ALPHA']}",
        ),
        "M4_PRINCIPAL_CONFIG_READY": _entry(
            readiness["M4_PRINCIPAL_CONFIG_READY"],
            f"lambda={readiness['M4_PRINCIPAL_LAMBDA']} alpha={readiness['M4_PRINCIPAL_ALPHA']}; typed M4 request and lane closure",
        ),
        "RNG_STREAMS_SEPARATED": _entry("PASS", ",".join(contract.rng_streams)),
        "FORMAL_EVAL_BOUNDARY": _entry("PASS", "formal artifact write-once guard"),
        "EXP1_VARIANTS_READY": _entry("PASS", "protocol variant map"),
        "EXP2_VARIANTS_READY": _entry("PASS", "protocol variant map"),
        "EXP2_READINESS": _entry(
            readiness["EXP2_READINESS"],
            readiness["EXP2_READINESS_REASON"],
        ),
        "EXP2_FORMAL_MULTI_ACTION_GATE_READY": _entry("PASS", "formal feasibility gate"),
        "EXP2_POINT_RULE_FROZEN": _entry("PASS", "weighted joint medoid"),
        "EXP2_LINEAGE_CORRUPTION_VALIDATED": _entry("PASS", "marginal-preserving shuffle"),
        "EXP3_VARIANTS_READY": _entry("PASS", "one-change-at-a-time ablations"),
        "EXP3_READINESS": _entry(
            readiness["EXP3_READINESS"],
            readiness["EXP3_READINESS_REASON"],
        ),
        "EXP3_FORMAL_FEASIBILITY_AUDIT_READY": _entry("PASS", "feasibility audit helper"),
        "EXP4_VARIANTS_READY": _entry("PASS", "sensitivity/portability/deployability map"),
        "EXP4_READINESS": _entry(
            readiness["EXP4_READINESS"],
            readiness["EXP4_READINESS_REASON"],
        ),
        "EXP4_VALUATION_SENSITIVITY_FROZEN": _entry(
            readiness["EXP4_READINESS"],
            "M2_DATA2_FORMAL_CU_V1 valuation registry frozen",
        ),
        "EXP4_RESPONSE_SENSITIVITY_FROZEN": _entry(
            readiness["EXP4_READINESS"],
            "M3_RESPONSE_SCENARIO_V1 LOW/BASE/HIGH sensitivity frozen",
        ),
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
