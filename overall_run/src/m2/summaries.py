from __future__ import annotations

import numpy as np

from .contracts import M2EpisodeSummary, M2SampleLoss


def _summary(values: list[float], *, tail_resolved: bool) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("mean", "median", "q90", "q95", "cvar90")}
    array = np.asarray(values, dtype=float)
    q90 = float(np.quantile(array, 0.90)); q95 = float(np.quantile(array, 0.95))
    tail = array[array >= q90]
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "q90": q90,
        "q95": q95 if tail_resolved else None,
        "cvar90": (float(tail.mean()) if len(tail) else q90) if tail_resolved else None,
    }


def summarize_episode(losses: tuple[M2SampleLoss, ...]) -> M2EpisodeSummary:
    values = [loss.total_pre_action_loss_rmb for loss in losses if loss.total_pre_action_loss_rmb is not None]
    channel_values = {channel: [loss.channel_loss_rmb.get(channel) for loss in losses if loss.channel_loss_rmb.get(channel) is not None] for channel in ("F", "P", "R")}
    contributions = {channel: float(np.mean(values_)) if values_ else None for channel, values_ in channel_values.items()}
    subitems: dict[str, list[float]] = {}
    for loss in losses:
        for name, value in loss.constructed_units.items():
            if value is not None: subitems.setdefault(name, []).append(float(value))
    sub_contrib = {name: float(np.mean(values_)) for name, values_ in subitems.items()}
    dominant = max(((value, key) for key, value in contributions.items() if value is not None), default=(None, None))[1]
    dominant_sub = max(((value, key) for key, value in sub_contrib.items()), default=(None, None))[1]
    tail_resolved = losses[0].tail_resolution_status != "TAIL_UNRESOLVED"
    constructed = [
        sum(v for v in loss.channel_constructed_units.values() if v is not None)
        for loss in losses
        if any(v is not None for v in loss.channel_constructed_units.values())
    ]
    return M2EpisodeSummary(
        losses[0].episode_id,
        _summary(constructed, tail_resolved=tail_resolved),
        _summary(values, tail_resolved=tail_resolved),
        contributions,
        sub_contrib,
        dominant,
        dominant_sub,
        tuple(name for name, loss in losses[0].constructed_units.items() if loss is None),
        tuple(sorted({name for loss in losses for name in loss.proxy_status})),
        float(np.mean([loss.overflow_present for loss in losses])),
        losses[0].tail_resolution_status,
    )
