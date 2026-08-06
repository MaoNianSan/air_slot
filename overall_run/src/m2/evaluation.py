from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

from .contracts import M2InputBundle, M2SampleLoss


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


def _joint_frequency(
    samples: tuple[object, ...],
    predicate: Callable[[object], bool | None],
) -> dict[str, float | bool | None]:
    evaluated = [predicate(sample) for sample in samples]
    resolved = [value for value in evaluated if value is not None]
    occurred = sum(bool(value) for value in resolved)
    unresolved = len(evaluated) - len(resolved)
    total = len(evaluated)
    return {
        "resolved_probability": occurred / len(resolved) if resolved else None,
        "unresolved_probability_mass": unresolved / total,
        "probability_lower_bound": occurred / total,
        "probability_upper_bound": (occurred + unresolved) / total,
        "formal_probability_available": unresolved == 0,
        "formal_probability": occurred / total if unresolved == 0 else None,
    }


def _both(sample: object, left: str, left_point: float, right: str, right_point: float) -> bool | None:
    left_value = getattr(sample, left, None)
    right_value = getattr(sample, right, None)
    if left_value is None or right_value is None:
        return None
    return float(left_value) > left_point and float(right_value) > right_point


def _correlation(samples: tuple[object, ...], left: str, right: str) -> float | None:
    pairs = [
        (float(getattr(sample, left)), float(getattr(sample, right)))
        for sample in samples
        if getattr(sample, left, None) is not None
        and getattr(sample, right, None) is not None
    ]
    if len(pairs) < 2:
        return None
    array = np.asarray(pairs, dtype=float)
    if np.std(array[:, 0]) <= 1e-12 or np.std(array[:, 1]) <= 1e-12:
        return None
    return float(np.corrcoef(array[:, 0], array[:, 1])[0, 1])


def evaluate_joint_scenarios(
    bundle: M2InputBundle,
    losses: tuple[M2SampleLoss, ...],
    *,
    observed_joint_events: Mapping[str, bool] | None = None,
) -> dict[str, object]:
    loss_by_sample = {loss.sample_id: loss for loss in losses}

    def turn_and_taxi(sample: object) -> bool | None:
        loss = loss_by_sample.get(int(getattr(sample, "sample_id", -1)))
        if loss is None or loss.turn_deficit_minutes is None or loss.extra_taxi_minutes is None:
            return None
        return loss.turn_deficit_minutes > 0.0 and loss.extra_taxi_minutes > 15.0

    frequencies = {
        "R_OB_GT_30_AND_T_TX_GT_15": _joint_frequency(
            bundle.joint_scenarios,
            lambda sample: _both(sample, "r_ob_minutes", 30.0, "taxi_time", 15.0),
        ),
        "TURN_GT_0_AND_EXTRA_TAXI_GT_15": _joint_frequency(
            bundle.joint_scenarios,
            turn_and_taxi,
        ),
        "D_OB_GT_30_AND_D_TO_GT_60": _joint_frequency(
            bundle.joint_scenarios,
            lambda sample: _both(
                sample,
                "offblock_delay",
                30.0,
                "total_takeoff_delay",
                60.0,
            ),
        ),
    }
    calibration: dict[str, object] = {}
    for name, estimate in frequencies.items():
        observed = None if observed_joint_events is None else observed_joint_events.get(name)
        probability = estimate["formal_probability"]
        if observed is None or probability is None:
            calibration[name] = {"status": "NOT_AVAILABLE", "brier_score": None}
        else:
            calibration[name] = {
                "status": "AVAILABLE",
                "brier_score": (float(probability) - float(bool(observed))) ** 2,
            }
    return {
        "joint_event_calibration": calibration,
        "residual_correlation": {
            "R_OB__T_TX": _correlation(
                bundle.joint_scenarios, "r_ob_minutes", "taxi_time"
            ),
            "D_OB__D_TO": _correlation(
                bundle.joint_scenarios,
                "offblock_delay",
                "total_takeoff_delay",
            ),
        },
        "joint_tail_frequency": frequencies,
        "sampling_model_changed": False,
        "dependence_mode": "CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING",
    }
