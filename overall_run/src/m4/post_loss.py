from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from ..m2.contracts import M2SampleLoss
from ..m3.artifact import M3Artifact
from ..m3.contracts import COST_CHANNELS, SUBITEMS_M2_V2
from .compatibility import SUBITEMS_BY_CHANNEL
from .contracts import M4ContractError
from .draw_pairing import response_draw_index


@dataclass(frozen=True)
class PostLossSamples:
    action_id: str
    draw_indices: np.ndarray
    pre_subitem_loss_rmb: Mapping[str, np.ndarray]
    post_subitem_loss_rmb: Mapping[str, np.ndarray]
    implementation_costs_rmb: Mapping[str, np.ndarray]
    post_channel_loss_rmb: Mapping[str, np.ndarray]
    pre_total_loss_rmb: np.ndarray
    post_total_loss_rmb: np.ndarray


def calculate_post_loss(
    *,
    action_id: str,
    losses: tuple[M2SampleLoss, ...],
    artifact: M3Artifact,
) -> PostLossSamples:
    if action_id not in artifact.action_catalog:
        raise M4ContractError(f"M4_ACTION_UNKNOWN:{action_id}")
    draw_indices = np.asarray([
        response_draw_index(
            episode_id=loss.episode_id,
            sample_id=loss.sample_id,
            m3_sample_hash=artifact.sample_hash,
            n_draws=artifact.n_draws,
        )
        for loss in losses
    ], dtype=np.int64)
    recovery_matrix = np.asarray(artifact.subitem_recovery_rates[action_id], dtype=float)[
        draw_indices
    ]
    cost_matrix = np.asarray(artifact.implementation_costs_rmb[action_id], dtype=float)[
        draw_indices
    ]
    pre_subitems = {
        name: np.asarray([float(loss.subitem_loss_rmb[name]) for loss in losses], dtype=float)
        for name in SUBITEMS_M2_V2
    }
    post_subitems = {
        name: (1.0 - recovery_matrix[:, index]) * pre_subitems[name]
        for index, name in enumerate(SUBITEMS_M2_V2)
    }
    implementation = {
        channel: cost_matrix[:, index]
        for index, channel in enumerate(COST_CHANNELS)
    }
    post_channels = {
        channel: sum(post_subitems[name] for name in names) + implementation[channel]
        for channel, names in SUBITEMS_BY_CHANNEL.items()
    }
    pre_total = sum(pre_subitems.values())
    post_total = sum(post_channels.values())
    if not np.isfinite(post_total).all() or np.any(post_total < 0.0):
        raise M4ContractError(f"M4_POST_LOSS_INVALID:{action_id}")
    if action_id == "A00":
        if not np.array_equal(recovery_matrix, np.zeros_like(recovery_matrix)):
            raise M4ContractError("M4_A00_RECOVERY_IDENTITY_FAILURE")
        if not np.array_equal(cost_matrix, np.zeros_like(cost_matrix)):
            raise M4ContractError("M4_A00_COST_IDENTITY_FAILURE")
        if not np.allclose(post_total, pre_total, atol=1e-10, rtol=1e-10):
            raise M4ContractError("M4_A00_SAMPLE_IDENTITY_FAILURE")
    return PostLossSamples(
        action_id=action_id,
        draw_indices=draw_indices,
        pre_subitem_loss_rmb=pre_subitems,
        post_subitem_loss_rmb=post_subitems,
        implementation_costs_rmb=implementation,
        post_channel_loss_rmb=post_channels,
        pre_total_loss_rmb=pre_total,
        post_total_loss_rmb=post_total,
    )
