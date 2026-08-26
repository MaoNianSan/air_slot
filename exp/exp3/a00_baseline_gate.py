"""Fail-closed operational recommendation gate with A00 as a baseline only.

This V2 gate is deliberately downstream of the frozen conditional M3/M4
records.  It does not alter scenario parameters, response draws, rankings, or
the frozen V1 artifacts.  Its only purpose is to prevent a conditional
diagnostic Top-1 (especially A00) from being reported as an operational
recommendation.

A non-A00 action can be recommended only when it is factually eligible at the
decision node, has SUPPORTED response evidence, and has a finite objective.
Otherwise the node is typed as an abstention.  A00 remains visible as the
counterfactual baseline but is never emitted as a recommendation.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd

from exp.common.official_execution import file_sha256, write_json
from model.common.identity import content_id


DEFAULT_ACTION_RISK = Path(
    "artifacts/paper_results_v1/exp3/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
)
DEFAULT_OUTPUT = Path(
    "artifacts/experiment/exp3/a00_baseline_gate_v2_20260826"
)
SCHEMA_VERSION = "AIR_SLOT_A00_BASELINE_GATE_V2"
POLICY_ID = "A00_BASELINE_NOT_RECOMMENDATION_FAIL_CLOSED_V2"
A00 = "A00"
REQUIRED_COLUMNS = frozenset({
    "decision_node_id",
    "response_sensitivity",
    "action_id",
    "eligibility_state",
    "response_support",
    "conditional_residual_risk",
})
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "MODEL_RETRAINED": False,
    "PAPER_FULL_RUN": False,
    "EXPENSIVE_UPSTREAM_RERUNS": 0,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _finite_objective(frame: pd.DataFrame) -> pd.DataFrame:
    objective = pd.to_numeric(frame["conditional_residual_risk"], errors="coerce")
    finite = objective.map(
        lambda value: False if pd.isna(value) else math.isfinite(float(value))
    )
    result = frame.loc[finite].copy()
    # Normalize to numeric before sorting so numeric strings cannot order
    # lexically when callers invoke the gate directly.
    result["conditional_residual_risk"] = objective.loc[finite].astype(float)
    return result


def _diagnostic_top1(frame: pd.DataFrame) -> str | None:
    """Return the frozen conditional diagnostic winner, never a recommendation."""
    comparable = _finite_objective(frame)
    if comparable.empty:
        return None
    ordered = comparable.sort_values(
        ["conditional_residual_risk", "action_id"], kind="stable",
    )
    return str(ordered.iloc[0]["action_id"])


def evaluate_records(records: pd.DataFrame) -> pd.DataFrame:
    """Apply the V2 gate once per decision node and valuation band.

    The returned ``recommended_action_id`` is always non-A00.  The explicit
    abstention states distinguish missing factual eligibility, unsupported
    response evidence, and a missing finite objective without fabricating any
    action availability.
    """
    missing = REQUIRED_COLUMNS - set(records.columns)
    _require(not missing, f"A00_GATE_COLUMNS_MISSING:{sorted(missing)}")

    rows: list[dict[str, Any]] = []
    grouped = records.groupby(["decision_node_id", "response_sensitivity"], sort=True)
    for (node_id, band), group in grouped:
        a00_rows = group[group["action_id"] == A00]
        _require(len(a00_rows) == 1, "A00_GATE_BASELINE_CARDINALITY_INVALID")
        a00 = a00_rows.iloc[0]
        non_a00 = group[group["action_id"] != A00]
        factually_eligible = non_a00[non_a00["eligibility_state"] == "TRUE"]
        supported = factually_eligible[
            factually_eligible["response_support"] == "SUPPORTED"
        ]
        operational = _finite_objective(supported)

        recommendation_status: str
        recommended_action_id: str | None
        recommendation_objective: float | None
        if factually_eligible.empty:
            recommendation_status = "ABSTAIN_NO_FACTUALLY_ELIGIBLE_NON_A00"
            recommended_action_id = None
            recommendation_objective = None
        elif supported.empty:
            recommendation_status = "ABSTAIN_NO_FACTUALLY_SUPPORTED_NON_A00"
            recommended_action_id = None
            recommendation_objective = None
        elif operational.empty:
            recommendation_status = "ABSTAIN_NO_FINITE_SUPPORTED_NON_A00"
            recommended_action_id = None
            recommendation_objective = None
        else:
            ordered = operational.sort_values(
                ["conditional_residual_risk", "action_id"], kind="stable",
            )
            selected = ordered.iloc[0]
            recommendation_status = "RECOMMEND_NON_A00"
            recommended_action_id = str(selected["action_id"])
            recommendation_objective = float(selected["conditional_residual_risk"])

        rows.append({
            "decision_node_id": node_id,
            "response_sensitivity": band,
            "a00_baseline_action_id": A00,
            "a00_baseline_objective": a00["conditional_residual_risk"],
            "conditional_diagnostic_top1_action_id": _diagnostic_top1(group),
            "factual_non_a00_candidate_count": int(len(factually_eligible)),
            "supported_non_a00_candidate_count": int(len(supported)),
            "operational_non_a00_candidate_count": int(len(operational)),
            "recommendation_status": recommendation_status,
            "recommended_action_id": recommended_action_id,
            "recommended_objective": recommendation_objective,
        })

    result = pd.DataFrame(rows)
    _require(
        not (result["recommended_action_id"] == A00).any(),
        "A00_GATE_A00_RECOMMENDATION_FORBIDDEN",
    )
    return result


def summary(result: pd.DataFrame) -> dict[str, Any]:
    status_counts = {
        str(status): int(count)
        for status, count in result["recommendation_status"].value_counts().items()
    }
    return {
        "decision_node_count": int(result["decision_node_id"].nunique()),
        "node_band_count": int(len(result)),
        "recommendation_status_counts": status_counts,
        "non_a00_recommendation_count": int(
            (result["recommendation_status"] == "RECOMMEND_NON_A00").sum()
        ),
        "a00_recommendation_count": 0,
        "conditional_a00_top1_count": int(
            (result["conditional_diagnostic_top1_action_id"] == A00).sum()
        ),
    }


def materialize(
    *, root: Path, action_risk: Path | None = None, output_root: Path | None = None,
) -> dict[str, Path]:
    root = Path(root).resolve()
    action_risk = (action_risk or root / DEFAULT_ACTION_RISK).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    _require(action_risk.is_file(), "A00_GATE_ACTION_RISK_MISSING")

    result = evaluate_records(pd.read_parquet(action_risk))
    result_summary = summary(result)
    output_root.mkdir(parents=True, exist_ok=True)
    records_path = output_root / "A00_BASELINE_GATED_RECOMMENDATIONS_V2.parquet"
    records_csv_path = output_root / "A00_BASELINE_GATED_RECOMMENDATIONS_V2.csv"
    summary_path = output_root / "A00_BASELINE_GATED_RECOMMENDATION_SUMMARY_V2.json"
    manifest_path = output_root / "A00_BASELINE_GATED_RECOMMENDATION_MANIFEST_V2.json"
    result.to_parquet(records_path, index=False)
    result.to_csv(records_csv_path, index=False)
    write_json(summary_path, result_summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "status": "MATERIALIZED_FAIL_CLOSED",
        "scope": "DEVELOPMENT_COHORT_OPERATIONAL_RECOMMENDATION_GATE",
        "paper_result": False,
        "baseline_rule": "A00_COUNTERFACTUAL_BASELINE_NOT_RECOMMENDATION",
        "non_a00_selection_rule": (
            "ELIGIBILITY_TRUE_AND_RESPONSE_SUPPORTED_AND_FINITE_OBJECTIVE_ONLY"
        ),
        "abstention_rule": (
            "UNKNOWN_OR_UNSUPPORTED_NON_A00_NEVER_PROMOTED_TO_A00_RECOMMENDATION"
        ),
        "input": {
            "action_risk": str(action_risk.relative_to(root)).replace("\\", "/"),
            "sha256": file_sha256(action_risk),
        },
        "outputs": {
            "records": records_path.name,
            "records_csv": records_csv_path.name,
            "summary": summary_path.name,
        },
        "summary": result_summary,
        "safety": dict(SAFETY),
    }
    manifest["manifest_hash"] = content_id(manifest)
    write_json(manifest_path, manifest)
    return {
        "records": records_path,
        "records_csv": records_csv_path,
        "summary": summary_path,
        "manifest": manifest_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--action-risk", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    paths = materialize(
        root=root, action_risk=args.action_risk, output_root=args.output_root,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
