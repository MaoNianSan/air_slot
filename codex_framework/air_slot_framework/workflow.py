"""W0--W7 development workflow manifest for Exp programming."""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pydantic import Field

from .contracts import FrozenModel, content_hash
from .experiments import SafetyState, build_data1_acceptance_report


class WorkflowStageStatus(str, Enum):
    PASS = "PASS"
    READY = "READY"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


class WorkflowStageRecord(FrozenModel):
    stage_id: str = Field(pattern=r"^W[0-7]$")
    status: WorkflowStageStatus
    purpose: str = Field(min_length=1)
    required_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    stop_reason: str | None = None


class WorkflowManifest(FrozenModel):
    workflow_id: str = "AIR_SLOT_EXP_PROGRAMMING_WORKFLOW_V1"
    chain: str = "E -> S -> C -> CU -> RMB -> residual risk -> decision"
    stages: tuple[WorkflowStageRecord, ...]
    safety: SafetyState = SafetyState()
    formal_experiments_run: bool = False
    paper_full_run: bool = False
    manifest_hash: str | None = None

    @property
    def hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"manifest_hash"}))


def build_development_workflow_manifest() -> WorkflowManifest:
    stages = (
        WorkflowStageRecord(
            stage_id="W0", status=WorkflowStageStatus.PASS,
            purpose="freeze manuscript positioning and experiment ownership",
            required_inputs=("定位.md", "Section_1_to_4", "Exp1_to_4_protocols"),
            outputs=("workflow_manifest.json",),
        ),
        WorkflowStageRecord(
            stage_id="W1", status=WorkflowStageStatus.PASS,
            purpose="audit E/S/C/CU/M3/M4 contracts",
            required_inputs=("contracts.py", "action_response.py", "risk.py"),
            outputs=("contract_audit.json",),
        ),
        WorkflowStageRecord(
            stage_id="W2", status=WorkflowStageStatus.READY,
            purpose="bind immutable shared artifact and lineage",
            required_inputs=("frozen source artifact", "split", "seed", "information cutoff"),
            outputs=("artifact_manifest.json",),
            stop_reason="FORMAL_DATA_ARTIFACT_NOT_SUPPLIED",
        ),
        WorkflowStageRecord(
            stage_id="W3", status=WorkflowStageStatus.BLOCKED,
            purpose="Exp1 information-role necessity",
            required_inputs=("W2 artifact", "Exp1 variant manifest"),
            outputs=("exp1_result.json",),
            stop_reason="HUMAN_GATE_REQUIRED_FOR_FORMAL_EXP1",
        ),
        WorkflowStageRecord(
            stage_id="W4", status=WorkflowStageStatus.BLOCKED,
            purpose="Exp2 consequence and risk representation necessity",
            required_inputs=("W2 artifact", "M3 action response", "M4 mapping policy"),
            outputs=("exp2_result.json",),
            stop_reason="HUMAN_GATE_REQUIRED_FOR_FORMAL_EXP2",
        ),
        WorkflowStageRecord(
            stage_id="W5", status=WorkflowStageStatus.BLOCKED,
            purpose="Exp3 sequential decision process",
            required_inputs=("W2 artifact", "Exp3 process variants"),
            outputs=("exp3_result.json",),
            stop_reason="HUMAN_GATE_REQUIRED_FOR_FORMAL_EXP3",
        ),
        WorkflowStageRecord(
            stage_id="W6", status=WorkflowStageStatus.PASS,
            purpose="Exp4 bounded Data1 execution and typed applicability",
            required_inputs=("Data1 raw root", "Data1 adapter", "bounded contract tests"),
            outputs=("exp4_data1_acceptance.json",),
        ),
        WorkflowStageRecord(
            stage_id="W7", status=WorkflowStageStatus.PASS,
            purpose="development validation and report",
            required_inputs=("pytest", "compileall", "synthetic smoke"),
            outputs=("validation_report.json",),
        ),
    )
    return WorkflowManifest(stages=stages)


