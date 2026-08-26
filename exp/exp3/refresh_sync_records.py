"""Exp3 refresh/sync records (freeze F3, exact vintage, 2026-08-26).

Materializes the manuscript "Rolling Recommendation Refresh and State
Synchronization" endpoints (05_experiment.tex subsec:exp_temporal_process,
eq:exp_anchor / eq:exp_state_vintage / eq:exp_post_replay) from the frozen
Development action-risk records.  No model inference is run: every value is
derived from the frozen per-node x action evaluations (BASE sensitivity) and
the frozen full-cohort decision times.

Rules (frozen):
- One-Shot vs Rolling: t_i^0 is the first node of episode i with at least two
  comparable actions and at least one non-A00 comparable action (eq:exp_anchor).
  One-Shot retains the Top-1 formed at t_i^0; Rolling refreshes to the Top-1
  of the current node.  Top-1 = min J with deterministic tie-break by
  action_id over ranked (J available) actions; A00 is in the comparison set.
- Executable rate: the One-Shot recommendation remains executable at a later
  node when it is still eligible and its J is still available.  No deadline
  data exists, so executability is typed from eligibility + support only and
  is never interpolated or assumed beyond the records.
- State sync: delta in {0,5,10} uses P2 exact_vintage_bindings (decision_time
  exactly t - delta); no nearest-past, no fallback; unmatched nodes are typed
  EXP3B_VINTAGE_NOT_AVAILABLE.  The vintage variant uses the frozen state
  identity of the vintage node (NO_REEVALUATION, NO_INTERPOLATION); the
  ex-post comparison evaluates both selected actions on the current node's
  frozen J rows when both are available.
- eq:exp_post_replay is used only where both actions are J-available at the
  node (common basis).
- Bootstrap: episode resampling unit, 2000 replicates, seed 20260825,
  percentile 95 (frozen spec).

Development-only: safety all zero, paper_result=false, FINAL_TEST_ACCESS_COUNT=0.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from exp.common.context import ExecutionTier, ExperimentContext
from exp.common.official_execution import file_sha256, write_json
from exp.exp3.vintage import exact_vintage_bindings

DEFAULT_OUTPUT = Path("artifacts/experiment/exp3/exp3_refresh_sync_20260826")
ACTION_RISK = Path(
    "artifacts/experiments/exp3/full_development_v1/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
)
COHORT = Path(
    "artifacts/experiment/full_development_inputs_v1/DATA2_FULL_DEVELOPMENT_COHORT.json"
)
OLD_REAL_FAST_EXP3 = (
    "artifacts/real_fast/exp3/exp3_exp3a_one_shot.json",
    "artifacts/real_fast/exp3/exp3_exp3a_rolling.json",
    "artifacts/real_fast/exp3/exp3_exp3b_sync.json",
    "artifacts/real_fast/exp3/exp3_exp3b_state_lag_5.json",
    "artifacts/real_fast/exp3/exp3_exp3b_state_lag_10.json",
)

BOOTSTRAP_SEED = 20260825
BOOTSTRAP_REPLICATES = 2000
SCHEMA_VERSION = "AIR_SLOT_EXP3_REFRESH_SYNC_V1"
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "EXP3_RUNS": 0,
    "PAPER_FULL_RUN": False,
}

COMPARISONS = ("ONE_SHOT_EXECUTABLE", "ROLLING_COMPARABLE", "STATE_SYNC_5", "STATE_SYNC_10")
STATE_SYNC_COMPARISON = {5: "STATE_SYNC_5", 10: "STATE_SYNC_10"}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def select_top1_action(rows: Iterable[dict[str, Any]]) -> str | None:
    """Deterministic Top-1 over ranked actions (min J, tie-break action_id)."""
    ranked = [
        (float(row["residual_risk"]), str(row["action_id"]))
        for row in rows
        if row.get("residual_risk") is not None
        and np.isfinite(float(row["residual_risk"]))
    ]
    if not ranked:
        return None
    ranked.sort()
    return ranked[0][1]


def find_anchor_node(nodes: list[dict[str, Any]]) -> str | None:
    """eq:exp_anchor: first node with >=2 comparable and >=1 non-A00."""
    for node in nodes:
        ranked = [
            row for row in node["action_rows"]
            if row.get("residual_risk") is not None
            and np.isfinite(float(row["residual_risk"]))
        ]
        non_a00 = [row for row in ranked if row["action_id"] != "A00"]
        if len(ranked) >= 2 and non_a00:
            return node["decision_node_id"]
    return None


def _node_frame(base: pd.DataFrame) -> dict[str, dict[str, dict[str, Any]]]:
    """node_id -> action_id -> typed frozen BASE row."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in base.to_dict(orient="records"):
        node = out.setdefault(str(row["decision_node_id"]), {})
        node[str(row["action_id"])] = {
            "action_id": str(row["action_id"]),
            "residual_risk": (
                None if row["conditional_residual_risk"] is None
                else float(row["conditional_residual_risk"])
            ),
            "eligibility_state": str(row["eligibility_state"]),
            "response_support": str(row["response_support"]),
            "diagnostic_support_status": str(row["diagnostic_support_status"]),
        }
    return out


