"""Single-entry, fail-closed workflow for the M3 scientific evidence lane.

This orchestrator only materializes and audits Development contracts.  It does
not train, tune, execute Exp2--Exp4, or promote scenario assumptions to
identified action effects.  Existing versioned artifacts are reused; the
workflow report itself is written to a new versioned directory.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from model.common.identity import content_id
from model.M3.registry import PRINCIPAL_IDS

from .action_consequence_literature_mapping import materialize as materialize_consequence
from .action_library_scientific_materialization import materialize as materialize_library
from .conditional_action_support_acceptance import materialize as materialize_conditional_support
from .conditional_support_binding import bind as bind_conditional_support
from exp.m2_cu_rmb_interface_correction import materialize as materialize_m2_rmb
from exp.m4_cu_rmb_readiness_audit import materialize as audit_cu_rmb
from .formal_preparation import prepare_formal_execution as prepare_exp3
from .formal_support_audit import audit as audit_support
from exp.exp4.formal_preparation import prepare_formal_execution as prepare_exp4
from exp.scientific_execution_readiness_reconciliation import reconcile


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
            raise RuntimeError(f"M3_WORKFLOW_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _assert_safety(payload: Any, label: str) -> None:
    """Reject any stage output that indicates execution or unsafe access."""
    if not isinstance(payload, dict):
        return
    safety = payload.get("safety")
    if isinstance(safety, dict):
        if safety.get("FINAL_TEST_ACCESS_COUNT", 0) != 0:
            raise RuntimeError(f"M3_WORKFLOW_FINAL_TEST_NONZERO:{label}")
        if safety.get("FULL", False) is not False:
            raise RuntimeError(f"M3_WORKFLOW_FULL_TRUE:{label}")
        if safety.get("PAPER_FULL_RUN", False) is not False:
            raise RuntimeError(f"M3_WORKFLOW_PAPER_FULL_TRUE:{label}")
        for key, value in safety.items():
            if key.endswith("RUNS") and isinstance(value, (int, float)) and value != 0:
                raise RuntimeError(f"M3_WORKFLOW_EXECUTION_COUNT_NONZERO:{label}:{key}")
    for value in payload.values():
        if isinstance(value, dict):
            _assert_safety(value, label)
        elif isinstance(value, list):
            for item in value:
                _assert_safety(item, label)


def _stage(name: str, fn: Callable[[], dict[str, Path]]) -> dict[str, Any]:
    outputs = fn()
    records = {}
    for key, path in outputs.items():
        path = Path(path)
        payload = _load(path) if path.suffix == ".json" else None
        if payload is not None:
            _assert_safety(payload, name)
        records[key] = {"path": path.as_posix(), "sha256": _hash(path)}
    return {"status": "COMPLETED", "outputs": records}


def run_workflow(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m3_scientific_workflow_v11").resolve()
    stages = {
        "consequence_mapping": _stage("consequence_mapping", lambda: materialize_consequence(root=root)),
        "action_library": _stage("action_library", lambda: materialize_library(root=root)),
        "m2_rmb_interface": _stage("m2_rmb_interface", lambda: materialize_m2_rmb(root=root)),
        "cu_rmb_readiness_audit": _stage("cu_rmb_readiness_audit", lambda: audit_cu_rmb(root=root)),
        "conditional_action_support": _stage("conditional_action_support", lambda: materialize_conditional_support(root=root)),
        "conditional_support_binding": _stage("conditional_support_binding", lambda: bind_conditional_support(root=root)),
        "formal_support_audit": _stage("formal_support_audit", lambda: audit_support(root=root)),
        "exp3_preparation": _stage("exp3_preparation", lambda: prepare_exp3(root=root)),
        "exp4_preparation": _stage("exp4_preparation", lambda: prepare_exp4(root=root)),
        "scientific_reconciliation": _stage("scientific_reconciliation", lambda: reconcile(root=root)),
    }

    library = _load(Path(stages["action_library"]["outputs"]["artifact"]["path"]))
    support = _load(Path(stages["formal_support_audit"]["outputs"]["artifact"]["path"]))
    conditional_support = _load(Path(stages["conditional_action_support"]["outputs"]["artifact"]["path"]))
    conditional_binding = _load(Path(stages["conditional_support_binding"]["outputs"]["artifact"]["path"]))
    cu_rmb_audit = _load(Path(stages["cu_rmb_readiness_audit"]["outputs"]["artifact"]["path"]))
    exp3 = _load(Path(stages["exp3_preparation"]["outputs"]["manifest"]["path"]))
    exp3_readiness = _load(Path(stages["exp3_preparation"]["outputs"]["readiness"]["path"]))
    exp4 = _load(Path(stages["exp4_preparation"]["outputs"]["manifest"]["path"]))
    reconciliation = _load(Path(stages["scientific_reconciliation"]["outputs"]["readiness"]["path"]))
    ids = [row["action_id"] for row in library["action_evidence_table"]]
    report = {
        "schema_version": "M3_SCIENTIFIC_WORKFLOW_REPORT_V2",
        "status": "WORKFLOW_COMPLETED_WITH_SCIENTIFIC_BLOCKERS",
        "scope": "DEVELOPMENT_MATERIALIZATION_AND_READINESS_ONLY",
        "stages": stages,
        "scientific_checks": {
            "action_count": len(ids),
            "action_identity_preserved": tuple(ids) == tuple(PRINCIPAL_IDS),
            "executable_action_ids": support["executable_action_ids"],
            "non_a00_executable_count": len(support["non_a00_executable_action_ids"]),
            "conditional_support_status": conditional_support["status"],
            "conditional_action_count": conditional_support["conditional_action_count"],
            "conditional_scenario_lane": conditional_support["conditional_scenario_lane"],
            "conditional_binding_status": conditional_binding["status"],
            "monetary_chain": conditional_binding["monetary_chain"],
            "cu_rmb_readiness_status": cu_rmb_audit["readiness_status"],
            "cu_rmb_checks_passed": all(cu_rmb_audit["checks"].values()),
            "cu_rmb_mapping_status": cu_rmb_audit["mapping_gate"]["status"],
            "exp3_status": exp3["status"],
            "exp3_execution_status": exp3_readiness.get("execution_status", "UNKNOWN"),
            "exp4_status": exp4["status"],
            "exp4_readiness_status": reconciliation["execution_status"],
        },
        "next_automatic_action": "NONE; stop at M4 CU-to-RMB scientific decision gate and M3 non-A00 response gate",
        "safety": dict(SAFETY),
    }
    report["artifact_hash"] = content_id(report)
    report_path = output_root / "M3_SCIENTIFIC_WORKFLOW_REPORT.json"
    _write(report_path, report)
    manifest = {
        "schema_version": "M3_SCIENTIFIC_WORKFLOW_MANIFEST_V1",
        "status": report["status"],
        "report": str(report_path.resolve()),
        "report_hash": report["artifact_hash"],
        "stages": {name: value["status"] for name, value in stages.items()},
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "M3_SCIENTIFIC_WORKFLOW_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"report": report_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fail-closed M3 scientific workflow.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    run_workflow(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("M3_SCIENTIFIC_WORKFLOW_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
