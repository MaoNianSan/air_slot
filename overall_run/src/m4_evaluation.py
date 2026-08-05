from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .m3 import Action, M3Artifact
from .m4_screening import CHANNELS, M4Artifact

RANKING_DEPTHS = (1, 2, 3, 5)
MAXIMUM_RANKING_DEPTH = 5


def derive_ranking_views(
    full_rankings: pd.DataFrame,
    depths: tuple[int, ...] = RANKING_DEPTHS,
) -> dict[int, pd.DataFrame]:
    """Derive fixed-depth views without re-sorting the authoritative ranking."""
    required = {"episode_id", "snapshot_id", "rank", "action_id", "score"}
    if not required.issubset(full_rankings.columns):
        raise ValueError(f"FULL_RANKING_SCHEMA_MISSING:{sorted(required - set(full_rankings.columns))}")
    if tuple(depths) != RANKING_DEPTHS:
        raise ValueError("RANKING_DEPTH_CONTRACT_MISMATCH")
    views: dict[int, pd.DataFrame] = {}
    groups = list(full_rankings.groupby(["episode_id", "snapshot_id"], sort=False, observed=True))
    for depth in depths:
        rows: list[dict[str, Any]] = []
        for (episode_id, snapshot_id), group in groups:
            ordered = group.sort_values("rank", kind="mergesort")
            if ordered["action_id"].astype(str).duplicated().any():
                raise RuntimeError(f"DUPLICATE_ACTION_IN_FULL_RANKING:{episode_id}:{snapshot_id}")
            real_count = min(len(ordered), depth)
            base = ordered.iloc[0] if len(ordered) else None
            for position in range(1, depth + 1):
                if position <= len(ordered):
                    item = ordered.iloc[position - 1]
                    action_id: str | None = str(item["action_id"])
                    score = float(item["score"])
                    expected_residual = float(item.get("expected_residual", np.nan))
                    cvar_residual = float(item.get("cvar_residual", item.get("cvar_component", np.nan)))
                    is_padding = False
                    rank_status = "available"
                else:
                    action_id = None
                    score = expected_residual = cvar_residual = np.nan
                    is_padding = True
                    rank_status = "unavailable"
                rows.append({
                    "episode_id": str(episode_id), "snapshot_id": str(snapshot_id),
                    "flight_id": str(base.get("flight_id", "")) if base is not None else "",
                    "airport": str(base.get("airport", "")) if base is not None else "",
                    "snapshot_stage": str(base.get("snapshot_stage", "")) if base is not None else "",
                    "ranking_k": depth, "rank_position": position, "action_id": action_id,
                    "is_padding": is_padding, "rank_status": rank_status, "score": score,
                    "expected_residual": expected_residual, "cvar_residual": cvar_residual,
                    "effective_action_count": real_count, "padding_count": depth - real_count,
                    "full_k_support": len(ordered) >= depth,
                })
        views[depth] = pd.DataFrame(rows)
    return views


def _cvar_and_tail_mask(values: np.ndarray, alpha: float) -> tuple[float, np.ndarray]:
    threshold = float(np.quantile(values, alpha))
    mask = values >= threshold
    return (float(values[mask].mean()) if mask.any() else threshold), mask


