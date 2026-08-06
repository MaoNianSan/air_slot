from __future__ import annotations

from .contracts import M2SampleLoss


def audit_sample_losses(losses: tuple[M2SampleLoss, ...], tolerance: float = 1e-9) -> dict[str, bool]:
    nonnegative = all(
        value is None or value >= 0.0
        for loss in losses
        for value in (
            *loss.quantities.values(),
            *loss.constructed_units.values(),
            *loss.channel_loss_rmb.values(),
            loss.total_pre_action_loss_rmb,
        )
    )
    currency_identity = all(
        all(
            loss.channel_loss_rmb.get(channel) is None
            or abs(
                float(loss.channel_loss_rmb[channel])
                - float(loss.channel_constructed_units[channel])
            ) <= tolerance
            for channel in ("F", "P", "R")
        )
        for loss in losses
    )
    total_additivity = all(
        loss.total_pre_action_loss_rmb is None
        or abs(
            float(loss.total_pre_action_loss_rmb)
            - sum(
                float(value)
                for value in loss.channel_loss_rmb.values()
                if value is not None
            )
        ) <= tolerance
        for loss in losses
    )
    return {
        "nonnegative": nonnegative,
        "currency_identity": currency_identity,
        "total_additivity": total_additivity,
    }