def _ordered_nodes(records: pd.DataFrame, node_frame: dict) -> dict[str, list[dict[str, Any]]]:
    """episode_id -> nodes sorted by (decision_time, decision_node_id)."""
    ordered: dict[str, list[dict[str, Any]]] = {}
    node_cols = ("episode_id", "decision_node_id", "decision_time")
    node_rows = records[list(node_cols)].drop_duplicates()
    for row in node_rows.to_dict(orient="records"):
        node_id = str(row["decision_node_id"])
        ordered.setdefault(str(row["episode_id"]), []).append(
            {
                "episode_id": str(row["episode_id"]),
                "decision_node_id": node_id,
                "decision_time": str(row["decision_time"]),
                "action_rows": list(node_frame[node_id].values()),
            }
        )
    for episode in ordered.values():
        episode.sort(key=lambda item: (item["decision_time"], item["decision_node_id"]))
    return ordered


def build_refresh_node_records(records: pd.DataFrame, node_frame: dict) -> pd.DataFrame:
    """Per-node One-Shot vs Rolling refresh records."""
    rows: list[dict[str, Any]] = []
    for episode_id, nodes in _ordered_nodes(records, node_frame).items():
        anchor_id = find_anchor_node(nodes)
        anchor = next((item for item in nodes if item["decision_node_id"] == anchor_id), None)
        for position, node in enumerate(nodes):
            current_actions = {row["action_id"]: row for row in node["action_rows"]}
            ranked = {
                action_id: row for action_id, row in current_actions.items()
                if row.get("residual_risk") is not None
                and np.isfinite(float(row["residual_risk"]))
            }
            node_assessable = len(ranked) >= 1
            rolling = select_top1_action(node["action_rows"])
            one_shot = select_top1_action(anchor["action_rows"]) if anchor else None
            one_shot_eligible = one_shot_available = one_shot_executable = None
            if anchor and one_shot is not None:
                action_row = current_actions.get(one_shot)
                one_shot_eligible = bool(action_row["eligibility_state"] == "TRUE") if action_row else False
                one_shot_available = one_shot in ranked
                one_shot_executable = bool(one_shot_eligible and one_shot_available)
            rolling_comparable = node_assessable
            difference = None
            if one_shot is not None and rolling is not None:
                difference = one_shot != rolling
            replay_comparable = None
            replay_difference = None
            if one_shot is not None and rolling is not None:
                one_j = ranked.get(one_shot)
                rolling_j = ranked.get(rolling)
                replay_comparable = one_j is not None and rolling_j is not None
                if replay_comparable:
                    replay_difference = float(one_j["residual_risk"]) - float(rolling_j["residual_risk"])
            exclusion = ""
            if anchor is None:
                exclusion = "NO_ONE_SHOT_ANCHOR"
            elif not node_assessable:
                exclusion = "EXP3B_NODE_NOT_ASSESSABLE"
            rows.append(
                {
                    "episode_id": episode_id,
                    "decision_node_id": node["decision_node_id"],
                    "decision_time": node["decision_time"],
                    "node_position_in_episode": position,
                    "is_anchor_node": node["decision_node_id"] == anchor_id,
                    "anchor_node_id": anchor_id,
                    "anchor_time": anchor["decision_time"] if anchor else None,
                    "node_assessable": node_assessable,
                    "one_shot_action_id": one_shot,
                    "rolling_action_id": rolling,
                    "one_shot_action_eligible": one_shot_eligible,
                    "one_shot_action_j_available": one_shot_available,
                    "one_shot_executable": one_shot_executable,
                    "rolling_comparable": rolling_comparable,
                    "selected_action_difference": difference,
                    "post_replay_comparable": replay_comparable,
                    "post_replay_residual_risk_difference": replay_difference,
                    "exclusion_code": exclusion,
                }
            )
    return pd.DataFrame(rows)


