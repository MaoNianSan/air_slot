from dataclasses import dataclass
from typing import Literal, Sequence

import torch
from torch.nn import functional as F
from pydantic import Field, model_validator

from model.common.value_objects import FrozenModel

from .contracts import AlignedScenario
from .scenarios import _uniform


PRINCIPAL_WARNING_EVENT = "D_TO_POST_GT_30"
PRINCIPAL_WARNING_THRESHOLD_MINUTES = 30.0


class WarningProbability(FrozenModel):
    """Weighted probability for the frozen signed-M1 takeoff-delay event."""

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
    tail_value_policy: Literal["TARGET_BIN_REPRESENTATIVE"] = "TARGET_BIN_REPRESENTATIVE"
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


def scenario_uniforms(episode_ids: Sequence[str], *, count: int, seed: int) -> torch.Tensor:
    """Return the frozen target-keyed uniforms, reusing rows for repeated episodes."""
    if count <= 0:
        raise ValueError("M1_SCENARIO_COUNT_MUST_BE_POSITIVE")
    unique = {}
    for episode_id in episode_ids:
        if episode_id in unique:
            continue
        values = []
        for scenario_id in range(count):
            values.append([
                _uniform(seed, episode_id, scenario_id, target)[0]
                for target in ("R_IB", "DELTA_OB", "T_TX")
            ])
        unique[episode_id] = torch.tensor(values, dtype=torch.float32)
    return torch.stack([unique[item] for item in episode_ids], dim=0)


def _encode_observed(values: Sequence[float | None], bin_contract) -> torch.Tensor:
    return torch.tensor([
        -1 if value is None else bin_contract.encode(float(value))
        for value in values
    ], dtype=torch.long)


def _representatives(bin_contract, *, device):
    values, underflow, overflow = zip(*(
        bin_contract.representative(index)
        for index in range(bin_contract.class_count)
    ))
    return (
        torch.tensor(values, dtype=torch.float32, device=device),
        torch.tensor(underflow, dtype=torch.bool, device=device),
        torch.tensor(overflow, dtype=torch.bool, device=device),
    )


def _sample_from_logits(logits: torch.Tensor, uniforms: torch.Tensor) -> torch.Tensor:
    while logits.ndim - 1 < uniforms.ndim:
        logits = logits.unsqueeze(-2)
    if logits.shape[:-1] != uniforms.shape:
        logits = logits.expand(*uniforms.shape, logits.shape[-1])
    probabilities = torch.softmax(logits, dim=-1)
    cumulative = torch.cumsum(probabilities, dim=-1)
    flat = torch.searchsorted(
        cumulative.reshape(-1, cumulative.shape[-1]),
        uniforms.reshape(-1, 1),
    ).clamp_max(cumulative.shape[-1] - 1).reshape(-1)
    return flat.reshape(uniforms.shape).to(dtype=torch.long)


def _sample_post_ib(
    model,
    history: torch.Tensor,
    ib_indices: torch.Tensor,
    uniforms: torch.Tensor,
    bins,
    temperatures: dict[str, float],
    taxi_reference: torch.Tensor,
    *,
    observed_delta: torch.Tensor,
    observed_tx: torch.Tensor,
    return_indices: bool,
) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor] | None]:
    """Sample the common POST_IB_PRE_OB / POST_OB_PRE_TO path.

    The T_TX head is affine in the two parent embeddings. Evaluating all DELTA
    categories once per node avoids constructing one Python scenario object per
    draw while preserving the ordered factorization and target-keyed uniforms.
    """
    device = history.device
    n, scenarios = uniforms.shape[:2]
    ib = ib_indices[:, 0]
    ib_logits = model.conditioned_logits(history, "DELTA_OB", ib_index=ib)
    delta_rep, delta_under, delta_over = _representatives(bins["DELTA_OB"], device=device)
    delta_indices = observed_delta[:, None].expand(n, scenarios).clone()
    sampled_delta = observed_delta < 0
    if sampled_delta.any():
        sampled = _sample_from_logits(
            ib_logits[sampled_delta] / float(temperatures["DELTA_OB"]),
            uniforms[sampled_delta, :, 1],
        )
        delta_indices[sampled_delta] = sampled

    tx_indices = observed_tx[:, None].expand(n, scenarios).clone()
    sampled_tx = observed_tx < 0
    tx_tail = torch.zeros((n, scenarios), dtype=torch.bool, device=device)
    if sampled_tx.any():
        history_tx = history[sampled_tx]
        ib_tx = ib[sampled_tx]
        sampled_delta_tx = delta_indices[sampled_tx]
        # Dense parent-conditioned logits are evaluated for the unique DELTA
        # support and gathered by the sampled category.
        tx_base = model.tx_head(
            torch.cat([
                history_tx,
                model.ib_embedding(ib_tx),
                torch.zeros_like(model.delta_ob_embedding.weight[0]).expand(history_tx.shape[0], -1),
            ], dim=-1)
        )
        tx_w_delta = model.tx_head.weight[:, -model.hidden_size:]
        tx_delta_contrib = F.linear(model.delta_ob_embedding.weight, tx_w_delta, None)
        tx_delta_logits = tx_base[:, None, :] + tx_delta_contrib[None, :, :]
        tx_probs = torch.softmax(tx_delta_logits / float(temperatures["T_TX"]), dim=-1)
        tx_cdf = torch.cumsum(tx_probs, dim=-1)
        gathered = tx_cdf.gather(
            1, sampled_delta_tx[..., None].expand(-1, -1, tx_cdf.shape[-1])
        )
        tx_uniforms = uniforms[sampled_tx, :, 2]
        sampled = torch.searchsorted(
            gathered.reshape(-1, gathered.shape[-1]), tx_uniforms.reshape(-1, 1)
        ).clamp_max(bins["T_TX"].class_count - 1).reshape(-1, scenarios)
        tx_indices[sampled_tx] = sampled
        tx_tail[sampled_tx] = sampled == bins["T_TX"].overflow_index

    delta_values = delta_rep[delta_indices]
    tx_rep, _tx_under, tx_over = _representatives(bins["T_TX"], device=device)
    d_to = delta_values + tx_rep[tx_indices] - taxi_reference[:, None]
    probability = (
        (d_to > PRINCIPAL_WARNING_THRESHOLD_MINUTES)
        .sum(dim=1, dtype=torch.int64)
        .to(dtype=torch.float64)
        / scenarios
    )
    tail = (
        delta_under[delta_indices]
        | delta_over[delta_indices]
        | tx_tail
        | tx_over[tx_indices]
    ).any(dim=1)
    indices = None
    if return_indices:
        indices = {"R_IB": ib_indices, "DELTA_OB": delta_indices, "T_TX": tx_indices}
    return probability, tail, indices


