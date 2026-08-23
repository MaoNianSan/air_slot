"""Ordered AIR SLOT experiment execution up to the current scientific gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exp1_reporting import build_exp1_report
from .workflow import build_phase0_consistency_audit


def run_ordered_execution(root: str | Path = ".", output_path: str | Path | None = None) -> dict[str, Any]:
    """Run available experiment stages in strict Exp1 -> Exp4 order.

    This orchestrator only invokes existing Development/preparation runners. It
    never enables Final Test, paper_full, tuning, or authoritative ranking.
    Scientific blockers are persisted as status records rather than bypassed.
    """
    root = Path(root).resolve()
    records: list[dict[str, Any]] = []
    phase0 = build_phase0_consistency_audit(root)
    records.append({"stage": "Phase0", "status": phase0["status"], "output": str(root / "codex_framework/phase0_consistency_audit.json")})

    exp1 = build_exp1_report(root)
    records.append({
        "stage": "Exp1",
        "status": "COMPLETE_DEVELOPMENT_ONLY",
        "paper_result": False,
        "outputs": exp1,
        "interpretation": "history-conditioned state evidence prepared; no downstream decision claim",
    })

    from exp.exp2.formal_development import run_formal_development
    production_root = root / "artifacts/diagnostics/v5_development_freeze"
    production_manifests = {
        "Exp2": production_root / "EXP2_DEVELOPMENT_V1.json",
        "Exp3": production_root / "EXP3_DEVELOPMENT_V1.json",
        "Exp4": production_root / "EXP4_DEVELOPMENT_V1.json",
    }
    exp2 = run_formal_development(root=root)
    exp2_metrics = json.loads(Path(exp2["metrics"]).read_text(encoding="utf-8"))
    records.append({
        "stage": "Exp2",
        "status": exp2_metrics["status"],
        "paper_result": False,
        "outputs": {key: str(value) for key, value in exp2.items()},
        "blocking_scope": "M3 non-A00 response and M4 mapping/tail downstream metrics remain gated",
        "production_artifact": str(production_manifests["Exp2"]) if production_manifests["Exp2"].is_file() else None,
    })

    from exp.exp3.formal_preparation import prepare_formal_execution as prepare_exp3
    exp3 = prepare_exp3(root=root)
    exp3_readiness = json.loads(Path(exp3["readiness"]).read_text(encoding="utf-8"))
    records.append({
        "stage": "Exp3",
        "status": exp3_readiness["execution_status"],
        "paper_result": False,
        "outputs": {key: str(value) for key, value in exp3.items()},
        "blocking_scope": "no executable non-A00 action for formal multi-action cohort",
        "production_artifact": str(production_manifests["Exp3"]) if production_manifests["Exp3"].is_file() else None,
    })

    from exp.exp4.formal_preparation import prepare_formal_execution as prepare_exp4
    exp4 = prepare_exp4(root=root)
    exp4_readiness = json.loads(Path(exp4["readiness"]).read_text(encoding="utf-8"))
    records.append({
        "stage": "Exp4",
        "status": exp4_readiness["execution_status"],
        "paper_result": False,
        "outputs": {key: str(value) for key, value in exp4.items()},
        "data1": "PASS_BOUNDED_DATA1_EXECUTION",
        "blocking_scope": "Data2 baseline/predictive artifacts are not registered; Data1 remains bounded only",
        "production_artifact": str(production_manifests["Exp4"]) if production_manifests["Exp4"].is_file() else None,
    })

    report = {
        "schema_version": "AIR_SLOT_FORMAL_EXPERIMENT_EXECUTION_STATUS_V1",
        "status": "EXECUTED_TO_CURRENT_SCIENTIFIC_GATES",
        "execution_order": ["Phase0", "Exp1", "Exp2", "Exp3", "Exp4"],
        "records": records,
        "safety": {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "AUTHORITATIVE_RANKING": False,
            "DEVELOPMENT_TUNING": False,
        },
        "scientific_note": "This report distinguishes executed Development/preparation artifacts from paper-level evidence; blocked metrics remain NOT_RUN/ABSTAIN.",
    }
    target = Path(output_path).resolve() if output_path else root / "codex_framework/formal_experiment_execution_status.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_ordered_execution(), ensure_ascii=True, indent=2, sort_keys=True))