def build_state_sync_records(
    records: pd.DataFrame,
    node_frame: dict,
    vintage_by_delta: dict[int, list[dict[str, Any]]],
) -> pd.DataFrame:
    """Per-node x delta in {0,5,10} state-synchronization records."""
    by_node = {
        (str(row["episode_id"]), str(row["decision_node_id"])): row
        for row in records.to_dict(orient="records")
    }
    rows: list[dict[str, Any]] = []
    for delta in (0, 5, 10):
        vintage = vintage_by_delta.get(delta) or []
        vintage_map = {
            (str(item["episode_id"]), str(item["decision_node_id"])): item
            for item in vintage
        }
        for (episode_id, node_id), current in by_node.items():
            current_actions = node_frame[node_id]
            current_top1 = select_top1_action(current_actions.values())
            if delta == 0:
                vintage_node_id, vintage_time, matched = node_id, current["decision_time"], True
                exclusion = ""
            else:
                item = vintage_map.get((episode_id, node_id))
                if item is None or not item["exact_vintage_match"]:
                    vintage_node_id = vintage_time = None
                    matched = False
                    exclusion = "EXP3B_VINTAGE_NOT_AVAILABLE"
                else:
                    vintage_node_id = item["state_vintage_node_id"]
                    vintage_time = item["state_vintage_time"]
                    matched = True
                    exclusion = ""
            vintage_top1 = None
            if matched and vintage_node_id is not None:
                vintage_actions = node_frame.get(vintage_node_id)
                if vintage_actions is not None:
                    vintage_top1 = select_top1_action(vintage_actions.values())
            difference = None
            if vintage_top1 is not None and current_top1 is not None:
                difference = vintage_top1 != current_top1
            replay_comparable = None
            replay_difference = None
            if vintage_top1 is not None and current_top1 is not None:
                vintage_j = current_actions.get(vintage_top1)
                current_j = current_actions.get(current_top1)
                replay_comparable = bool(
                    vintage_j is not None
                    and current_j is not None
                    and vintage_j.get("residual_risk") is not None
                    and current_j.get("residual_risk") is not None
                )
                if replay_comparable:
                    replay_difference = (
                        float(vintage_j["residual_risk"]) - float(current_j["residual_risk"])
                    )
            rows.append(
                {
                    "episode_id": episode_id,
                    "decision_node_id": node_id,
                    "delta_minutes": delta,
                    "state_vintage_node_id": vintage_node_id,
                    "state_vintage_time": vintage_time,
                    "exact_vintage_match": matched,
                    "exclusion_code": exclusion,
                    "vintage_top1_action_id": vintage_top1,
                    "current_top1_action_id": current_top1,
                    "selected_action_difference_vs_sync": difference,
                    "post_replay_comparable": replay_comparable,
                    "post_replay_residual_risk_difference": replay_difference,
                }
            )
    return pd.DataFrame(rows)