def _sample_pre_ib(
    model,
    history: torch.Tensor,
    uniforms: torch.Tensor,
    bins,
    temperatures: dict[str, float],
    taxi_reference: torch.Tensor,
    *,
    return_indices: bool,
) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor] | None]:
    device = history.device
    n, scenarios = uniforms.shape[:2]
    ib_logits = model.conditioned_logits(history, "R_IB")
    ib_indices = _sample_from_logits(
        ib_logits[:, None, :].expand(n, scenarios, -1) / float(temperatures["R_IB"]),
        uniforms[..., 0],
    )
    delta_w_history = model.delta_ob_head.weight[:, :model.hidden_size]
    delta_w_ib = model.delta_ob_head.weight[:, model.hidden_size:]
    delta_base = F.linear(history, delta_w_history, model.delta_ob_head.bias)
    delta_parent = F.linear(model.ib_embedding.weight, delta_w_ib, None)
    delta_logits = delta_base[:, None, :] + delta_parent[ib_indices]
    delta_indices = _sample_from_logits(
        delta_logits / float(temperatures["DELTA_OB"]), uniforms[..., 1]
    )

    tx_w_history = model.tx_head.weight[:, :model.hidden_size]
    tx_w_ib = model.tx_head.weight[:, model.hidden_size:2 * model.hidden_size]
    tx_w_delta = model.tx_head.weight[:, 2 * model.hidden_size:]
    tx_base = F.linear(history, tx_w_history, model.tx_head.bias)
    tx_ib = F.linear(model.ib_embedding.weight, tx_w_ib, None)
    tx_delta = F.linear(model.delta_ob_embedding.weight, tx_w_delta, None)
    tx_logits = tx_base[:, None, :] + tx_ib[ib_indices] + tx_delta[delta_indices]
    tx_indices = _sample_from_logits(
        tx_logits / float(temperatures["T_TX"]), uniforms[..., 2]
    )
    delta_rep, delta_under, delta_over = _representatives(bins["DELTA_OB"], device=device)
    tx_rep, _tx_under, tx_over = _representatives(bins["T_TX"], device=device)
    d_to = delta_rep[delta_indices] + tx_rep[tx_indices] - taxi_reference[:, None]
    probability = (
        (d_to > PRINCIPAL_WARNING_THRESHOLD_MINUTES)
        .sum(dim=1, dtype=torch.int64)
        .to(dtype=torch.float64)
        / scenarios
    )
    tail = (
        delta_under[delta_indices]
        | delta_over[delta_indices]
        | tx_over[tx_indices]
        | (ib_indices == bins["R_IB"].overflow_index)
    ).any(dim=1)
    indices = None
    if return_indices:
        indices = {"R_IB": ib_indices, "DELTA_OB": delta_indices, "T_TX": tx_indices}
    return probability, tail, indices


