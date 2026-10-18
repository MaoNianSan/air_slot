"""M1 V2 warning: P(D_TO > 30) from formal V2 aligned scenarios.

The V2 warning consumes only formal V2 scenario quantities
(T_IB_A00 / D_OB / D_TX / derived D_TO).  D_TO is never reconstructed from
DELTA_OB / raw T_TX / taxi reference: D_TX is itself a formal sampled
quantity and the legacy V1 signed-warning artifact is HISTORICAL_ONLY.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Sequence

import torch
from pydantic import Field, model_validator

from model.common.value_objects import FrozenModel

from .contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1V2Scenario,
    M1_V2_HAZARD_COORDINATE,
    V2_TARGETS,
)
from .loss import hazard_pmf, monotone_positive_quantiles, quantile_value
from .scenario_layer.sampler import _uniform_v2, required_observations_v2
from .semantics import M1_V2_HAZARD_COORDINATE_TARGET

PRINCIPAL_WARNING_EVENT = "D_TO_POST_GT_30"
PRINCIPAL_WARNING_THRESHOLD_MINUTES = 30.0
# Seed-key targets follow the internal V2 target names so the vectorized path
# produces the exact uniforms of ``ancestral_sample_v2``.
V2_WARNING_TARGETS = V2_TARGETS


class WarningProbability(FrozenModel):
    """Weighted probability for the formal V2 takeoff-delay event."""

    episode_id: str | None
    decision_node_id: str | None
    event_id: str
    comparison: Literal["STRICT_GT"] = "STRICT_GT"
    delay_threshold_minutes: float = Field(ge=0)
    probability: float | None = Field(default=None, ge=0, le=1)
    support_state: Literal["SUPPORTED", "ABSTAIN"]
    reason_code: str
    scenario_count: int = Field(ge=0)
    scenario_weight_sum: float = Field(ge=0)
    exceedance_weight: float = Field(ge=0)
    estimator: Literal["WEIGHTED_ALIGNED_SCENARIO_FREQUENCY"] = (
        "WEIGHTED_ALIGNED_SCENARIO_FREQUENCY"
    )
    tail_value_policy: Literal["TARGET_BIN_REPRESENTATIVE"] = (
        "TARGET_BIN_REPRESENTATIVE"
    )
    tail_representative_used: bool = False
    taxi_reference_id: str | None = None
    taxi_reference_hash: str | None = None

    @model_validator(mode="after")
    def status_matches_probability(self):
        if self.support_state == "SUPPORTED" and self.probability is None:
            raise ValueError("supported warning probability requires a value")
        if self.support_state == "ABSTAIN" and self.probability is not None:
            raise ValueError("abstained warning probability cannot carry a value")
        return self


@dataclass(frozen=True)
class BatchedWarningResult:
    probability: torch.Tensor
    support: torch.Tensor
    tail_representative_used: torch.Tensor
    sampled_indices: dict[str, torch.Tensor] | None = None


def scenario_uniforms(
    episode_ids: Sequence[str], *, count: int, seed: int
) -> torch.Tensor:
    """V2 target-keyed uniforms, reusing rows for repeated episodes."""
    if count <= 0:
        raise ValueError("M1_SCENARIO_COUNT_MUST_BE_POSITIVE")
    unique = {}
    for episode_id in episode_ids:
        if episode_id in unique:
            continue
        values = []
        for scenario_id in range(count):
            values.append(
                [
                    _uniform_v2(seed, episode_id, scenario_id, target)[0]
                    for target in V2_WARNING_TARGETS
                ]
            )
        unique[episode_id] = torch.tensor(values, dtype=torch.float32)
    return torch.stack([unique[item] for item in episode_ids], dim=0)


def _sample_from_pmf(pmf: torch.Tensor, uniforms: torch.Tensor) -> torch.Tensor:
    while pmf.ndim - 1 < uniforms.ndim:
        pmf = pmf.unsqueeze(-2)
    if pmf.shape[:-1] != uniforms.shape:
        pmf = pmf.expand(*uniforms.shape, pmf.shape[-1])
    cumulative = torch.cumsum(pmf, dim=-1)
    flat = (
        torch.searchsorted(
            cumulative.reshape(-1, cumulative.shape[-1]),
            uniforms.reshape(-1, 1).contiguous(),
        )
        .clamp_max(cumulative.shape[-1] - 1)
        .reshape(-1)
    )
    return flat.reshape(uniforms.shape).to(dtype=torch.long)


def _gather_heads(
    zero: torch.Tensor,
    quantile: torch.Tensor,
    ib_bin: torch.Tensor,
    d_ob_bin: torch.Tensor | None,
):
    """Gather (K, ...)/(K, G, ...) head tables by sampled parent bins."""
    if d_ob_bin is None:
        zero_g = zero[ib_bin]
        quant_g = quantile[ib_bin]
    else:
        zero_g = zero[ib_bin, d_ob_bin]
        quant_g = quantile[ib_bin, d_ob_bin]
    return zero_g, quant_g


def _sample_hurdle_quantile_batch(
    zero_logit: torch.Tensor,
    quantile_logits: torch.Tensor,
    contract: HurdleQuantileContract,
    uniforms: torch.Tensor,
    device: torch.device,
):
    zero_probability = torch.sigmoid(zero_logit)
    quantiles = monotone_positive_quantiles(quantile_logits)
    value = torch.zeros_like(uniforms, dtype=torch.float32, device=device)
    positive = uniforms >= zero_probability
    if positive.any():
        positive_uniform = (uniforms[positive] - zero_probability[positive]) / (
            (1.0 - zero_probability[positive]).clamp_min(1e-12)
        )
        value[positive] = quantile_value(
            quantiles[positive],
            contract.quantile_levels,
            positive_uniform,
            upper_tail_policy=contract.upper_tail_policy,
        )
    finite_index = torch.clamp(
        torch.floor(value / contract.bin_width_minutes).long(),
        0,
        contract.overflow_index - 1,
    )
    overflow = value > contract.max_finite_minutes
    index = torch.where(
        overflow,
        torch.full_like(finite_index, contract.overflow_index),
        finite_index,
    )
    return value, index, overflow


def batched_warning_probability(
    pipeline,
    histories: torch.Tensor,
    *,
    episode_ids: Sequence[str],
    stages: Sequence[str],
    decision_times_utc: Sequence[str | None],
    observed_t_ib: Sequence[str | None],
    observed_d_ob: Sequence[float | None],
    observed_d_tx: Sequence[float | None],
    count: int,
    seed: int,
    return_indices: bool = False,
) -> BatchedWarningResult:
    """Vectorized V2 P(D_TO > 30) sampling for one bundle of decision nodes.

    The ancestral order T_IB_A00 -> D_OB|T_IB_A00 -> D_TX|T_IB_A00,D_OB is
    preserved; D_TO = D_OB + D_TX is derived per scenario.
    """
    model = pipeline.model
    contracts = pipeline.contracts
    hazard: HazardBinContract = contracts[M1_V2_HAZARD_COORDINATE]
    d_ob_contract: HurdleQuantileContract = contracts["D_OB"]
    d_tx_contract: HurdleQuantileContract = contracts["D_TX"]
    device = histories.device
    # Fused state representation consumed by every head call in this bundle.
    state = model.state_representation(histories)
    n = histories.shape[0]
    if (
        len(
            {
                len(episode_ids),
                len(stages),
                len(decision_times_utc),
                len(observed_t_ib),
                len(observed_d_ob),
                len(observed_d_tx),
            }
        )
        != 1
    ):
        raise ValueError("M1_V2_BATCHED_WARNING_SEQUENCE_LENGTH_MISMATCH")
    if n != len(episode_ids):
        raise ValueError("M1_V2_BATCHED_WARNING_NODE_COUNT_MISMATCH")

    uniforms = scenario_uniforms(episode_ids, count=count, seed=seed).to(device)
    supported = torch.ones(n, dtype=torch.bool, device=device)
    temperature = pipeline.temperatures

    # ---- T_IB_A00 (discrete hazard over the internal remaining-time coord) ----
    hazard_pmfs = hazard_pmf(
        model.hazard_logits(state)
        / float(temperature.get(M1_V2_HAZARD_COORDINATE, 1.0)),
        hazard,
    )  # (n, K)
    ib_bin = torch.full((n, count), -1, dtype=torch.long, device=device)
    overflow_ib = torch.zeros((n, count), dtype=torch.bool, device=device)
    for i in range(n):
        stage = stages[i]
        required = required_observations_v2(stage)
        missing = [
            target
            for target in required
            if (target == "T_IB_A00" and observed_t_ib[i] is None)
            or (target == "D_OB" and observed_d_ob[i] is None)
            or (target == "D_TX" and observed_d_tx[i] is None)
        ]
        if missing:
            supported[i] = False
            continue
        if observed_t_ib[i] is not None:
            if decision_times_utc[i] is None:
                supported[i] = False
                continue
            remaining = max(
                0.0,
                (
                    datetime.fromisoformat(observed_t_ib[i])
                    - datetime.fromisoformat(decision_times_utc[i])
                ).total_seconds()
                / 60.0,
            )
            index = hazard.encode(remaining)
            ib_bin[i] = index
            overflow_ib[i] = hazard.tail_state(index) == "OVERFLOW"
        else:
            if decision_times_utc[i] is None:
                supported[i] = False
                continue
            index = _sample_from_pmf(hazard_pmfs[i : i + 1], uniforms[i : i + 1, :, 0])
            ib_bin[i] = index
            overflow_ib[i] = index == hazard.overflow_index

    # ---- D_OB (hurdle + conditional quantile, parent T_IB_A00) ----
    d_ob_value = torch.full(
        (n, count), float("nan"), dtype=torch.float32, device=device
    )
    d_ob_bin = torch.full((n, count), -1, dtype=torch.long, device=device)
    overflow_ob = torch.zeros((n, count), dtype=torch.bool, device=device)
    for i in range(n):
        if not supported[i]:
            continue
        if observed_d_ob[i] is not None:
            value = float(observed_d_ob[i])
            index = d_ob_contract.encode(value)
            d_ob_value[i] = value
            d_ob_bin[i] = index
            overflow_ob[i] = d_ob_contract.tail_state(index) == "OVERFLOW"
            continue
        if (ib_bin[i] < 0).any():
            supported[i] = False
            continue
        # Evaluate the D_OB heads for every hazard bin once per node.
        all_bins = torch.arange(hazard.class_count, device=device)
        hist = state[i : i + 1].expand(hazard.class_count, -1)
        zero, quant = model.d_ob_heads(hist, all_bins)
        zero = zero.squeeze(-1) / float(temperature.get("D_OB", 1.0))
        quant = quant / float(temperature.get("D_OB", 1.0))
        zero_g, quant_g = _gather_heads(zero, quant, ib_bin[i], None)
        value, index, overflow = _sample_hurdle_quantile_batch(
            zero_g, quant_g, d_ob_contract, uniforms[i, :, 1], device
        )
        d_ob_value[i] = value
        d_ob_bin[i] = index
        overflow_ob[i] = overflow

    # ---- D_TX (hurdle + conditional quantile, parents T_IB_A00, D_OB) ----
    d_tx_value = torch.full(
        (n, count), float("nan"), dtype=torch.float32, device=device
    )
    d_tx_bin = torch.full((n, count), -1, dtype=torch.long, device=device)
    overflow_tx = torch.zeros((n, count), dtype=torch.bool, device=device)
    for i in range(n):
        if not supported[i]:
            continue
        if observed_d_tx[i] is not None:
            value = float(observed_d_tx[i])
            index = d_tx_contract.encode(value)
            d_tx_value[i] = value
            d_tx_bin[i] = index
            overflow_tx[i] = d_tx_contract.tail_state(index) == "OVERFLOW"
            continue
        if (ib_bin[i] < 0).any() or (d_ob_bin[i] < 0).any():
            supported[i] = False
            continue
        hidden = model.hidden_size
        hazard_count = hazard.class_count
        ob_count = d_ob_contract.class_count
        all_ib = torch.arange(hazard_count, device=device)
        hist = state[i : i + 1].expand(hazard_count, -1)
        ibc = model.ib_embedding(all_ib)
        features = torch.cat([hist, ibc, torch.zeros_like(ibc)], dim=-1)
        zero_base = model.d_tx_zero_head(features).squeeze(-1)  # (K,)
        quant_base = model.d_tx_quantile_head(features)  # (K, Q)
        ob_emb = model.d_ob_embedding.weight  # (G, H)
        # The D_OB parent block is the trailing ``hidden_size`` columns of the
        # D_TX head input regardless of the fused state width.
        zero_contrib = model.d_tx_zero_head.weight[:, -hidden:] @ ob_emb.t()  # (1, G)
        quant_contrib = (
            model.d_tx_quantile_head.weight[:, -hidden:] @ ob_emb.t()
        )  # (Q, G)
        zero = (zero_base[:, None] + zero_contrib) / float(
            temperature.get("D_TX", 1.0)
        )  # (K, G)
        quant = (
            quant_base[:, None, :] + quant_contrib.permute(1, 0)[None, :, :]
        ) / float(
            temperature.get("D_TX", 1.0)
        )  # (K, G, Q)
        zero_g, quant_g = _gather_heads(zero, quant, ib_bin[i], d_ob_bin[i])
        value, index, overflow = _sample_hurdle_quantile_batch(
            zero_g, quant_g, d_tx_contract, uniforms[i, :, 2], device
        )
        d_tx_value[i] = value
        d_tx_bin[i] = index
        overflow_tx[i] = overflow

    d_to = d_ob_value + d_tx_value
    probabilities = torch.full((n,), float("nan"), dtype=torch.float64, device=device)
    tails = torch.zeros(n, dtype=torch.bool, device=device)
    probabilities[supported] = (
        d_to[supported] > PRINCIPAL_WARNING_THRESHOLD_MINUTES
    ).sum(dim=1, dtype=torch.int64).to(dtype=torch.float64) / count
    tails[supported] = (
        overflow_ib[supported] | overflow_ob[supported] | overflow_tx[supported]
    ).any(dim=1)
    indices = None
    if return_indices:
        indices = {
            "T_IB_A00": ib_bin,
            "D_OB": d_ob_bin,
            "D_TX": d_tx_bin,
        }
    return BatchedWarningResult(
        probability=probabilities,
        support=supported,
        tail_representative_used=tails,
        sampled_indices=indices,
    )


def warning_probability(
    scenarios: Sequence[M1V2Scenario],
    *,
    threshold_minutes: float = PRINCIPAL_WARNING_THRESHOLD_MINUTES,
    event_id: str = PRINCIPAL_WARNING_EVENT,
) -> WarningProbability:
    """Estimate P(D_TO > threshold) from one V2 aligned scenario bundle.

    The function never drops unsupported scenarios; if any formal D_TO value
    is unavailable the whole node abstains.
    """

    if threshold_minutes < 0:
        raise ValueError("warning threshold must be nonnegative")
    rows = tuple(scenarios)
    if not rows:
        return WarningProbability(
            episode_id=None,
            decision_node_id=None,
            event_id=event_id,
            delay_threshold_minutes=threshold_minutes,
            support_state="ABSTAIN",
            reason_code="NO_ALIGNED_SCENARIOS",
            scenario_count=0,
            scenario_weight_sum=0.0,
            exceedance_weight=0.0,
        )

    identities = {(row.episode_id, row.decision_node_id) for row in rows}
    if len(identities) != 1:
        raise ValueError("warning probability requires one episode/decision node")
    if len({row.scenario_id for row in rows}) != len(rows):
        raise ValueError("warning probability requires unique scenario ids")
    if any(row.scenario_weight <= 0 for row in rows):
        raise ValueError("warning probability requires positive scenario weights")

    episode_id, decision_node_id = next(iter(identities))
    weight_sum = float(sum(row.scenario_weight for row in rows))
    derived = tuple(row.d_to_minutes for row in rows)
    supports = {row.d_to_support for row in rows}
    tail_used = any(
        row.overflow_t_ib or row.overflow_d_ob or row.overflow_d_tx for row in rows
    )
    reference_ids = {row.taxi_reference_id for row in rows}
    reference_hashes = {row.taxi_reference_hash for row in rows}
    if any(value is None for value in derived) or supports != {"SUPPORTED"}:
        return WarningProbability(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            event_id=event_id,
            delay_threshold_minutes=threshold_minutes,
            support_state="ABSTAIN",
            reason_code="M1_V2_D_TO_UNAVAILABLE",
            scenario_count=len(rows),
            scenario_weight_sum=weight_sum,
            exceedance_weight=0.0,
            tail_representative_used=tail_used,
            taxi_reference_id=(
                next(iter(reference_ids)) if len(reference_ids) == 1 else None
            ),
            taxi_reference_hash=(
                next(iter(reference_hashes)) if len(reference_hashes) == 1 else None
            ),
        )

    exceedance_weight = float(
        sum(
            row.scenario_weight
            for row, value in zip(rows, derived)
            if value is not None and value > threshold_minutes
        )
    )
    return WarningProbability(
        episode_id=episode_id,
        decision_node_id=decision_node_id,
        event_id=event_id,
        delay_threshold_minutes=threshold_minutes,
        probability=exceedance_weight / weight_sum,
        support_state="SUPPORTED",
        reason_code="M1_V2_D_TO_ALIGNED_SCENARIOS",
        scenario_count=len(rows),
        scenario_weight_sum=weight_sum,
        exceedance_weight=exceedance_weight,
        tail_representative_used=tail_used,
        taxi_reference_id=(
            next(iter(reference_ids)) if len(reference_ids) == 1 else None
        ),
        taxi_reference_hash=(
            next(iter(reference_hashes)) if len(reference_hashes) == 1 else None
        ),
    )