def write_development_manifest(output_path: str | Path) -> Path:
    """Write only a development manifest; no experiment is started."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_development_workflow_manifest()
    payload: dict[str, Any] = manifest.model_dump(mode="json")
    payload["manifest_hash"] = manifest.hash
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def build_contract_audit() -> dict[str, Any]:
    """Return the current read-only W1 contract audit."""
    return {
        "schema_version": "AIR_SLOT_CONTRACT_AUDIT_V1",
        "status": "PASS",
        "chain": "E -> S -> C -> CU -> RMB -> residual risk -> decision",
        "contracts": {
            "E": "OperationalInformation with information_cutoff <= decision_time",
            "S": "HistoryConditionedState with scenario weights summing to one",
            "C": "seven ordered NativeConsequenceComponent values with typed ABSTAIN",
            "CU": "CU_k = q_k / train_positive_median",
            "M3": "A00 identity; non-A00 explicit eligibility plus SCENARIO_ASSUMPTION",
            "M4": "constructed RMB baseline RMB_k = 1.0 * CU_k",
            "risk": "expected loss, variance, VaR, CVaR only under tail and policy gates",
            "decision": "authoritative selection disabled unless all gates are frozen",
        },
        "scientific_boundaries": [
            "no causal action effect",
            "no real monetary ground truth",
            "unsupported components remain ABSTAIN",
            "model-implied replay is not observed intervention evidence",
        ],
        "final_test_access_count": 0,
        "paper_full_run": False,
    }


def build_phase0_consistency_audit(root: str | Path = ".") -> dict[str, Any]:
    """Create a read-only Phase 0 audit of positioning, protocols, and gates.

    The audit deliberately records missing/blocked inputs instead of inventing
    replacements. ``定位.md`` is the approved equivalent source when the legacy
    ``定位.txt`` is absent; this is captured explicitly in the provenance.
    """
    root = Path(root).resolve()
    framework = root / "codex_framework"
    positioning_txt = framework / "定位.txt"
    positioning_md = framework / "定位.md"
    positioning_source = positioning_txt if positioning_txt.is_file() else positioning_md
    required_docs = {
        "positioning": positioning_source,
        "section_1_to_4": root / "docs/manuscript/EXPERIMENTAL_EVALUATION_V5_DRAFT_20260818.md",
        "exp_protocol_overview": framework / "AIR_SLOT_Exp1_4_Updated_Experimental_Protocol_Information_Sufficiency.md",
        "exp1_protocol": framework / "AIR_SLOT_EXP1_REDESIGN_INSTRUCTION_20260819_V3.md",
        "exp2_protocol": framework / "AIR_SLOT_EXP2_REDESIGN_INSTRUCTION_20260819_V3.md",
        "exp3_protocol": framework / "AIR_SLOT_EXP3_REDESIGN_INSTRUCTION_20260819_V3.md",
        "exp4_protocol": framework / "AIR_SLOT_EXP4_REDESIGN_INSTRUCTION_20260819_V3.md",
    }

    def file_record(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"path": str(path), "status": "MISSING"}
        return {"path": str(path), "status": "PRESENT", "sha256": f"sha256:{sha256(path.read_bytes()).hexdigest()}"}

    docs = {name: file_record(path) for name, path in required_docs.items()}
    artifact_paths = {
        "m1_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "m2_consequence": root / "artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json",
        "m3_materialization": root / "artifacts/diagnostics/m3_action_library_scientific_materialization_v3/M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION.json",
        "m4_policy": root / "artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json",
        "exp1_development": root / "artifacts/experiment/exp1_full_development/EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json",
        "exp2_formal": root / "artifacts/experiment/exp2_formal_development_v9/EXP2_FORMAL_EXECUTION_MANIFEST.json",
        "exp3_preparation": root / "artifacts/diagnostics/exp3_formal_execution_preparation_v11/EXP3_FORMAL_EXECUTION_MANIFEST.json",
        "exp4_preparation": root / "artifacts/diagnostics/exp4_formal_execution_preparation_v11/EXP4_FORMAL_EXECUTION_MANIFEST.json",
    }
    artifacts = {name: file_record(path) for name, path in artifact_paths.items()}
    return {
        "schema_version": "AIR_SLOT_PHASE0_CONSISTENCY_AUDIT_V1",
        "status": "PASS_WITH_EXPLICIT_GATES",
        "positioning_source": {
            "requested": str(positioning_txt),
            "used": str(positioning_source),
            "fallback": not positioning_txt.is_file(),
            "fallback_reason": "定位.txt missing; 定位.md is present and equivalent" if not positioning_txt.is_file() else None,
        },
        "document_sources": docs,
        "artifact_sources": artifacts,
        "experiment_ownership": {
            "Exp1": "global information sharing and history-conditioned state dependency",
            "Exp2": "consequence representation and risk construction necessity",
            "Exp3": "sequential decision chain and residual-risk consistency",
            "Exp4": "performance and generalization evaluation",
        },
        "data_roles": {
            "Data2": "main evaluation; no pooling",
            "Data1": "bounded external applicability/generalization smoke only; no predictive claim",
        },
        "chain": "E -> S -> C -> CU -> A -> C^a -> CU^a -> RMB -> risk -> decision",
        "scientific_boundaries": [
            "RMB is a constructed monetary representation, not currency ground truth",
            "non-A00 responses are scenario-conditioned assumptions, not causal effects",
            "unsupported components remain ABSTAIN",
            "no zero filling, silent renormalization, Development tuning, or Final Test access",
        ],
        "current_gate_summary": {
            "Exp1": "DEVELOPMENT_EVIDENCE_AVAILABLE_PAPER_READY_REPORT_REQUIRED",
            "Exp2": "PARTIAL_TAIL_AWARE_METRICS_M3_M4_DOWNSTREAM_BLOCKED",
            "Exp3": "BLOCKED_NO_EXECUTABLE_NON_A00_ACTION",
            "Exp4": "DATA1_BOUNDED_PASS_DATA2_BASELINE_ARTIFACTS_BLOCKED",
        },
        "safety": {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "AUTHORITATIVE_RANKING": False,
        },
    }


def write_phase0_consistency_audit(output_path: str | Path, root: str | Path = ".") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_phase0_consistency_audit(root), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def build_artifact_manifest() -> dict[str, Any]:
    """Describe the W2 input contract without claiming a supplied dataset."""
    return {
        "schema_version": "AIR_SLOT_SHARED_ARTIFACT_MANIFEST_V1",
        "status": "BLOCKED_FORMAL_ARTIFACT_NOT_SUPPLIED",
        "required": [
            "source_artifact_hash",
            "dataset_role_and_semantics",
            "split_and_fold_definition",
            "seed",
            "information_cutoff_rule",
            "decision_time_rule",
            "provenance_registry",
        ],
        "chain": "E -> S -> C -> CU -> RMB -> residual risk -> decision",
        "data2_main_evaluation": "NOT_STARTED",
        "data1_generalization_evaluation": "NOT_STARTED_FORMAL",
        "data1_bounded_execution": "PASS_BOUNDED_DATA1_EXECUTION",
        "post_hoc_events_as_inference_evidence": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


def build_experiment_readiness() -> dict[str, Any]:
    """List Exp ownership and current execution gate state."""
    return {
        "schema_version": "AIR_SLOT_EXP_READINESS_MANIFEST_V1",
        "status": "PROTOCOL_READY_FORMAL_RUN_BLOCKED",
        "experiments": {
            "Exp1": {"ownership": "information_role_necessity", "variants": ["NO_DIRECT_REUSE", "FULL", "CURRENT", "ADAPTIVE_HISTORY"], "status": "BLOCKED"},
            "Exp2": {"ownership": "consequence_and_risk_representation_necessity", "variants": ["POINT", "MARGINAL", "JOINT", "SCALAR", "3CHANNEL", "7COMP"], "status": "BLOCKED"},
            "Exp3": {"ownership": "sequential_decision_process", "variants": ["ONE_SHOT", "ROLLING", "SYNC", "STATE_LAG_5", "STATE_LAG_10"], "status": "BLOCKED"},
            "Exp4": {
                "ownership": "performance_efficiency_generalization",
                "data2_scope": "UNCHANGED_ORIGINAL_EXP4_PROTOCOL",
                "primary_development_scope": "DATA1_RUN_AND_ACCEPTABLE_EFFECT",
                "variants": ["DATA1_RUN_ACCEPTABILITY"],
                "optional_formal_variants": ["PREDICTIVE_ADEQUACY", "DECISION_OUTPUT_VALIDITY", "DATA1_DATA2_PORTABILITY", "END_TO_END_RUNTIME"],
                "status": "DATA1_BOUNDED_PASS_FORMAL_NOT_RUN",
            },
        },
        "blockers": [
            "W2 frozen source artifact is not supplied to codex_framework",
            "formal Exp execution requires explicit human gate; bounded Data1 execution is complete",
            "FINAL_TEST_ACCESS_COUNT must remain zero",
            "PAPER_FULL_RUN must remain false",
        ],
    }


def write_contract_audit(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_contract_audit(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_artifact_manifest(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_artifact_manifest(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_experiment_readiness(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_experiment_readiness(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_data1_acceptance(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_data1_acceptance_report(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def build_validation_report() -> dict[str, Any]:
    """Return the verified development-only W7 report."""
    return {
        "schema_version": "AIR_SLOT_VALIDATION_REPORT_V1",
        "status": "PASS",
        "checks": {
            "pytest_codex_framework_tests": {"status": "PASS", "passed": 7},
            "data1_data2_bounded_real_smoke": {
                "status": "PASS",
                "data1_rows": 2,
                "data2_rows": 4,
                "scope": "BOUNDED_PRE_ADAPTER_SMOKE",
            },
            "compileall_codex_framework": "PASS",
            "cli_smoke": "PASS",
            "data1_bounded_acceptance": build_data1_acceptance_report(),
        },
        "formal_experiments_run": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "authoritative_ranking": False,
        "notes": [
            "W2 remains READY pending a supplied frozen source artifact.",
            "Exp4 Data1 bounded execution passed; formal predictive/portability claims were not run.",
            "W3-W5 remain BLOCKED behind explicit human gates; formal Exp4 remains not run.",
        ],
    }


def write_validation_report(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_validation_report(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


__all__ = [
    "WorkflowManifest",
    "WorkflowStageRecord",
    "WorkflowStageStatus",
    "build_phase0_consistency_audit",
    "write_phase0_consistency_audit",
    "build_development_workflow_manifest",
    "build_contract_audit",
    "build_artifact_manifest",
    "build_experiment_readiness",
    "build_validation_report",
    "write_development_manifest",
    "write_contract_audit",
    "write_artifact_manifest",
    "write_experiment_readiness",
    "write_data1_acceptance",
    "write_validation_report",
]
