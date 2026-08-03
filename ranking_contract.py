from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


RANKING_DEPTHS = (1, 2, 3, 5)
RANKING_CONTRACT_VERSION = "M4_RANKING_1235_V1_PROVISIONAL"
RANKING_REQUIRED_COLUMNS = (
    "episode_id", "snapshot_id", "ranking_k", "rank_position",
    "action_id", "action_family", "is_padding", "rank_status", "score",
    "expected_residual", "cvar_residual", "effective_action_count",
    "padding_count", "full_k_support", "action_library_version",
    "ranking_contract_version",
)


def build_ranking_prefixes(
    episode_universe: pd.DataFrame,
    full_ranking: pd.DataFrame,
    depths: Iterable[int] = RANKING_DEPTHS,
    *,
    action_library_version: str = "M3_RESPONSE_V3_EXPANDED_PROVISIONAL",
    ranking_contract_version: str = RANKING_CONTRACT_VERSION,
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """Materialize fixed-width prefixes from one authoritative full sort."""
    depths = tuple(int(value) for value in depths)
    if depths != RANKING_DEPTHS:
        raise ValueError("RANKING_DEPTHS_MUST_BE_1_2_3_5")
    universe_required = {"episode_id", "snapshot_id"}
    universe_missing = sorted(universe_required - set(episode_universe.columns))
    if universe_missing:
        raise ValueError("RANKING_UNIVERSE_MISSING:" + ",".join(universe_missing))
    universe = episode_universe.drop_duplicates(
        ["episode_id", "snapshot_id"], keep="first"
    ).copy()
    if len(universe) != len(episode_universe):
        raise ValueError("RANKING_UNIVERSE_DUPLICATE_KEY")
    if universe.empty:
        empty = pd.DataFrame(columns=RANKING_REQUIRED_COLUMNS)
        return empty, {depth: empty.copy() for depth in depths}
    rank_column = "rank_position" if "rank_position" in full_ranking else "rank"
    if not full_ranking.empty:
        required = {
            "episode_id", "snapshot_id", "action_id", "action_family", "score", rank_column
        }
        missing = sorted(required - set(full_ranking.columns))
        if missing:
            raise ValueError("RANKING_INPUT_MISSING:" + ",".join(missing))
        universe_keys = set(
            universe[["episode_id", "snapshot_id"]].itertuples(index=False, name=None)
        )
        ranking_keys = set(
            full_ranking[["episode_id", "snapshot_id"]].itertuples(index=False, name=None)
        )
        if not ranking_keys.issubset(universe_keys):
            raise ValueError("RANKING_ROWS_OUTSIDE_EPISODE_UNIVERSE")

    rows: list[dict[str, object]] = []
    identity_columns = [
        column
        for column in ("flight_id", "airport", "snapshot_stage")
        if column in universe.columns or column in full_ranking.columns
    ]
    ranking_groups = {
        key: group
        for key, group in full_ranking.groupby(
            ["episode_id", "snapshot_id"], sort=False, observed=True
        )
    } if not full_ranking.empty else {}
    for universe_row in universe.itertuples(index=False):
        universe_values = universe.loc[
            universe["episode_id"].eq(universe_row.episode_id)
            & universe["snapshot_id"].eq(universe_row.snapshot_id)
        ].iloc[0]
        key = (universe_row.episode_id, universe_row.snapshot_id)
        group = ranking_groups.get(key)
        ordered = (
            group.sort_values(rank_column, kind="mergesort").reset_index(drop=True)
            if group is not None
            else pd.DataFrame()
        )
        if not ordered.empty and ordered["action_id"].astype("string").duplicated().any():
            raise ValueError(f"RANKING_DUPLICATE_ACTION:{key}")
        if not ordered.empty and int(ordered["action_id"].astype("string").eq("A00").sum()) > 1:
            raise ValueError(f"RANKING_A00_DUPLICATE:{key}")
        for depth in depths:
            effective = min(len(ordered), depth)
            padding = depth - effective
            for position in range(1, depth + 1):
                if position <= effective:
                    source = ordered.iloc[position - 1]
                    row = source.to_dict()
                    row.update({
                        "ranking_k": depth,
                        "rank_position": position,
                        "is_padding": False,
                        "rank_status": "AVAILABLE",
                        "expected_residual": source.get("expected_residual", np.nan),
                        "cvar_residual": source.get(
                            "cvar_residual", source.get("cvar_component", np.nan)
                        ),
                    })
                else:
                    row = {
                        "episode_id": key[0],
                        "snapshot_id": key[1],
                        "ranking_k": depth,
                        "rank_position": position,
                        "action_id": pd.NA,
                        "action_family": pd.NA,
                        "is_padding": True,
                        "rank_status": "UNAVAILABLE",
                        "score": np.nan,
                        "expected_residual": np.nan,
                        "cvar_residual": np.nan,
                    }
                    for column in identity_columns:
                        row[column] = universe_values.get(column, pd.NA)
                row.update({
                    "effective_action_count": effective,
                    "padding_count": padding,
                    "full_k_support": padding == 0,
                    "action_library_version": action_library_version,
                    "ranking_contract_version": ranking_contract_version,
                })
                rows.append(row)
    all_k = pd.DataFrame(rows)
    ordered_columns = [
        *RANKING_REQUIRED_COLUMNS,
        *[column for column in identity_columns if column not in RANKING_REQUIRED_COLUMNS],
    ]
    extra = [column for column in all_k if column not in ordered_columns]
    all_k = all_k[ordered_columns + extra].sort_values(
        ["episode_id", "snapshot_id", "ranking_k", "rank_position"],
        kind="mergesort",
    ).reset_index(drop=True)
    views = {
        depth: all_k[all_k["ranking_k"].eq(depth)].reset_index(drop=True)
        for depth in depths
    }
    validate_ranking_prefixes(all_k)
    return all_k, views


def validate_ranking_prefixes(all_k: pd.DataFrame) -> None:
    missing = sorted(set(RANKING_REQUIRED_COLUMNS) - set(all_k.columns))
    if missing:
        raise ValueError("RANKING_SCHEMA_MISSING:" + ",".join(missing))
    for key, group in all_k.groupby(
        ["episode_id", "snapshot_id"], sort=False, observed=True
    ):
        sequences: dict[int, list[str]] = {}
        for depth in RANKING_DEPTHS:
            view = group[group["ranking_k"].eq(depth)].sort_values("rank_position")
            if len(view) != depth:
                raise ValueError(f"RANKING_FIXED_WIDTH_FAILURE:{key}:{depth}")
            real = view[~view["is_padding"].fillna(False).astype(bool)]
            if real["action_id"].isna().any():
                raise ValueError(f"RANKING_REAL_ACTION_NULL:{key}:{depth}")
            padding = view[view["is_padding"].fillna(False).astype(bool)]
            if padding["action_id"].notna().any():
                raise ValueError(f"RANKING_PADDING_ACTION_NON_NULL:{key}:{depth}")
            null_columns = ["score", "expected_residual", "cvar_residual"]
            if padding[null_columns].notna().any().any():
                raise ValueError(f"RANKING_PADDING_METRIC_NON_NULL:{key}:{depth}")
            if not padding["rank_status"].eq("UNAVAILABLE").all():
                raise ValueError(f"RANKING_PADDING_STATUS_INVALID:{key}:{depth}")
            if int(real["action_id"].astype(str).eq("A00").sum()) > 1:
                raise ValueError(f"RANKING_A00_DUPLICATE:{key}:{depth}")
            sequences[depth] = real["action_id"].astype(str).tolist()
        longest = sequences[5]
        for depth in RANKING_DEPTHS:
            if sequences[depth] != longest[: min(depth, len(longest))]:
                raise ValueError(f"RANKING_PREFIX_FAILURE:{key}:{depth}")


def full_ranking_from_scores(
    scores: pd.DataFrame,
    score_column: str,
    *,
    group_columns: tuple[str, str] = ("episode_id", "snapshot_id"),
) -> pd.DataFrame:
    """Apply the shared stable tie-break once for each episode."""
    required = {
        *group_columns,
        "action_id",
        "action_family",
        score_column,
        "expected_residual",
    }
    missing = sorted(required - set(scores.columns))
    if missing:
        raise ValueError("RANKING_SCORE_INPUT_MISSING:" + ",".join(missing))
    frame = scores.copy()
    frame["score"] = pd.to_numeric(frame[score_column], errors="coerce")
    if "priority" not in frame:
        frame["priority"] = 0
    frame = frame.sort_values(
        [*group_columns, "score", "expected_residual", "priority", "action_id"],
        kind="mergesort",
    )
    frame["rank"] = frame.groupby(list(group_columns), sort=False).cumcount() + 1
    return frame.reset_index(drop=True)


def compare_ranking_prefixes(
    global_prefixes: pd.DataFrame,
    local_prefixes: pd.DataFrame,
) -> pd.DataFrame:
    """Compare fixed-width prefixes while excluding padding from set metrics."""
    validate_ranking_prefixes(global_prefixes)
    validate_ranking_prefixes(local_prefixes)
    rows: list[dict[str, object]] = []
    keys = ["episode_id", "snapshot_id", "ranking_k"]
    global_groups = {key: group for key, group in global_prefixes.groupby(keys, sort=False)}
    local_groups = {key: group for key, group in local_prefixes.groupby(keys, sort=False)}
    if set(global_groups) != set(local_groups):
        raise ValueError("RANKING_COMPARISON_KEY_MISMATCH")
    for key in sorted(global_groups, key=lambda value: tuple(map(str, value))):
        global_group = global_groups[key].sort_values("rank_position")
        local_group = local_groups[key].sort_values("rank_position")
        global_actions = global_group.loc[
            ~global_group["is_padding"].astype(bool), "action_id"
        ].astype(str).tolist()
        local_actions = local_group.loc[
            ~local_group["is_padding"].astype(bool), "action_id"
        ].astype(str).tolist()
        exact = global_actions == local_actions
        same_set = set(global_actions) == set(local_actions)
        overlap = len(set(global_actions) & set(local_actions))
        depth = int(key[2])
        effective_denominator = max(len(global_actions), len(local_actions))
        position_matches = sum(
            left == right
            for left, right in zip(
                global_group["action_id"].astype("string"),
                local_group["action_id"].astype("string"),
            )
            if pd.notna(left) and pd.notna(right)
        )
        first_different = next(
            (
                position
                for position, (left, right) in enumerate(
                    zip(
                        global_group["action_id"].astype("string"),
                        local_group["action_id"].astype("string"),
                    ),
                    1,
                )
                if not (
                    (pd.isna(left) and pd.isna(right))
                    or (pd.notna(left) and pd.notna(right) and left == right)
                )
            ),
            pd.NA,
        )
        rows.append({
            "episode_id": key[0],
            "snapshot_id": key[1],
            "ranking_k": depth,
            "exact_order_match": exact,
            "ordered_disagreement": not exact,
            "set_disagreement": not same_set,
            "order_only_disagreement": same_set and not exact,
            "overlap_count": overlap,
            "overlap_rate": (
                overlap / effective_denominator if effective_denominator else 1.0
            ),
            "position_match_count": position_matches,
            "position_match_rate": (
                position_matches / effective_denominator if effective_denominator else 1.0
            ),
            "first_different_rank": first_different,
            "effective_action_count_global": len(global_actions),
            "effective_action_count_local": len(local_actions),
            "padding_count_global": depth - len(global_actions),
            "padding_count_local": depth - len(local_actions),
            "full_k_support": len(global_actions) == depth and len(local_actions) == depth,
            "comparison_class": (
                "EXACT_ORDER_MATCH"
                if exact
                else "SAME_SET_DIFFERENT_ORDER"
                if same_set
                else "DIFFERENT_SET"
            ),
        })
    return pd.DataFrame(rows)


def real_ranking_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only real actions for action, burden, recovery, and regret metrics."""
    if "is_padding" not in frame:
        return frame.copy()
    return frame[~frame["is_padding"].fillna(False).astype(bool)].copy()
