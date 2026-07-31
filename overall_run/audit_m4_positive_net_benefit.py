from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.m4_pnb_audit import run_audit


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Read-only M4 positive-net-benefit and parameter audit"
    )
    command.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "output" / "fast",
        help="Frozen Fast run directory",
    )
    command.add_argument(
        "--audit-id",
        default=None,
        help="Isolated audit identifier; defaults to M4_PNB_AUDIT_<timestamp>",
    )
    command.add_argument(
        "--mc-samples",
        type=int,
        default=4096,
        help="Isolated M3 audit budget; must be a multiple of formal 256",
    )
    return command


def main() -> int:
    args = parser().parse_args()
    audit_id = args.audit_id or f"M4_PNB_AUDIT_{datetime.now():%Y%m%d_%H%M%S}"
    try:
        result = run_audit(args.run_dir, audit_id, args.mc_samples)
        print("M4 PNB formula identity: PASS")
        print(
            "q max error="
            f"{result['identity']['positive_net_benefit_probability_max_abs_error']:.3g}; "
            f"gate disagreements={result['identity']['gate_disagreement_count']}; "
            f"candidate disagreements={result['identity']['candidate_disagreement_count']}"
        )
        print(
            f"MC {result['mc_stability']['formal_samples']} vs "
            f"{result['mc_stability']['audit_samples']}: "
            f"gate flip rate={result['mc_stability']['gate_flip_rate']:.4%}"
        )
        print("Parameter sensitivity: OFFLINE COUNTERFACTUAL DIAGNOSTIC")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        print(f"M4_PNB_AUDIT_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