def batched_warning_probability(
    pipeline,
    histories: torch.Tensor,
    *,
    episode_ids: Sequence[str],
    observed_r_ib: Sequence[float | None],
    observed_delta_ob: Sequence[float | None],
    observed_t_tx: Sequence[float | None],
    taxi_reference_minutes: Sequence[float | None],
    count: int,
    seed: int,
    return_indices: bool = False,
    uniforms: torch.Tensor | None = None,
) -> BatchedWarningResult:
    """Vectorized aligned scenario sampling for one node batch.

    RNG keys, ordered parent conditioning, representative tails, and strict
    ``D_TO > 30`` semantics are shared with :func:`ancestral_sample`.
    """
    if histories.ndim != 2 or len(episode_ids) != histories.shape[0]:
        raise ValueError("M1_BATCHED_WARNING_HISTORY_SHAPE_MISMATCH")
    device = histories.device
    n = histories.shape[0]
    if uniforms is None:
        uniforms = scenario_uniforms(episode_ids, count=count, seed=seed)
    uniforms = uniforms.to(device)
    if uniforms.shape != (n, count, 3):
        raise ValueError("M1_BATCHED_WARNING_UNIFORM_SHAPE_MISMATCH")
    refs = torch.tensor([
        float(value) if value is not None else float("nan")
        for value in taxi_reference_minutes
    ], dtype=torch.float32, device=device)
    supported = torch.isfinite(refs)
    safe_refs = torch.where(supported, refs, torch.zeros_like(refs))
    ib_observed = _encode_observed(observed_r_ib, pipeline.bins["R_IB"]).to(device)
    delta_observed = _encode_observed(observed_delta_ob, pipeline.bins["DELTA_OB"]).to(device)
    tx_observed = _encode_observed(observed_t_tx, pipeline.bins["T_TX"]).to(device)
    probabilities = torch.zeros(n, dtype=torch.float64, device=device)
    tails = torch.zeros(n, dtype=torch.bool, device=device)
    all_indices = {
        name: torch.full((n, count), -1, dtype=torch.long, device=device)
        for name in ("R_IB", "DELTA_OB", "T_TX")
    } if return_indices else None

    pre = ib_observed < 0
    if pre.any():
        probability, tail, indices = _sample_pre_ib(
            pipeline.model, histories[pre], uniforms[pre], pipeline.bins,
            pipeline.temperatures, safe_refs[pre], return_indices=return_indices,
        )
        probabilities[pre], tails[pre] = probability, tail
        if all_indices is not None and indices is not None:
            for name in all_indices:
                all_indices[name][pre] = indices[name]

    post_ib = ~pre
    if post_ib.any():
        probability, tail, indices = _sample_post_ib(
            pipeline.model, histories[post_ib],
            ib_observed[post_ib, None].expand(-1, count), uniforms[post_ib], pipeline.bins,
            pipeline.temperatures, safe_refs[post_ib], observed_delta=delta_observed[post_ib],
            observed_tx=tx_observed[post_ib], return_indices=return_indices,
        )
        probabilities[post_ib], tails[post_ib] = probability, tail
        if all_indices is not None and indices is not None:
            for name in all_indices:
                all_indices[name][post_ib] = indices[name]

    probabilities[~supported] = float("nan")
    tails[~supported] = False
    if all_indices is not None:
        for name in all_indices:
            all_indices[name][~supported] = -1
    return BatchedWarningResult(
        probability=probabilities,
        support=supported,
        tail_representative_used=tails,
        sampled_indices=all_indices,
    )


def warning_probability(
    scenarios: Sequence[AlignedScenario],
    *,
    threshold_minutes: float = PRINCIPAL_WARNING_THRESHOLD_MINUTES,
    event_id: str = PRINCIPAL_WARNING_EVENT,
) -> WarningProbability:
    """Estimate P(D_TO > threshold) from one aligned joint-scenario bundle.

    The function never drops unsupported scenarios. If the train-frozen taxi
    reference or any derived D_TO value is unavailable, the whole node abstains.
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
    reference_ids = {row.taxi_reference_id for row in rows}
    reference_hashes = {row.taxi_reference_hash for row in rows}
    reference_states = {row.taxi_reference_support_state for row in rows}
    formal_reference = (
        len(reference_ids) == 1
        and None not in reference_ids
        and len(reference_hashes) == 1
        and None not in reference_hashes
        and reference_states == {"SUPPORTED"}
    )
    derived = tuple(row.d_to_minutes for row in rows)
    tail_used = any(
        row.underflow_delta_ob or row.overflow_delta_ob or row.overflow_tx
        for row in rows
    )
    if not formal_reference or any(value is None for value in derived):
        return WarningProbability(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            event_id=event_id,
            delay_threshold_minutes=threshold_minutes,
            support_state="ABSTAIN",
            reason_code="TRAIN_FROZEN_TAXI_REFERENCE_OR_D_TO_UNAVAILABLE",
            scenario_count=len(rows),
            scenario_weight_sum=weight_sum,
            exceedance_weight=0.0,
            tail_representative_used=tail_used,
            taxi_reference_id=next(iter(reference_ids)) if len(reference_ids) == 1 else None,
            taxi_reference_hash=next(iter(reference_hashes)) if len(reference_hashes) == 1 else None,
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
        reason_code="SIGNED_D_TO_ALIGNED_SCENARIOS",
        scenario_count=len(rows),
        scenario_weight_sum=weight_sum,
        exceedance_weight=exceedance_weight,
        tail_representative_used=tail_used,
        taxi_reference_id=next(iter(reference_ids)),
        taxi_reference_hash=next(iter(reference_hashes)),
    )
