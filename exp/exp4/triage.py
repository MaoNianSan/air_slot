"""Frozen retrospective fixed-capacity screening primitives for Exp4."""

from __future__ import annotations

from math import ceil

import pandas as pd
import numpy as np
from exp.shared.contracts import SupportedScore
from exp.shared.recovery_priority import compute_no_f_execution_priority

ACTIVE_STAGES = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")


def _top_ids(group: pd.DataFrame, column: str, k: int) -> set[str]:
    return set(
        group.sort_values([column, "decision_node_id"], ascending=[False, True], kind="mergesort")
        .head(k)["decision_node_id"]
    )


def prepare_canonical_events(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = frame.copy()
    data["D"] = data["delay_to_mean_cs"].astype(float)
    data["S_F"] = data[["Z_F_continuity_cs", "Z_F_execution_cs", "Z_F_propagation_cs"]].mean(axis=1)
    data["S_P"] = data[["Z_P_time_cs", "Z_P_itinerary_cs", "Z_P_service_cs"]].mean(axis=1)
    data["S_R"] = data["Z_R_operating_cs"].astype(float)
    data["S_C"] = data[["S_F", "S_P", "S_R"]].mean(axis=1)
    data = data[data.operational_stage.isin(ACTIVE_STAGES)].copy()
    data = data.sort_values(["original_episode_id", "operational_stage", "decision_time", "decision_node_id"])
    canonical = data.groupby(["original_episode_id", "operational_stage"], as_index=False, sort=False).head(1).copy()
    canonical["canonical_event_status"] = canonical.apply(
        lambda row: "SUPPORTED"
        if bool(row.get("support_primary", False))
        and bool(row.get("conditional_aggregate_complete", False))
        and pd.notna(row["D"])
        and pd.notna(row["S_C"])
        else "EXCLUDE_WITH_TYPED_REASON",
        axis=1,
    )
    canonical["canonical_event_exclusion_reason"] = canonical.apply(
        lambda row: ""
        if row["canonical_event_status"] == "SUPPORTED"
        else "PRIMARY_SUPPORT_OR_AGGREGATE_UNSUPPORTED",
        axis=1,
    )
    return canonical.reset_index(drop=True), data.reset_index(drop=True)


def screen(canonical: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    rows = []
    for stage, group in canonical[canonical.canonical_event_status == "SUPPORTED"].groupby("operational_stage", sort=False):
        n = len(group)
        if not n:
            continue
        k = ceil(q * n)
        delay = _top_ids(group, "D", k)
        consequence = _top_ids(group, "S_C", k)
        overlap = len(delay & consequence)
        rows.append({"stage": stage, "q": q, "n": n, "k": k, "overlap": overlap, "slots_reassigned": k - overlap, "reassigned_rate": (k - overlap) / k})
    return pd.DataFrame(rows)


def capture(canonical: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    component_columns = [
        "F_continuity_native_cs", "F_execution_native_cs", "F_propagation_native_cs",
        "P_time_native_cs", "P_itinerary_native_cs", "P_service_native_cs",
        "R_operating_native_cs",
    ]
    rows = []
    for stage, group in canonical[canonical.canonical_event_status == "SUPPORTED"].groupby("operational_stage", sort=False):
        k = ceil(q * len(group))
        selections = {"DELAY": _top_ids(group, "D", k), "CONSEQUENCE": _top_ids(group, "S_C", k)}
        for method, selected in selections.items():
            selected_rows = group[group.decision_node_id.isin(selected)]
            for domain, column in {"F": "S_F", "P": "S_P", "R": "S_R"}.items():
                denom = float(group[column].sum())
                rows.append({"stage": stage, "q": q, "method": method, "measure": domain, "capture": None if denom == 0 else float(selected_rows[column].sum() / denom)})
            for column in component_columns:
                denom = float(group[column].sum())
                rows.append({"stage": stage, "q": q, "method": method, "measure": column.replace("_native_cs", ""), "capture": None if denom == 0 else float(selected_rows[column].sum() / denom)})
    return pd.DataFrame(rows)


def robust_sets(canonical: pd.DataFrame, threshold: int = 4) -> pd.DataFrame:
    group = canonical[canonical.canonical_event_status == "SUPPORTED"].copy()
    group["stage"] = group["operational_stage"]
    views = {
        "F_DOMAIN": "S_F", "P_DOMAIN": "S_P", "R_DOMAIN": "S_R",
        "EQUAL_COMPONENT": None, "NO_F_EXECUTION": None,
    }
    group["EQUAL_COMPONENT"] = group[["Z_F_continuity_cs", "Z_F_execution_cs", "Z_F_propagation_cs", "Z_P_time_cs", "Z_P_itinerary_cs", "Z_P_service_cs", "Z_R_operating_cs"]].mean(axis=1)
    def shared_no_exec(row: pd.Series) -> float:
        components = {
            "F_continuity": SupportedScore(value=float(row["Z_F_continuity_cs"]), support="SUPPORTED"),
            "F_execution": SupportedScore(value=float(row["Z_F_execution_cs"]), support="SUPPORTED"),
            "F_propagation": SupportedScore(value=float(row["Z_F_propagation_cs"]), support="SUPPORTED"),
            "P_time": SupportedScore(value=float(row["Z_P_time_cs"]), support="SUPPORTED"),
            "P_itinerary": SupportedScore(value=float(row["Z_P_itinerary_cs"]), support="SUPPORTED"),
            "P_service": SupportedScore(value=float(row["Z_P_service_cs"]), support="SUPPORTED"),
            "R_operating": SupportedScore(value=float(row["Z_R_operating_cs"]), support="SUPPORTED"),
        }
        result = compute_no_f_execution_priority(components)
        if result.value is None:
            raise ValueError("EXP4_NO_F_EXECUTION_UNSUPPORTED")
        return float(result.value)

    group["NO_F_EXECUTION"] = group.apply(shared_no_exec, axis=1)
    for name, column in (("F_EMPHASIS_050_025_025", None), ("P_EMPHASIS_025_050_025", None), ("R_EMPHASIS_025_025_050", None)):
        weights = {"F_EMPHASIS_050_025_025": (0.50, 0.25, 0.25), "P_EMPHASIS_025_050_025": (0.25, 0.50, 0.25), "R_EMPHASIS_025_025_050": (0.25, 0.25, 0.50)}[name]
        group[name] = weights[0] * group.S_F + weights[1] * group.S_P + weights[2] * group.S_R
        views[name] = name
    outputs = []
    for stage, stage_group in group.groupby("stage", sort=False):
        counts = {node: 0 for node in stage_group.decision_node_id}
        k = max(1, ceil(.10 * len(stage_group)))
        for name, column in views.items():
            ranking = column or name
            for node in _top_ids(stage_group, ranking, k):
                counts[node] += 1
        out = stage_group[["stage", "original_episode_id", "decision_node_id", "D", "S_C"]].copy()
        out["view_count"] = out.decision_node_id.map(counts)
        out["robust_high_consequence"] = out.view_count >= threshold
        outputs.append(out)
    return pd.concat(outputs, ignore_index=True) if outputs else group.iloc[0:0]


def pareto_reversals(canonical: pd.DataFrame, q: float = .10) -> pd.DataFrame:
    rows = []
    for stage, group in canonical[canonical.canonical_event_status == "SUPPORTED"].groupby("operational_stage", sort=False):
        k = ceil(q * len(group))
        components = ["Z_F_continuity_cs", "Z_F_execution_cs", "Z_F_propagation_cs", "Z_P_time_cs", "Z_P_itinerary_cs", "Z_P_service_cs", "Z_R_operating_cs"]
        for method, selected in {"DELAY": set(group.nlargest(k, "D").decision_node_id), "CONSEQUENCE": set(group.nlargest(k, "S_C").decision_node_id)}.items():
            dominated = 0
            for _, row in group.iterrows():
                if row.decision_node_id in selected:
                    for _, other in group.iterrows():
                        if other.decision_node_id not in selected and all(pd.notna(other[c]) and pd.notna(row[c]) for c in components) and all(other[c] >= row[c] for c in components) and any(other[c] > row[c] for c in components):
                            dominated += 1
                            break
            rows.append({"stage": stage, "q": q, "method": method, "selected_count": k, "pareto_reversal_count": dominated, "pareto_reversal_rate": dominated / k})
    return pd.DataFrame(rows)


def bootstrap_screening(
    canonical: pd.DataFrame, *, replicates: int = 2000, seed: int = 20260906
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    episodes = tuple(sorted(canonical.original_episode_id.astype(str).unique()))
    output = []
    for replicate in range(replicates):
        sampled = rng.choice(episodes, size=len(episodes), replace=True)
        chunks = []
        for position, episode_id in enumerate(sampled):
            chunk = canonical[
                canonical.original_episode_id.astype(str).eq(episode_id)
            ].copy()
            chunk["bootstrap_instance_id"] = f"{episode_id}#bootstrap-{position}"
            chunk["technical_node_id"] = (
                chunk.decision_node_id.astype(str) + f"#bootstrap-{position}"
            )
            chunks.append(chunk)
        sample = pd.concat(chunks, ignore_index=True)
        stats = screen(sample, q=.10)
        stats["replicate"] = replicate
        output.append(stats)
    return pd.concat(output, ignore_index=True) if output else pd.DataFrame()
