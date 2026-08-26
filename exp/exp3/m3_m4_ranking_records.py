"""M3 non-A00 / M4 production comparison and ranking records (V3 T4, 2026-08-26).

Materializes the per-node action comparison/ranking table from the frozen
Exp3 full-development action-risk records (1769 nodes x 23 actions x 3 bands).
No model inference is run: every value is carried from the frozen parquet or
derived from its frozen ranking semantics.

Frozen rules (PAPER_OUTPUT_SPEC_V1.json, registry v2, F7/F8):
- Ranking objective J = conditional_residual_risk over the frozen five-anchor
  constructed-EUR subset; min J with deterministic tie-break by action_id
  (ascending); A00 is always in the comparison set.
- F7: P_itinerary / P_service are ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY;
  event counts never enter J, are never zero-filled, and carry no monetary value.
- F8: RMB is not instantiated; no beta_k^RMB value exists anywhere.
- Wording discipline: this table is a model-derived ordering under frozen
  declared assumptions only; no causal or empirical-effect claim is made.
- Development-only: safety all zero, paper_result=false, FINAL_TEST_ACCESS_COUNT=0.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from exp.common.official_execution import file_sha256, write_json

DEFAULT_OUTPUT = Path("artifacts/experiment/m3m4/m3_m4_comparison_ranking_20260826")
ACTION_RISK = Path(
    "artifacts/experiments/exp3/full_development_v1/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
)
REGISTRY_V2 = Path("registries/m4_eur_mapping_assumption_grounded_v2.json")
SPEC_V1 = Path("codex_framework/PAPER_OUTPUT_SPEC_V1.json")

SCHEMA_VERSION = "AIR_SLOT_M3M4_COMPARISON_RANKING_V1"
BAND_SCALE_FACTOR = {"LOW": 0.5, "BASE": 1.0, "HIGH": 2.0}
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "EXPERIMENT_RERUNS": 0,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def recompute_rank(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Frozen Top-1 semantics: min J, tie-break action_id, J-available only."""
    comparable = [row for row in rows if pd.notna(row["residual_risk_objective"])]
    comparable.sort(key=lambda row: (row["residual_risk_objective"], row["action_id"]))
    return {row["action_id"]: rank for rank, row in enumerate(comparable, start=1)}


def materialize_records(source: pd.DataFrame) -> pd.DataFrame:
    """Carry frozen fields and derive rank_position/top1 per node x band."""
    rows: list[dict[str, Any]] = []
    grouped = source.groupby(["decision_node_id", "response_sensitivity"], sort=False)
    for (node_id, band), group in grouped:
        action_rows = [
            {
                "action_id": row["action_id"],
                "residual_risk_objective": row["conditional_residual_risk"],
            }
            for _, row in group.iterrows()
        ]
        ranks = recompute_rank(action_rows)
        for _, row in group.iterrows():
            action_id = row["action_id"]
            rank = ranks.get(action_id)
            rows.append(
                {
                    "episode_id": row["episode_id"],
                    "decision_node_id": node_id,
                    "action_id": action_id,
                    "action_family": row["action_family"],
                    "band": band,
                    "band_scale_factor": BAND_SCALE_FACTOR[band],
                    "eligibility_state": row["eligibility_state"],
                    "response_support": row["response_support"],
                    "diagnostic_support_status": row["diagnostic_support_status"],
                    "expected_constructed_eur": row["conditional_expected_constructed_eur"],
                    "constructed_eur_cvar_alpha": row["conditional_constructed_eur_cvar_alpha"],
                    "residual_risk_objective": row["conditional_residual_risk"],
                    "rank_position": rank,
                    "top1": rank == 1 if rank is not None else None,
                    "p_itinerary_event_count": row["p_itinerary_event_count"],
                    "p_service_event_count": row["p_service_event_count"],
                    "pending_monetary_event_status": row["pending_monetary_event_status"],
                    "ranking_authority": row["ranking_authority"],
                    "monetary_ground_truth_claim": row["monetary_ground_truth_claim"],
                    "causal_action_effect_claim": row["causal_action_effect_claim"],
                }
            )
    records = pd.DataFrame(rows)
    # Re-derive the frozen rank column independently and require exact agreement.
    frozen = source.set_index(
        ["decision_node_id", "response_sensitivity", "action_id"]
    )["conditional_diagnostic_rank"]
    recomputed = records.set_index(
        ["decision_node_id", "band", "action_id"]
    )["rank_position"]
    _require(
        frozen.reindex(recomputed.index).equals(recomputed.rename("conditional_diagnostic_rank")),
        "M3M4_RANK_MISMATCH_WITH_FROZEN_RANK",
    )
    return records


def top1_summary(records: pd.DataFrame) -> pd.DataFrame:
    ranked = records[records["top1"].astype("boolean").fillna(False)]
    rows = []
    for (node_id, band), group in ranked.groupby(["decision_node_id", "band"], sort=False):
        row = group.iloc[0]
        rows.append(
            {
                "decision_node_id": node_id,
                "band": band,
                "top1_action_id": row["action_id"],
                "top1_residual_risk_objective": row["residual_risk_objective"],
                "top1_expected_constructed_eur": row["expected_constructed_eur"],
                "n_comparable_actions": int(group["rank_position"].nunique()),
                "support_status": row["diagnostic_support_status"],
            }
        )
    return pd.DataFrame(rows)


