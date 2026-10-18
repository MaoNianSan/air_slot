"""V2 split-isolation validator (Phase 1).

Verifies that a Development object may reference Train/Calibration/Development
only, and that a Test object may never be reachable from Development (and vice
versa). The checker uses the frozen PRE contract, so the rule that is validated
is the rule the runtime builder uses.

This validator never reads ``artifacts/experiment/final_test`` and does not
change ``FINAL_TEST_ACCESS_COUNT``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.PRE.decision_environment import assert_split_isolation  # noqa: E402
from model.common.decision_contracts import SplitName  # noqa: E402
from model.common.errors import ContractError  # noqa: E402


CASES = (
    {
        "case_id": "DEVELOPMENT_READS_TRAIN_CALIBRATION_DEVELOPMENT",
        "split": "development",
        "referenced_splits": ["train", "calibration", "development"],
        "expected": "PASS",
    },
    {
        "case_id": "DEVELOPMENT_READS_TEST",
        "split": "development",
        "referenced_splits": ["test"],
        "expected": "FAIL",
    },
    {
        "case_id": "DEVELOPMENT_READS_TEST_WITHIN_TRAIN",
        "split": "development",
        "referenced_splits": ["train", "test"],
        "expected": "FAIL",
    },
    {
        "case_id": "TEST_READS_DEVELOPMENT",
        "split": "test",
        "referenced_splits": ["development"],
        "expected": "FAIL",
    },
    {
        "case_id": "TEST_READS_TRAIN_CALIBRATION_TEST",
        "split": "test",
        "referenced_splits": ["train", "calibration", "test"],
        "expected": "PASS",
    },
    {
        "case_id": "TRAIN_READS_DEVELOPMENT",
        "split": "train",
        "referenced_splits": ["development"],
        "expected": "FAIL",
    },
)


def run_cases() -> dict:
    results = []
    for case in CASES:
        try:
            assert_split_isolation(
                split=SplitName(case["split"]),
                referenced_splits=case["referenced_splits"],
            )
            observed = "PASS"
            reason = None
        except ContractError as error:
            observed = "FAIL"
            reason = str(error)
        results.append(
            {
                **case,
                "observed": observed,
                "reason": reason,
                "status": "OK" if observed == case["expected"] else "MISMATCH",
            }
        )
    passed = all(item["status"] == "OK" for item in results)
    return {
        "validator_id": "V2_SPLIT_ISOLATION",
        "scope": "PRE_EVIDENCE_BOUNDARY",
        "final_test_access_count": 0,
        "cases": results,
        "status": "PASS" if passed else "FAIL",
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Validate V2 PRE split isolation")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/diagnostics/v2_phase1/SPLIT_ISOLATION_REPORT.json"),
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    report = run_cases()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
