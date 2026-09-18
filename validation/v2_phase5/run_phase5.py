"""Phase 5 orchestration: Train support, Development families, draft freeze.

Run:

``python -m validation.v2_phase5.run_phase5``

The runner is Development-only. It never reads or writes
``artifacts/experiment/final_test`` and never pushes.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .common import (
    PHASE_DIR,
    Phase5GuardError,
    assert_development_path,
    load_authorities,
    load_development_bridge,
    load_tail_continuations,
    write_json,
)
from .families import (
    build_consequence_service,
    materialize_family_a,
    materialize_family_b,
)
from .freeze import build_freeze_draft
from .h8 import materialize_h8_sensitivity
from .train_support import materialize_train_support


RUN_SUMMARY_NAME = "PHASE5_RUN_SUMMARY.json"


def run_phase5(
    *,
    output_dir: Path = PHASE_DIR,
    node_limit: int | None = None,
    reuse_h8: bool = True,
    train_support: bool = True,
) -> dict[str, Any]:
    """Execute the Phase 5 pipeline and return the run summary."""

    started = time.perf_counter()
    output_dir = Path(output_dir)
    assert_development_path(output_dir)
    timings: dict[str, float] = {}

    def mark(label: str) -> None:
        timings[label] = round(time.perf_counter() - started, 3)

    authorities = load_authorities()
    mark("load_authorities")
    bridge = load_development_bridge()
    mark("load_development_bridge")
    tails = load_tail_continuations()
    mark("load_tail_continuations")

    if train_support:
        train_payload = materialize_train_support(output_dir=output_dir)
    else:
        train_payload = json.loads(
            (output_dir / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json").read_text(
                encoding="utf-8"
            )
        )
    mark("train_support")

    h8_result = materialize_h8_sensitivity(reuse=reuse_h8)
    mark("h8_sensitivity")

    layer = build_consequence_service(
        authorities=authorities, bridge=bridge, output_dir=output_dir
    )
    mark("consequence_service")
    family_a = materialize_family_a(
        authorities=authorities,
        bridge=bridge,
        tails=tails,
        layer=layer,
        output_dir=output_dir,
        node_limit=node_limit,
    )
    mark("family_a")
    family_b = materialize_family_b(
        authorities=authorities,
        bridge=bridge,
        layer=layer,
        output_dir=output_dir,
        node_limit=node_limit,
    )
    mark("family_b")
    freeze = build_freeze_draft(
        authorities=authorities,
        train_support=train_payload,
        family_a=family_a,
        family_b=family_b,
        h8_result=h8_result,
    )
    mark("freeze_draft")

    summary: dict[str, Any] = {
        "schema_version": "V2_PHASE5_RUN_SUMMARY_V1",
        "status": "PASS",
        "phase": "PHASE_5",
        "artifact_scope": "DEVELOPMENT_ONLY",
        "node_count": family_a.get("node_count"),
        "node_limit": node_limit,
        "train_support": {
            "rotation_count": train_payload.get("rotation_count"),
            "artifact_hash": train_payload.get("artifact_hash"),
        },
        "h8_sensitivity": {
            "status": h8_result.get("status"),
            "manifest_path": h8_result.get("manifest_path"),
            "matched_audit": h8_result.get("matched_audit", {}).get("status"),
        },
        "family_a_hash": family_a.get("artifact_hash"),
        "family_b_hash": family_b.get("artifact_hash"),
        "freeze_draft": freeze,
        "authority_audit": dict(authorities.audit),
        "timings_seconds": timings,
        "final_test_access_count": 1,
        "new_final_test_execution": False,
        "no_final_test_path_read": True,
        "push_performed": False,
        "timings_total_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(output_dir / RUN_SUMMARY_NAME, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="AirSlot V2 Phase 5 runner")
    parser.add_argument("--node-limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=PHASE_DIR)
    parser.add_argument("--no-reuse-h8", action="store_true")
    parser.add_argument("--skip-train-support", action="store_true")
    args = parser.parse_args()
    try:
        summary = run_phase5(
            output_dir=args.output_dir,
            node_limit=args.node_limit,
            reuse_h8=not args.no_reuse_h8,
            train_support=not args.skip_train_support,
        )
    except Phase5GuardError as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, indent=2))
        return 2
    print(json.dumps({"status": summary["status"], "timings": summary["timings_seconds"]}, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["RUN_SUMMARY_NAME", "run_phase5"]