def aggregate_stats(records: pd.DataFrame, summary: pd.DataFrame) -> dict[str, Any]:
    nodes = records["decision_node_id"].nunique()
    per_band: dict[str, Any] = {}
    for band, group in summary.groupby("band", sort=False):
        per_band[band] = {
            "ranked_nodes": int(group["decision_node_id"].nunique()),
            "top1_a00_share": float((group["top1_action_id"] == "A00").mean()),
        }
    return {
        "node_count": int(nodes),
        "action_count": int(records["action_id"].nunique()),
        "band_count": int(records["band"].nunique()),
        "record_count": int(len(records)),
        "ranked_nodes": int(summary["decision_node_id"].nunique()),
        "unranked_nodes": int(nodes - summary["decision_node_id"].nunique()),
        "top1_by_band": per_band,
    }


def run(
    *, root: Path, output_root: Path | None = None,
    action_risk: Path | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    action_risk = (action_risk or root / ACTION_RISK).resolve()
    _require(action_risk.is_file(), "M3M4_SOURCE_PARQUET_MISSING")
    _require((root / REGISTRY_V2).is_file(), "M3M4_REGISTRY_V2_MISSING")
    _require((root / SPEC_V1).is_file(), "M3M4_SPEC_V1_MISSING")

    registry = json.loads((root / REGISTRY_V2).read_text(encoding="utf-8"))
    components = {c["component_id"]: c for c in registry["ops_components"]}
    _require(
        components["P_itinerary"]["anchor_status"] == "ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY",
        "M3M4_F7_P_ITINERARY_NOT_ABSTAIN",
    )
    _require(
        components["P_service"]["anchor_status"] == "ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY",
        "M3M4_F7_P_SERVICE_NOT_ABSTAIN",
    )
    _require(
        registry["rmb_reporting_system"] == "NOT_INSTANTIATED_NO_BETA_K_RMB",
        "M3M4_F8_RMB_NOT_ABSTAIN",
    )

    source = pd.read_parquet(action_risk)
    _require(int(source["decision_node_id"].nunique()) == 1769, "M3M4_NODE_COUNT_INVALID")
    _require(
        len(source) == 1769 * 23 * len(BAND_SCALE_FACTOR),
        "M3M4_SOURCE_CARDINALITY_INVALID",
    )

    records = materialize_records(source)
    _require(len(records) == len(source), "M3M4_RECORD_CARDINALITY_INVALID")

    # A00 must be in the comparison set for every node x band that has any
    # comparable action (sample-level identity; frozen selection rule).
    ranked = records[records["top1"].astype("boolean").fillna(False)]
    _require(
        int(ranked["decision_node_id"].nunique()) == 1765,
        "M3M4_RANKED_NODE_COUNT_INVALID",
    )
    a00_top1 = ranked.groupby(["decision_node_id", "band"], sort=False)["action_id"].apply(
        lambda values: list(values) == ["A00"]
    )
    _require(bool(a00_top1.all()), "M3M4_TOP1_NOT_A00")

    summary = top1_summary(records)
    stats = aggregate_stats(records, summary)

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "records": output_root / "M3M4_COMPARISON_RANKING_RECORDS_DEVELOPMENT_ONLY.parquet",
        "records_csv": output_root / "M3M4_COMPARISON_RANKING_RECORDS_DEVELOPMENT_ONLY.csv",
        "top1_summary": output_root / "M3M4_TOP1_SUMMARY_DEVELOPMENT_ONLY.csv",
        "stats": output_root / "M3M4_AGGREGATE_STATS_DEVELOPMENT_ONLY.json",
        "manifest": output_root / "M3M4_MANIFEST_DEVELOPMENT_ONLY.json",
    }
    records.to_parquet(paths["records"], index=False)
    records.to_csv(paths["records_csv"], index=False)
    summary.to_csv(paths["top1_summary"], index=False)
    write_json(paths["stats"], stats)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "dataset": "DATA2",
        "split": "DEVELOPMENT",
        "status": "MATERIALIZED",
        "spec_ref": "PAPER_OUTPUT_SPEC_V1",
        "registry_ref": registry["registry_id"],
        "episode_count": int(records["episode_id"].nunique()),
        "node_count": 1769,
        "rules": {
            "selection_rule": "MIN_J_LAMBDA_0_25_ALPHA_0_90_TIE_ACTION_ID_A00_REQUIRED",
            "ranking_authority": "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL",
            "f7": "P_ITINERARY_P_SERVICE_ABSTAIN_EVENT_COUNTS_ONLY_NOT_IN_J_NO_ZERO_FILL",
            "f8": "RMB_NOT_INSTANTIATED_NO_BETA_K_RMB",
            "wording_discipline": (
                "FROZEN_DECLARED_ASSUMPTION_MODEL_DERIVED_ORDER_ONLY_NO_CAUSAL_CLAIM"
            ),
        },
        "aggregate": stats,
        "input_hashes": {
            "action_risk": file_sha256(action_risk),
            "registry_v2": file_sha256(root / REGISTRY_V2),
            "spec_v1": file_sha256(root / SPEC_V1),
        },
        "registry_hash": registry["registry_hash"],
        "safety": dict(SAFETY),
        "paper_result": False,
        "outputs": {name: str(path.relative_to(root)) for name, path in paths.items()},
    }
    write_json(paths["manifest"], manifest)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    paths = run(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