def evaluate_m4(
    snapshots: pd.DataFrame,
    m2_costs_rmb: dict[str, np.ndarray],
    physical_audit: pd.DataFrame,
    actions: dict[str, Action],
    response_library: M3Artifact,
    artifact: M4Artifact,
    frozen_evaluation_actions: dict[tuple[str, str], set[str]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n_rows = len(snapshots)
    arrays = {
        channel: np.asarray(m2_costs_rmb[channel], dtype=float)
        for channel in CHANNELS
    }
    sample_counts = {array.shape[1] for array in arrays.values() if array.ndim == 2}
    if any(array.shape[0] != n_rows for array in arrays.values()) or len(sample_counts) != 1:
        raise RuntimeError("M4_M2_COST_SHAPE_MISMATCH")
    n_samples = next(iter(sample_counts))
    if response_library.n_samples != n_samples:
        raise RuntimeError(
            f"M4_M3_SAMPLE_COUNT_MISMATCH:{response_library.n_samples}!={n_samples}"
        )

    audit_groups = {
        (str(key[0]), str(key[1])): group.set_index("action_id", drop=False)
        for key, group in physical_audit.groupby(
            ["episode_id", "snapshot_id"], sort=False
        )
    }
    action_rows: list[dict[str, Any]] = []
    ranking_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    for row_index, snapshot in enumerate(snapshots.itertuples(index=False)):
        key = (str(snapshot.episode_id), str(snapshot.snapshot_id))
        physical = audit_groups.get(key)
        if physical is None or set(physical.index.astype(str)) != set(actions):
            raise RuntimeError(f"M4_PHYSICAL_AUDIT_INCOMPLETE:{key}")
        pre_channel = {
            channel: arrays[channel][row_index]
            for channel in CHANNELS
        }
        supported = all(
            np.isfinite(pre_channel[channel]).all() for channel in CHANNELS
        )
        trigger = bool(physical["trigger"].iloc[0])
        pre_total = sum(pre_channel.values()) if supported else np.full(n_samples, np.nan)
        expected_pre = float(pre_total.mean()) if supported else np.nan
        zero_pre_cost = bool(
            supported and expected_pre <= artifact.zero_cost_epsilon
        )
        evaluated_rows: list[dict[str, Any]] = []

        for action_id in sorted(actions, key=lambda item: actions[item].priority):
            action = actions[action_id]
            physical_row = physical.loc[action_id]
            physical_feasible = bool(physical_row["physical_feasible"])
            candidate: dict[str, Any] = {
                "episode_id": key[0],
                "snapshot_id": key[1],
                "flight_id": str(snapshot.flight_id),
                "airport": str(snapshot.airport),
                "snapshot_stage": str(snapshot.snapshot_stage),
                "action_id": action_id,
                "action_family": action.family,
                "trigger": trigger,
                "m2_cost_supported": supported,
                "physical_feasible": physical_feasible,
                "physical_rejection_codes": str(physical_row["failure_codes"]),
                "physical_primary_reason": str(physical_row["primary_failure_code"]),
                "physical_failed_gate_count": int(physical_row["failed_gate_count"]),
                **{
                    f"gate_{gate}": bool(physical_row[f"gate_{gate}"])
                    for gate in ("capacity", "window", "resource", "authority", "lead", "typed")
                },
                **{
                    f"gate_{gate}_status": str(physical_row[f"gate_{gate}_status"])
                    for gate in ("capacity", "window", "resource", "authority", "lead", "typed")
                },
                "typed_gate_required": str(physical_row.get("typed_gate_required", "")),
            }

            if not supported:
                candidate.update({
                    "recovery_ratio": np.nan,
                    "burden_ratio": np.nan,
                    "positive_net_benefit_probability": np.nan,
                    "gate_burden_ratio": False,
                    "gate_positive_net_benefit": False,
                    "decision_value_pass": False,
                    "decision_value_rejection_codes": "M2_COST_UNAVAILABLE",
                    "is_evaluated": False,
                    "evaluation_status": "M2_COST_UNAVAILABLE",
                    "primary_reason": "M2_COST_UNAVAILABLE",
                    "candidate_flag": False,
                })
                candidate_rows.append(candidate)
                continue

            recovery_rate = np.asarray(
                response_library.recovery_rates[action_id], dtype=float
            )
            implementation = np.asarray(
                response_library.implementation_costs_rmb[action_id], dtype=float
            )
            recovered_by_channel = {
                channel: recovery_rate[:, index] * pre_channel[channel]
                for index, channel in enumerate(CHANNELS)
            }
            implementation_by_channel = {
                channel: implementation[:, index]
                for index, channel in enumerate(CHANNELS)
            }
            recovered_total = sum(recovered_by_channel.values())
            implementation_total = sum(implementation_by_channel.values())
            expected_recovery = float(recovered_total.mean())
            expected_implementation = float(implementation_total.mean())

            if action_id == "A00":
                recovery_ratio = np.nan
                burden_ratio = np.nan
                positive_probability = np.nan
                gate_burden = True
                gate_positive = True
                decision_pass = True
                decision_codes = "NOT_APPLICABLE"
            elif expected_recovery <= artifact.zero_cost_epsilon:
                recovery_ratio = 0.0
                burden_ratio = np.inf
                positive_probability = 0.0
                gate_burden = False
                gate_positive = False
                decision_pass = False
                decision_codes = (
                    "BURDEN_RATIO_ABOVE_MAX|POSITIVE_NET_BENEFIT_PROBABILITY_BELOW_MIN"
                )
            else:
                recovery_ratio = expected_recovery / max(
                    expected_pre, artifact.zero_cost_epsilon
                )
                burden_ratio = expected_implementation / expected_recovery
                positive_probability = float(
                    (recovered_total > implementation_total).mean()
                )
                gate_burden = burden_ratio <= artifact.burden_ratio_max
                gate_positive = (
                    positive_probability
                    >= artifact.positive_net_benefit_probability_min
                )
                decision_pass = bool(
                    gate_burden and gate_positive
                )
                failures = []
                if not gate_burden:
                    failures.append("BURDEN_RATIO_ABOVE_MAX")
                if not gate_positive:
                    failures.append(
                        "POSITIVE_NET_BENEFIT_PROBABILITY_BELOW_MIN"
                    )
                decision_codes = "|".join(failures) if failures else "PASS"

            if frozen_evaluation_actions is not None:
                frozen_set = frozen_evaluation_actions.get(key)
                if frozen_set is None or "A00" not in frozen_set:
                    raise RuntimeError(f"M4_FROZEN_EVALUATION_SET_MISSING:{key}")
                is_evaluated = action_id in frozen_set
                evaluation_status = (
                    "FROZEN_EVALUATION_SET" if is_evaluated else "FROZEN_OUT"
                )
                primary_reason = evaluation_status
            else:
                is_evaluated = bool(
                    action_id == "A00"
                    or (
                        trigger
                        and not zero_pre_cost
                        and physical_feasible
                        and decision_pass
                    )
                )
                if action_id != "A00" and not trigger:
                    evaluation_status = "TRIGGER_INACTIVE"
                    primary_reason = "TRIGGER_INACTIVE"
                elif action_id != "A00" and zero_pre_cost:
                    evaluation_status = "PRE_ACTION_COST_ZERO"
                    primary_reason = "PRE_ACTION_COST_ZERO"
                elif not physical_feasible:
                    evaluation_status = "PHYSICAL_REJECTED"
                    primary_reason = str(physical_row["primary_failure_code"])
                elif not decision_pass:
                    evaluation_status = "DECISION_VALUE_REJECTED"
                    primary_reason = next(
                        (code for code in decision_codes.split("|") if code),
                        "DECISION_VALUE_REJECTED",
                    )
                else:
                    evaluation_status = "EVALUATED"
                    primary_reason = "PASS"

            candidate.update({
                "expected_pre_action_cost_rmb": expected_pre,
                "expected_recovery_rmb": expected_recovery,
                "expected_implementation_cost_rmb": expected_implementation,
                "recovery_ratio": recovery_ratio,
                "burden_ratio": burden_ratio,
                "positive_net_benefit_probability": positive_probability,
                "gate_burden_ratio": bool(gate_burden),
                "gate_positive_net_benefit": bool(gate_positive),
                "decision_value_pass": bool(decision_pass),
                "decision_value_rejection_codes": decision_codes,
                "is_evaluated": is_evaluated,
                "evaluation_status": evaluation_status,
                "primary_reason": primary_reason,
                "candidate_flag": is_evaluated,
            })
            candidate_rows.append(candidate)
            if not is_evaluated:
                continue

            post_by_channel = {
                channel: (
                    (1.0 - recovery_rate[:, index]) * pre_channel[channel]
                    + implementation[:, index]
                )
                for index, channel in enumerate(CHANNELS)
            }
            post_total = sum(post_by_channel.values())
            if action_id == "A00" and not np.allclose(
                post_total, pre_total, atol=1e-7, rtol=1e-7
            ):
                raise RuntimeError(f"A00_IDENTITY_FAILURE:{key}")
            if not np.isfinite(post_total).all() or np.any(post_total < -1e-9):
                raise RuntimeError(f"M4_INVALID_POST_COST:{key}:{action_id}")

            expected_total = float(post_total.mean())
            cvar_total, tail_mask = _cvar_and_tail_mask(
                post_total, artifact.cvar_alpha
            )
            score = (
                (1.0 - artifact.risk_aversion) * expected_total
                + artifact.risk_aversion * cvar_total
            )
            channel_expected = {
                channel: float(post_by_channel[channel].mean())
                for channel in CHANNELS
            }
            channel_tail = {
                channel: float(post_by_channel[channel][tail_mask].mean())
                for channel in CHANNELS
            }
            channel_contribution = {
                channel: (
                    (1.0 - artifact.risk_aversion) * channel_expected[channel]
                    + artifact.risk_aversion * channel_tail[channel]
                )
                for channel in CHANNELS
            }
            if not np.isclose(
                sum(channel_contribution.values()), score, atol=1e-7, rtol=1e-7
            ):
                raise RuntimeError(
                    f"M4_CHANNEL_SCORE_DECOMPOSITION_FAILURE:{key}:{action_id}"
                )

            score_row = {
                "episode_id": key[0],
                "snapshot_id": key[1],
                "flight_id": str(snapshot.flight_id),
                "airport": str(snapshot.airport),
                "snapshot_stage": str(snapshot.snapshot_stage),
                "action_id": action_id,
                "action_family": action.family,
                "score": score,
                "total_score": score,
                "expected_residual": expected_total,
                "expected_component": expected_total,
                "cvar_component": cvar_total,
                "secondary_burden": expected_implementation,
                "expected_implementation_cost_rmb": expected_implementation,
                "expected_recovery_rmb": expected_recovery,
                "execution_burden": action.burden,
                "priority": action.priority,
                "recovery_ratio": recovery_ratio,
                "burden_ratio": burden_ratio,
                "positive_net_benefit_probability": positive_probability,
                **{
                    f"risk_{channel}": channel_contribution[channel]
                    for channel in CHANNELS
                },
                **{
                    f"expected_component_{channel}": channel_expected[channel]
                    for channel in CHANNELS
                },
                **{
                    f"cvar_component_{channel}": channel_tail[channel]
                    for channel in CHANNELS
                },
                **{
                    f"reduction_{channel}": float(
                        recovered_by_channel[channel].mean()
                    )
                    for channel in CHANNELS
                },
                **{
                    f"channel_contribution_{channel}": channel_contribution[channel]
                    for channel in CHANNELS
                },
                **{
                    f"secondary_burden_{channel}": float(
                        implementation_by_channel[channel].mean()
                    )
                    for channel in CHANNELS
                },
                **{
                    f"expected_implementation_cost_rmb_{channel}": float(
                        implementation_by_channel[channel].mean()
                    )
                    for channel in CHANNELS
                },
            }
            evaluated_rows.append(score_row)
            action_rows.append(score_row)

        if not evaluated_rows:
            if not supported:
                # Unsupported formal rows remain in candidate_screen with an
                # explicit reason and intentionally have no ranking/recommendation.
                continue
            raise RuntimeError(f"M4_EMPTY_EVALUATION_SET:{key}")
        rank_frame = pd.DataFrame(evaluated_rows).sort_values(
            ["score", "expected_residual", "priority", "action_id"],
            kind="mergesort",
        ).reset_index(drop=True)
        rank_frame["rank"] = np.arange(1, len(rank_frame) + 1)
        best = rank_frame.iloc[0]
        a00_score = float(
            rank_frame.loc[rank_frame["action_id"] == "A00", "score"].iloc[0]
        )
        if float(best["score"]) > a00_score + 1e-8:
            raise RuntimeError(f"RECOMMENDATION_WORSE_THAN_NULL:{key}")
        tolerance = max(
            artifact.near_abs_rmb,
            artifact.near_rel
            * max(abs(float(best["score"])), artifact.zero_cost_epsilon),
        )
        near = set(
            rank_frame.loc[
                rank_frame["score"] - float(best["score"]) <= tolerance,
                "action_id",
            ].astype(str)
        )
        for ranked in rank_frame.itertuples(index=False):
            ranking_rows.append({
                "episode_id": key[0],
                "snapshot_id": key[1],
                "flight_id": str(snapshot.flight_id),
                "airport": str(snapshot.airport),
                "snapshot_stage": str(snapshot.snapshot_stage),
                "action_id": str(ranked.action_id),
                "action_family": actions[str(ranked.action_id)].family,
                "rank": int(ranked.rank),
                "ranking_k": 0,
                "rank_position": int(ranked.rank),
                "is_padding": False,
                "rank_status": "available",
                "score": float(ranked.score),
                "total_score": float(ranked.score),
                "expected_residual": float(ranked.expected_residual),
                "cvar_residual": float(ranked.cvar_component),
                "effective_action_count": len(rank_frame),
                "padding_count": 0,
                "full_k_support": True,
                "recommended": bool(ranked.rank == 1),
                "near_equivalent": str(ranked.action_id) in near,
                "near_equivalent_size": len(near),
                "score_gap_to_best": float(ranked.score - best["score"]),
                "negative_intervention": bool(ranked.score > a00_score + 1e-8),
            })

    return (
        pd.DataFrame(action_rows),
        pd.DataFrame(ranking_rows),
        pd.DataFrame(candidate_rows),
    )
