"""Bind the paper positioning file to the current Exp1--Exp4 readiness.

This is a non-executing claim/contract audit.  It prevents Exp3 from being
described as causal action-effect estimation and keeps the central chain and
experiment questions explicit without changing any experiment implementation.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.common.identity import content_id


POSITIONING = Path("codex_framework/定位.md")
CHAIN = "E -> S -> C -> CU -> RMB -> risk -> decision"
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
            raise RuntimeError(f"PAPER_POSITIONING_ALIGNMENT_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(path)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/paper_positioning_alignment_v1").resolve()
    positioning_path = root / POSITIONING
    if not positioning_path.is_file():
        raise RuntimeError("PAPER_POSITIONING_SOURCE_MISSING")
    positioning_text = positioning_path.read_text(encoding="utf-8")
    if "为什么要跨阶段共享信息和状态依赖" not in positioning_text:
        raise RuntimeError("PAPER_POSITIONING_RESEARCH_QUESTION_MISSING")
    required_terms = ("4.1", "4.2", "4.3", "4.4", "framework")
    if any(term not in positioning_text for term in required_terms):
        raise RuntimeError("PAPER_POSITIONING_EXPERIMENT_STRUCTURE_INCOMPLETE")

    report = {
        "schema_version": "AIR_SLOT_PAPER_POSITIONING_ALIGNMENT_V1",
        "status": "POSITIONING_BOUND_NO_EXPERIMENT_DEFINITION_CHANGE",
        "positioning_source": {"path": POSITIONING.as_posix(), "sha256": _hash(positioning_path)},
        "research_objective": "Why global information sharing and state dependency are necessary in rolling airline disruption recovery, and how the proposed decision chain realizes this.",
        "central_chain": CHAIN,
        "experiment_alignment": {
            "Exp1": {
                "question": "necessity of global information sharing and historical state dependency",
                "implementation_boundary": "information/history ablations only; no representation-granularity reinterpretation",
                "status": "BOUND_TO_EXISTING_EXP1_CONTRACT",
            },
            "Exp2": {
                "question": "necessity of the proposed consequence representation and risk construction",
                "implementation_boundary": "POINT/MARGINAL/JOINT and SCALAR/3CHANNEL/7COMP representation sensitivity under one common chain",
                "status": "M4_INTERNAL_LOSS_READY_M3_CONDITIONAL_GATE_REMAINS",
            },
            "Exp3": {
                "question": "necessity of the proposed sequential decision process",
                "implementation_boundary": "decision refresh, state synchronization, chain consistency, and conditional residual-risk ranking",
                "forbidden_reinterpretation": "causal action-effect estimation or empirical action effectiveness",
                "non_a00_status": "SCENARIO_CONDITIONED_DECISION_CANDIDATES",
                "status": "FORMAL_COHORT_BLOCKED",
            },
            "Exp4": {
                "question": "necessary performance and generalization evaluation",
                "implementation_boundary": "predictive adequacy, operational validity, portability, and computation",
                "status": "PREDICTIVE_ARTIFACTS_BLOCKED",
            },
        },
        "claim_guardrails": {
            "causal_action_effect_claim": False,
            "real_currency_claim": False,
            "monetary_ground_truth_claim": False,
            "authoritative_ranking_claim": False,
            "universal_optimality_claim": False,
            "passenger_completeness_claim": False,
            "conditional_ranking_interpretation": "decision-chain consistency and residual-risk sensitivity only",
        },
        "required_followup": [
            "retain M3 non-A00 responses as scenario-conditioned candidates",
            "report Exp3 rankings as conditional/non-authoritative when formal support permits",
            "keep unsupported passenger itinerary/service components explicit ABSTAIN",
            "do not rename internal-loss sensitivity as observed RMB cost or causal action effect",
        ],
        "safety": dict(SAFETY),
    }
    report["artifact_hash"] = content_id(report)
    report_path = output_root / "AIR_SLOT_PAPER_POSITIONING_ALIGNMENT.json"
    _write(report_path, report)
    manifest = {
        "schema_version": "AIR_SLOT_PAPER_POSITIONING_ALIGNMENT_MANIFEST_V1",
        "status": report["status"],
        "positioning_source": POSITIONING.as_posix(),
        "positioning_sha256": _hash(positioning_path),
        "report": str(report_path.resolve()),
        "report_hash": report["artifact_hash"],
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "AIR_SLOT_PAPER_POSITIONING_ALIGNMENT_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"report": report_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit manuscript positioning against current experiment readiness.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("AIR_SLOT_PAPER_POSITIONING_ALIGNMENT_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
