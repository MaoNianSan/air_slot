from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .utils import stable_hash


@dataclass(frozen=True)
class Cohorts:
    all_valid: pd.DataFrame
    balanced_rolling: pd.DataFrame
    formal_core: pd.DataFrame
    precision: pd.DataFrame


def _is_valid_snapshot(df: pd.DataFrame) -> pd.Series:
    for col in ("snapshot_valid", "is_valid", "valid"):
        if col in df.columns:
            return df[col].fillna(False).astype(bool)
    return pd.Series(True, index=df.index)


def _stable_select_flights(df: pd.DataFrame, max_flights: int, seed: int, strata: list[str]) -> pd.DataFrame:
    flights = df[["flight_id", *[c for c in strata if c in df.columns]]].drop_duplicates("flight_id").copy()
    flights["selection_key"] = flights["flight_id"].map(lambda x: stable_hash(seed, x))
    if not strata:
        selected = flights.sort_values("selection_key").head(max_flights)
    else:
        available = [c for c in strata if c in flights.columns]
        groups = flights.groupby(available, dropna=False, sort=True) if available else [(None, flights)]
        sizes = {k: len(g) for k, g in groups}
        total = sum(sizes.values())
        selected_parts = []
        for key, group in (flights.groupby(available, dropna=False, sort=True) if available else [(None, flights)]):
            quota = max(1, round(max_flights * len(group) / max(total, 1)))
            selected_parts.append(group.sort_values("selection_key").head(quota))
        selected = pd.concat(selected_parts, ignore_index=True).sort_values("selection_key").head(max_flights)
    return df[df["flight_id"].isin(set(selected["flight_id"]))].copy()


def build_cohorts(
    snapshots: pd.DataFrame,
    scientific: dict[str, Any],
    mode_cfg: dict[str, Any],
    seed: int,
) -> Cohorts:
    roles = scientific["cohort"]["roles"]
    test_roles = {str(x).lower() for x in roles.get("test", ["test", "final_test"])}
    valid = snapshots[_is_valid_snapshot(snapshots) & snapshots["split"].isin(test_roles)].copy()

    primary_stages = {str(x) for x in scientific["cohort"].get("primary_stages", ["t1", "t2", "t3"])}
    primary = valid[valid["snapshot_stage"].isin(primary_stages)].copy()
    core_airports = {x.upper() for x in scientific["cohort"].get("core_airports", [])}
    core = primary[primary["airport"].isin(core_airports)].copy()
    if "anchor_date" not in core.columns:
        core["anchor_date"] = core["decision_time"].dt.date.astype(str)
    if "evidence_quality_stratum" not in core.columns:
        candidates = [c for c in core.columns if "coverage" in c.lower() or "quality" in c.lower()]
        if candidates:
            q = pd.to_numeric(core[candidates[0]], errors="coerce")
            core["evidence_quality_stratum"] = pd.qcut(q.rank(method="first"), 3, labels=["low", "mid", "high"], duplicates="drop").astype(str)
        else:
            core["evidence_quality_stratum"] = "unknown"

    max_flights = int(mode_cfg.get("max_formal_core_flights", 1200))
    per_airport = mode_cfg.get("max_flights_per_core_airport")
    if per_airport:
        selected = []
        for airport, g in core.groupby("airport", sort=True):
            selected.append(
                _stable_select_flights(
                    g,
                    int(per_airport),
                    seed,
                    ["anchor_date", "balanced_primary_cohort", "evidence_quality_stratum"],
                )
            )
        formal = pd.concat(selected, ignore_index=True) if selected else core.iloc[0:0].copy()
        if formal["flight_id"].nunique() > max_flights:
            formal = _stable_select_flights(formal, max_flights, seed, ["airport", "anchor_date"])
    else:
        formal = _stable_select_flights(core, max_flights, seed, ["airport", "anchor_date", "evidence_quality_stratum"])

    stage_count = formal.groupby("flight_id")["snapshot_stage"].nunique()
    balanced_ids = set(stage_count[stage_count == len(primary_stages)].index)
    balanced = formal[formal["flight_id"].isin(balanced_ids)].copy()

    precision_n = int(mode_cfg.get("max_flights", 200))
    precision = _stable_select_flights(formal, min(precision_n, formal["flight_id"].nunique()), seed + 1, ["airport", "anchor_date"])
    return Cohorts(all_valid=primary, balanced_rolling=balanced, formal_core=formal, precision=precision)
