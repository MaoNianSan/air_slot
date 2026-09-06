"""Frozen retrospective fixed-capacity screening primitives for Exp4."""

from __future__ import annotations

from math import ceil

import pandas as pd

ACTIVE_STAGES = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")


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
        delay = set(group.nlargest(k, "D").decision_node_id)
        consequence = set(group.nlargest(k, "S_C").decision_node_id)
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
        selections = {"DELAY": set(group.nlargest(k, "D").decision_node_id), "CONSEQUENCE": set(group.nlargest(k, "S_C").decision_node_id)}
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
    group["NO_F_EXECUTION"] = group[["Z_F_continuity_cs", "Z_F_propagation_cs", "S_P", "S_R"]].mean(axis=1)
    for name, column in (("F_EMPHASIS_050_025_025", None), ("P_EMPHASIS_025_050_025", None), ("R_EMPHASIS_025_025_050", None)):
        weights = {"F_EMPHASIS_050_025_025": (0.50, 0.25, 0.25), "P_EMPHASIS_025_050_025": (0.25, 0.50, 0.25), "R_EMPHASIS_025_025_050": (0.25, 0.25, 0.50)}[name]
        group[name] = weights[0] * group.S_F + weights[1] * group.S_P + weights[2] * group.S_R
        views[name] = name
    counts = {node: 0 for node in group.decision_node_id}
    for name, column in views.items():
        values = group[column] if column else group[name]
        k = max(1, ceil(.10 * len(group)))
        for node in group.nlargest(k, values.name).decision_node_id:
            counts[node] += 1
    out = group[["stage", "original_episode_id", "decision_node_id", "D", "S_C"]].copy()
    out["view_count"] = out.decision_node_id.map(counts)
    out["robust_high_consequence"] = out.view_count >= threshold
    return out


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
                        if other.decision_node_id not in selected and all(other[c] >= row[c] for c in components) and any(other[c] > row[c] for c in components):
                            dominated += 1
                            break
            rows.append({"stage": stage, "q": q, "method": method, "selected_count": k, "pareto_reversal_count": dominated, "pareto_reversal_rate": dominated / k})
    return pd.DataFrame(rows)
