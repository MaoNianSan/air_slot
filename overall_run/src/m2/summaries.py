from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .contracts import M2EpisodeSummary, M2SampleLoss


def _distribution_summary(
    resolved_values: list[float],
    *,
    formal_available: bool,
) -> dict[str, float | bool | None]:
    keys = (
        "mean",
        "median",
        "q90",
        "q95",
        "cvar90",
        "resolved_only_mean",
        "resolved_only_median",
        "resolved_only_q90",
        "resolved_only_q95",
        "resolved_only_cvar90",
    )
    if not resolved_values:
        return {
            **{key: None for key in keys},
            "formal_q95_available": False,
            "formal_cvar90_available": False,
        }
    array = np.asarray(resolved_values, dtype=float)
    q90 = float(np.quantile(array, 0.90))
    q95 = float(np.quantile(array, 0.95))
    tail = array[array >= q90]
    cvar90 = float(tail.mean()) if len(tail) else q90
    resolved = {
        "resolved_only_mean": float(array.mean()),
        "resolved_only_median": float(np.median(array)),
        "resolved_only_q90": q90,
        "resolved_only_q95": q95,
        "resolved_only_cvar90": cvar90,
    }
    formal = {
        "mean": resolved["resolved_only_mean"] if formal_available else None,
        "median": resolved["resolved_only_median"] if formal_available else None,
        "q90": resolved["resolved_only_q90"] if formal_available else None,
        "q95": q95 if formal_available else None,
        "cvar90": cvar90 if formal_available else None,
        "formal_q95_available": formal_available,
        "formal_cvar90_available": formal_available,
    }
    return {**formal, **resolved}


def _weighted_mean(
    losses: tuple[M2SampleLoss, ...],
    getter: Callable[[M2SampleLoss], float | None],
) -> float | None:
    pairs = [
        (float(loss.sample_weight), getter(loss))
        for loss in losses
        if getter(loss) is not None
    ]
    if not pairs:
        return None
    weight = sum(item[0] for item in pairs)
    return sum(item[0] * float(item[1]) for item in pairs) / weight


def _shares(
    means: dict[str, float | None],
    total_mean: float | None,
    *,
    resolved_only: bool,
) -> tuple[dict[str, float | None], str]:
    if total_mean is None:
        return {name: None for name in means}, "TOTAL_LOSS_UNAVAILABLE"
    if abs(total_mean) <= 1e-12:
        return {name: None for name in means}, "ZERO_TOTAL_LOSS"
    shares = {
        name: None if value is None else float(value) / float(total_mean)
        for name, value in means.items()
    }
    return shares, "RESOLVED_ONLY" if resolved_only else "PASS"


def summarize_episode(losses: tuple[M2SampleLoss, ...]) -> M2EpisodeSummary:
    if not losses:
        raise ValueError("M2_SUMMARY_LOSSES_EMPTY")
    unresolved_probability = sum(
        float(loss.sample_weight)
        for loss in losses
        if loss.tail_resolution_status == "TAIL_UNRESOLVED"
    )
    formal_values = [
        float(loss.total_pre_action_loss_rmb)
        for loss in losses
        if loss.total_pre_action_loss_rmb is not None
    ]
    resolved_values = [
        float(loss.resolved_only_total_pre_action_loss_rmb)
        for loss in losses
        if loss.resolved_only_total_pre_action_loss_rmb is not None
    ]
    formal_tail_available = (
        unresolved_probability == 0.0
        and len(formal_values) == len(losses)
        and bool(formal_values)
    )
    resolved_losses = tuple(
        loss
        for loss in losses
        if loss.resolved_only_total_pre_action_loss_rmb is not None
    )
    channel_means = {
        channel: _weighted_mean(
            resolved_losses,
            lambda loss, channel=channel: loss.channel_loss_rmb.get(channel),
        )
        for channel in ("F", "P", "R")
    }
    subitem_names = tuple(losses[0].subitem_loss_rmb)
    subitem_means = {
        name: _weighted_mean(
            resolved_losses,
            lambda loss, name=name: loss.subitem_loss_rmb.get(name),
        )
        for name in subitem_names
    }
    total_mean = _weighted_mean(
        resolved_losses,
        lambda loss: loss.resolved_only_total_pre_action_loss_rmb,
    )
    channel_shares, channel_share_status = _shares(
        channel_means,
        total_mean,
        resolved_only=not formal_tail_available,
    )
    subitem_shares, subitem_share_status = _shares(
        subitem_means,
        total_mean,
        resolved_only=not formal_tail_available,
    )
    dominant_channel = max(
        (
            (value, name)
            for name, value in channel_means.items()
            if value is not None
        ),
        default=(None, None),
    )[1]
    dominant_subitem = max(
        (
            (value, name)
            for name, value in subitem_means.items()
            if value is not None
        ),
        default=(None, None),
    )[1]
    constructed_values = [
        float(sum(value for value in loss.channel_constructed_units.values() if value is not None))
        for loss in resolved_losses
    ]
    tail_status = "RESOLVED" if formal_tail_available else "TAIL_UNRESOLVED"
    if unresolved_probability > 0.0:
        m4_gate = "M2_TAIL_NOT_READY_FOR_M4"
    elif not formal_tail_available:
        m4_gate = "M2_FORMAL_LOSS_NOT_AVAILABLE"
    else:
        m4_gate = "READY_FOR_M4_CONTRACT"
    rmb_summary = _distribution_summary(
        resolved_values,
        formal_available=formal_tail_available,
    )
    return M2EpisodeSummary(
        episode_id=losses[0].episode_id,
        constructed_unit_summary=_distribution_summary(
            constructed_values,
            formal_available=formal_tail_available,
        ),
        rmb_summary=rmb_summary,
        channel_mean_losses=channel_means,
        channel_loss_shares=channel_shares,
        channel_loss_shares_status=channel_share_status,
        subitem_mean_losses=subitem_means,
        subitem_loss_shares=subitem_shares,
        subitem_loss_shares_status=subitem_share_status,
        dominant_channel=dominant_channel,
        dominant_subitem=dominant_subitem,
        unsupported_subitems=tuple(
            name
            for name, value in losses[0].constructed_units.items()
            if value is None
        ),
        proxy_active_subitems=tuple(
            sorted({name for loss in losses for name in loss.proxy_status})
        ),
        unresolved_probability=unresolved_probability,
        overflow_probability=sum(
            float(loss.sample_weight) for loss in losses if loss.overflow_present
        ),
        tail_resolution_status=tail_status,
        formal_q95_available=bool(rmb_summary["formal_q95_available"]),
        formal_cvar90_available=bool(rmb_summary["formal_cvar90_available"]),
        m4_gate_status=m4_gate,
    )