def _bootstrap(
    values: Iterable[float],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float]:
    """Episode-cluster percentile bootstrap (frozen spec semantics)."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        raise ValueError("No finite episode-level values")
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(array), size=(replicates, len(array)))
    means = array[indices].mean(axis=1)
    return {
        "estimate": float(array.mean()),
        "ci_lower": float(np.quantile(means, 0.025)),
        "ci_upper": float(np.quantile(means, 0.975)),
        "episodes": int(len(array)),
    }


def episode_refresh_values(refresh: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (episode_id,), group in refresh.groupby(["episode_id"], sort=True):
        post = group.loc[group["node_position_in_episode"] > 0]
        if post.empty:
            continue
        assessed = post.loc[post["node_assessable"]]
        if assessed.empty:
            continue
        one_shot_values = assessed["one_shot_executable"].astype(float)
        one_shot_values = one_shot_values.loc[one_shot_values.notna()]
        rolling_values = assessed["rolling_comparable"].astype(float)
        compared = post.loc[post["selected_action_difference"].notna()]
        replay = post.loc[post["post_replay_comparable"].astype(bool)]
        rows.append(
            {
                "episode_id": episode_id,
                "comparison": "ONE_SHOT_EXECUTABLE",
                "coverage": float(one_shot_values.mean()) if len(one_shot_values) else np.nan,
                "n_assessed_nodes": int(len(assessed)),
            }
        )
        rows.append(
            {
                "episode_id": episode_id,
                "comparison": "ROLLING_COMPARABLE",
                "coverage": float(rolling_values.mean()),
                "n_assessed_nodes": int(len(assessed)),
            }
        )
        rows.append(
            {
                "episode_id": episode_id,
                "comparison": "SELECTED_ACTION_DIFFERENCE",
                "coverage": (
                    float(compared["selected_action_difference"].astype(float).mean())
                    if len(compared)
                    else np.nan
                ),
                "n_assessed_nodes": int(len(compared)),
            }
        )
        rows.append(
            {
                "episode_id": episode_id,
                "comparison": "POST_REPLAY_COMPARABLE",
                "coverage": (
                    float(replay["post_replay_comparable"].astype(float).mean())
                    if len(replay)
                    else np.nan
                ),
                "n_assessed_nodes": int(len(replay)),
            }
        )
        rows.append(
            {
                "episode_id": episode_id,
                "comparison": "MEAN_POST_REPLAY_DIFFERENCE",
                "coverage": (
                    float(replay["post_replay_residual_risk_difference"].mean())
                    if len(replay)
                    else np.nan
                ),
                "n_assessed_nodes": int(len(replay)),
            }
        )
    return pd.DataFrame(rows)


def episode_state_sync_values(state_sync: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (episode_id,), group in state_sync.groupby(["episode_id"], sort=True):
        for delta in (5, 10):
            cell = group.loc[group["delta_minutes"] == delta]
            coverage = (
                float(cell["exact_vintage_match"].astype(float).mean())
                if len(cell)
                else np.nan
            )
            rows.append(
                {
                    "episode_id": episode_id,
                    "comparison": STATE_SYNC_COMPARISON[delta],
                    "coverage": coverage,
                    "n_assessed_nodes": int(len(cell)),
                }
            )
    return pd.DataFrame(rows)


def summary_from_values(episode_values: pd.DataFrame) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for comparison, group in episode_values.groupby("comparison", sort=False):
        values = group["coverage"]
        finite = values.loc[values.notna()]
        if finite.empty:
            out.append(
                {
                    "comparison": comparison,
                    "coverage": None,
                    "ci_lower": None,
                    "ci_upper": None,
                    "episodes": 0,
                    "assessed_nodes": int(group["n_assessed_nodes"].sum()),
                    "unavailable_nodes": 0,
                }
            )
            continue
        estimate = _bootstrap(finite)
        out.append(
            {
                "comparison": comparison,
                "coverage": estimate["estimate"],
                "ci_lower": estimate["ci_lower"],
                "ci_upper": estimate["ci_upper"],
                "episodes": estimate["episodes"],
                "assessed_nodes": int(group["n_assessed_nodes"].sum()),
                "unavailable_nodes": int(len(group) - len(finite)),
            }
        )
    return pd.DataFrame(out)


def _load_base_rows(root: Path, action_risk: Path) -> pd.DataFrame:
    columns = (
        "episode_id", "decision_node_id", "action_id",
        "response_sensitivity", "eligibility_state", "response_support",
        "diagnostic_support_status", "conditional_residual_risk",
        "conditional_diagnostic_rank",
    )
    frame = pd.read_parquet(action_risk, columns=list(columns))
    frame = frame.loc[frame["response_sensitivity"] == "BASE"].copy()
    _require(len(frame) > 0, "EXP3_REFRESH_BASE_ROWS_EMPTY")
    return frame


def _top1_parity(frame: pd.DataFrame) -> None:
    """Stored frozen rank-1 must equal recomputed min-J tie-break Top-1."""
    ranked = frame.loc[frame["conditional_residual_risk"].notna()].copy()
    recomputed = (
        ranked.sort_values(["conditional_residual_risk", "action_id"])
        .groupby(["episode_id", "decision_node_id"], sort=False)["action_id"]
        .first()
        .rename("recomputed_top1")
    )
    stored = ranked.loc[ranked["conditional_diagnostic_rank"] == 1].set_index(
        ["episode_id", "decision_node_id"]
    )["action_id"]
    merged = pd.concat([stored, recomputed], axis=1, join="inner")
    _require(len(merged) == len(stored), "EXP3_REFRESH_TOP1_PARITY_INCOMPLETE")
    _require(bool((merged["action_id"] == merged["recomputed_top1"]).all()), "EXP3_REFRESH_TOP1_PARITY_DRIFT")


def run(
    *, root: Path, output_root: Path | None = None,
    action_risk: Path | None = None,
) -> dict[str, Path]:
    action_risk = (action_risk or root / ACTION_RISK).resolve()
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    _require(root in output_root.parents, "EXP3_REFRESH_OUTPUT_OUTSIDE_PROJECT")
    records = _load_base_rows(root, action_risk)
    _top1_parity(records)

    node_frame = _node_frame(records)
    _require(
        len(node_frame) == int(records["decision_node_id"].nunique()),
        "EXP3_REFRESH_NODE_FRAME_INCOMPLETE",
    )

    cohort = json.loads((root / COHORT).read_text(encoding="utf-8"))
    nodes = tuple(dict(item) for item in cohort["decision_nodes"])
    decision_time_by_node = {
        str(item["decision_node_id"]): str(item["decision_time"])
        for item in nodes
    }
    records["decision_time"] = records["decision_node_id"].map(decision_time_by_node)
    _require(records["decision_time"].notna().all(), "EXP3_REFRESH_DECISION_TIME_MAP_INCOMPLETE")
    context = ExperimentContext(
        dataset_id="DATA2",
        split="DEVELOPMENT",
        execution_tier=ExecutionTier.REAL_DATA_FAST,
        cohort=nodes,
        seed=20260813,
        pre_binding={"source_manifest_hash": str(cohort["cohort_hash"])},
        config_hash=str(nodes[0]["config_hash"]),
        scenario_hash=str(cohort["cohort_hash"]),
        final_test_access_count=0,
        paper_full_run=False,
    )
    vintage_by_delta = {
        delta: exact_vintage_bindings(context, lag_minutes=delta)
        for delta in (5, 10)
    }

    refresh = build_refresh_node_records(records, node_frame)
    state_sync = build_state_sync_records(records, node_frame, vintage_by_delta)
    refresh_episode = episode_refresh_values(refresh)
    sync_episode = episode_state_sync_values(state_sync)
    all_episode = pd.concat([refresh_episode, sync_episode], ignore_index=True)
    all_summary = summary_from_values(all_episode)
    figure_episode = all_episode.loc[all_episode["comparison"].isin(COMPARISONS)]
    figure_summary = all_summary.loc[all_summary["comparison"].isin(COMPARISONS)]

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "refresh_records": output_root / "EXP3_REFRESH_RECORDS_DEVELOPMENT_ONLY.parquet",
        "refresh_records_csv": output_root / "EXP3_REFRESH_RECORDS_DEVELOPMENT_ONLY.csv",
        "state_sync_records": output_root / "EXP3_STATE_SYNC_RECORDS_DEVELOPMENT_ONLY.parquet",
        "state_sync_records_csv": output_root / "EXP3_STATE_SYNC_RECORDS_DEVELOPMENT_ONLY.csv",
        "refresh_episode": output_root / "EXP3_REFRESH_EPISODE_VALUES_DEVELOPMENT_ONLY.csv",
        "state_sync_episode": output_root / "EXP3_STATE_SYNC_EPISODE_VALUES_DEVELOPMENT_ONLY.csv",
        "figure_episode": output_root / "EXP3_FIGURE7A_EPISODE_VALUES_DEVELOPMENT_ONLY.csv",
        "figure_summary": output_root / "EXP3_FIGURE7A_SUMMARY_DEVELOPMENT_ONLY.csv",
        "summary": output_root / "EXP3_REFRESH_SYNC_SUMMARY_DEVELOPMENT_ONLY.csv",
        "manifest": output_root / "EXP3_REFRESH_SYNC_MANIFEST_DEVELOPMENT_ONLY.json",
    }
    refresh.to_parquet(paths["refresh_records"], index=False)
    refresh.to_csv(paths["refresh_records_csv"], index=False)
    state_sync.to_parquet(paths["state_sync_records"], index=False)
    state_sync.to_csv(paths["state_sync_records_csv"], index=False)
    refresh_episode.to_csv(paths["refresh_episode"], index=False)
    sync_episode.to_csv(paths["state_sync_episode"], index=False)
    figure_episode.to_csv(paths["figure_episode"], index=False)
    figure_summary.to_csv(paths["figure_summary"], index=False)
    all_summary.to_csv(paths["summary"], index=False)

    superseded = []
    for relative in OLD_REAL_FAST_EXP3:
        old_path = root / relative
        if old_path.is_file():
            superseded.append(
                {
                    "path": relative,
                    "sha256": file_sha256(old_path),
                    "reason": (
                        "pre-P2 lag semantics (nearest-past selection) on the 69-node pilot "
                        "cohort; decision endpoints NOT_RUN (BLOCKED_ANCHOR_ACTION_COVERAGE). "
                        "Superseded by F3 exact-vintage full-cohort materialization; "
                        "numerical differences are expected by design."
                    ),
                }
            )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "dataset": "DATA2",
        "split": "DEVELOPMENT",
        "status": "MATERIALIZED",
        "episode_count": int(records["episode_id"].nunique()),
        "node_count": int(records["decision_node_id"].nunique()),
        "rules": {
            "anchor_rule": "EQ_EXP_ANCHOR_FIRST_NODE_TWO_COMPARABLE_AND_ONE_NON_A00",
            "selection_rule": "MIN_J_LAMBDA_0_25_ALPHA_0_90_TIE_ACTION_ID_A00_REQUIRED",
            "vintage_rule": "F3_EXACT_DECISION_TIME_T_MINUS_DELTA_NO_FALLBACK_NO_NEAREST_PAST",
            "vintage_exclusion_code": "EXP3B_VINTAGE_NOT_AVAILABLE",
            "vintage_identity_rule": (
                "FROZEN_PRIOR_STATE_IDENTITY_NO_REEVALUATION_NO_INTERPOLATION"
            ),
            "executability_rule": (
                "ELIGIBILITY_TRUE_AND_J_AVAILABLE_NO_DEADLINE_DATA_NO_INTERPOLATION"
            ),
            "post_replay_rule": "EQ_EXP_POST_REPLAY_COMMON_J_BASIS_ONLY",
            "bootstrap": {
                "resampling_unit": "EPISODE",
                "replicates": BOOTSTRAP_REPLICATES,
                "seed": BOOTSTRAP_SEED,
                "ci_method": "PERCENTILE_95",
            },
        },
        "endpoints": {
            "one_shot_executable_rate": (
                "PROPORTION_OF_ANCHOR_RECOMMENDATIONS_STILL_EXECUTABLE_AS_AGED"
            ),
            "selected_action_difference": "ONE_SHOT_TOP1_VS_ROLLING_TOP1",
            "post_replay": "EQ_EXP_POST_REPLAY_COMMON_BASIS_RESIDUAL_RISK_DIFFERENCE",
            "state_sync": "SELECTED_ACTION_DIFFERENCE_DELTA_5_10_VS_DELTA_0",
        },
        "superseded_artifacts": superseded,
        "input_hashes": {
            "action_risk": file_sha256(action_risk),
            "cohort": file_sha256(root / COHORT),
        },
        "safety": dict(SAFETY),
        "paper_result": False,
        "outputs": {
            name: str(path.relative_to(root)) for name, path in paths.items()
        },
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

