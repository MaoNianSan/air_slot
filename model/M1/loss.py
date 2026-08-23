import torch

from model.common.errors import ContractError

from .contracts import TargetBinContract


def interval_nll(logits: torch.Tensor, bins: TargetBinContract, *, lower: torch.Tensor,
                 upper: torch.Tensor, active: torch.Tensor, weights: torch.Tensor | None = None):
    logp = torch.log_softmax(logits, -1); losses=[]; selected=[]
    for index in range(logits.shape[0]):
        if not bool(active[index]): continue
        lo, hi = float(lower[index]), float(upper[index])
        indices = []
        for bin_index in range(bins.finite_start_index, bins.overflow_index):
            start = bins.finite_minimum_minutes + (
                bin_index - bins.finite_start_index
            ) * bins.bin_width_minutes
            if start < hi and start + bins.bin_width_minutes > lo:
                indices.append(bin_index)
        if bins.signed and lo < bins.finite_minimum_minutes:
            indices.append(bins.underflow_index)
        if not indices: indices=[bins.encode(lo)]
        if hi >= bins.max_finite_minutes + bins.bin_width_minutes: indices.append(bins.class_count-1)
        losses.append(-torch.logsumexp(logp[index, indices], 0)); selected.append(index)
    if not losses: return logits.sum() * 0
    stack=torch.stack(losses)
    if weights is not None: stack=stack*weights[torch.tensor(selected,device=weights.device)]
    return stack.mean()


def exact_nll(logits, labels, active, weights=None):
    losses=torch.nn.functional.cross_entropy(logits, labels, reduction="none")
    mask=active.float(); losses=losses*mask
    if weights is not None: losses=losses*weights
    return losses.sum()/mask.sum().clamp_min(1)



# ---------------------------------------------------------------------------
# V2 losses: discrete hazard (T_IB_A00) and hurdle + conditional quantile
# (D_OB / D_TX).  The V1 interval/exact losses above remain LEGACY_V1.
# ---------------------------------------------------------------------------


def monotone_positive_quantiles(logits: torch.Tensor) -> torch.Tensor:
    """Positive, strictly increasing quantiles from unconstrained head logits.

    q_1 = softplus(logits[..., 0]) > 0 and q_k strictly increases, so the
    positive conditional quantile curve is always monotone with positive
    support by construction.
    """
    increments = torch.nn.functional.softplus(logits)
    return torch.cumsum(increments, dim=-1)


def hazard_pmf(logits: torch.Tensor, contract) -> torch.Tensor:
    """Discrete-hazard PMF over ``contract.class_count`` bins.

    ``logits`` has shape (..., finite_class_count); each entry is the hazard
    for its finite remaining-time bin.  The final class is the survival tail
    P(T >= max_finite), and the returned PMF always sums to one.
    """
    hazard = torch.sigmoid(logits)
    survival = torch.cumprod(1.0 - hazard, dim=-1)
    shifted = torch.cat(
        [torch.ones_like(survival[..., :1]), survival[..., :-1]], dim=-1
    )
    pmf = hazard * shifted
    tail = survival[..., -1:]
    return torch.cat([pmf, tail], dim=-1)


def hazard_interval_nll(
    logits: torch.Tensor,
    contract,
    *,
    lower: torch.Tensor,
    upper: torch.Tensor,
    active: torch.Tensor,
    weights: torch.Tensor | None = None,
    denominator: int | float | None = None,
):
    """Negative discrete-hazard likelihood over remaining-time bins.

    For each active row the likelihood is the summed probability mass of every
    bin overlapping the label interval [lower, upper].  Exact-minute labels
    pass lower == upper.  With ``denominator`` the term is the weighted sum
    over active rows divided by that global count (batch-split invariant).
    Formal V2 training uses episode-normalized weights and an active-episode
    denominator; otherwise this is the mean over the batch's active rows.
    """
    pmf = hazard_pmf(logits, contract)
    logp = torch.log(pmf.clamp_min(1e-12))
    losses, selected = [], []
    for index in range(logits.shape[0]):
        if not bool(active[index]):
            continue
        lo, hi = float(lower[index]), float(upper[index])
        indices = []
        for bin_index in range(contract.class_count):
            start = contract.bin_start(bin_index)
            end = contract.bin_end(bin_index)
            if start < hi and end > lo:
                indices.append(bin_index)
        if not indices:
            indices = [contract.encode(lo)]
        losses.append(-torch.logsumexp(logp[index, indices], 0))
        selected.append(index)
    if not losses:
        return logits.sum() * 0
    stack = torch.stack(losses)
    if weights is not None:
        stack = stack * weights[torch.tensor(selected, device=weights.device)]
    if denominator is not None:
        if denominator == 0:
            return logits.sum() * 0
        return stack.sum() / float(denominator)
    return stack.mean()


def pinball_loss(
    value: torch.Tensor,
    quantiles: torch.Tensor,
    levels: tuple[float, ...],
) -> torch.Tensor:
    """Mean pinball loss across the declared positive quantile levels."""
    error = value.unsqueeze(-1) - quantiles
    levels_t = torch.as_tensor(levels, dtype=error.dtype, device=error.device)
    loss = torch.where(error >= 0, levels_t * error, (levels_t - 1) * error)
    return loss.mean(dim=-1)


def hurdle_quantile_loss(
    zero_logit: torch.Tensor,
    quantile_logits: torch.Tensor,
    contract,
    *,
    zero: torch.Tensor,
    value: torch.Tensor,
    active: torch.Tensor,
    weights: torch.Tensor | None = None,
    zero_weights: torch.Tensor | None = None,
    positive_weights: torch.Tensor | None = None,
    zero_denominator: int | float | None = None,
    positive_denominator: int | float | None = None,
) -> torch.Tensor:
    """Hurdle + positive conditional quantile loss for D_OB / D_TX.

    ``zero`` is the observed zero indicator (1 when D == 0) and ``value`` is
    the observed nonnegative delay in minutes.  Active rows contribute the
    zero-mass Bernoulli loss; active positive rows additionally contribute the
    pinball loss at the declared quantile levels. ``zero_weights`` and
    ``positive_weights`` let the terms use distinct episode normalization; the
    legacy ``weights`` argument remains a shared fallback. With global episode
    denominators the result is batch-split invariant.
    """
    mask = active.float()
    zero_target = zero.float()
    zero_row_weights = weights if zero_weights is None else zero_weights
    positive_row_weights = weights if positive_weights is None else positive_weights
    if zero_logit.shape != zero_target.shape:
        if zero_logit.ndim == zero_target.ndim + 1 and zero_logit.shape[-1] == 1:
            zero_logit = zero_logit.squeeze(-1)
        else:
            raise ValueError(
                f"zero_logit shape {tuple(zero_logit.shape)} is incompatible "
                f"with zero target shape {tuple(zero_target.shape)}"
            )
    zero_losses = torch.nn.functional.binary_cross_entropy_with_logits(
        zero_logit, zero_target, reduction="none"
    )
    if zero_row_weights is not None:
        zero_losses = zero_losses * zero_row_weights
    if zero_denominator is not None:
        zero_term = (
            (zero_losses * mask).sum() / float(zero_denominator)
            if zero_denominator else torch.zeros((), dtype=zero_logit.dtype,
                                                 device=zero_logit.device)
        )
    else:
        zero_term = (zero_losses * mask).sum() / mask.sum().clamp_min(1)

    quantiles = monotone_positive_quantiles(quantile_logits)
    positive_mask = mask * (value > 0).float()
    if positive_mask.sum() == 0:
        positive_term = torch.zeros((), dtype=zero_logit.dtype, device=zero_logit.device)
    else:
        # Pinball is evaluated only on active positive rows so that inactive
        # (NaN-valued) rows never poison the mean.
        active_positive = positive_mask.bool()
        positive_losses = pinball_loss(
            value[active_positive], quantiles[active_positive],
            contract.quantile_levels,
        )
        if positive_row_weights is not None:
            positive_losses = positive_losses * positive_row_weights[active_positive]
        if positive_denominator is not None:
            positive_term = (
                positive_losses.sum() / float(positive_denominator)
                if positive_denominator else torch.zeros(
                    (), dtype=positive_losses.dtype, device=positive_losses.device)
            )
        else:
            positive_term = positive_losses.sum() / positive_mask.sum().clamp_min(1)
    return zero_term + positive_term




def _quantile_tail_values(
    quantiles: torch.Tensor,
    levels: tuple[float, ...],
) -> tuple[float, torch.Tensor, torch.Tensor]:
    """Return (q_max level, anchor Q(q_max) (B,), last-segment slope (B,))."""
    batch, quantile_count = quantiles.shape
    q_max = float(levels[-1])
    v_max = quantiles[:, -1]
    if quantile_count >= 2:
        q_prev = float(levels[-2])
        v_prev = quantiles[:, -2]
    else:
        q_prev = 0.0
        v_prev = torch.zeros(batch, dtype=quantiles.dtype, device=quantiles.device)
    slope = (v_max - v_prev) / max(q_max - q_prev, 1e-12)
    return q_max, v_max, slope


def _apply_quantile_piecewise(
    flat_uu: torch.Tensor,
    lo: torch.Tensor,
    hi: torch.Tensor,
    vlo: torch.Tensor,
    vhi: torch.Tensor,
    *,
    q_max: float,
    tail_anchor: torch.Tensor,
    slope: torch.Tensor,
    upper_tail_policy: str,
) -> torch.Tensor:
    """Evaluate Q(flat_uu) on the declared grid, then resolve the tail region.

    ``flat_uu`` is 1-D; ``lo/hi/vlo/vhi`` have the same leading length.
    ``u > q_max`` is never silently clamped to ``Q(q_max)`` (Round 2.1).
    """
    weight = ((flat_uu - lo) / (hi - lo).clamp_min(1e-12)).clamp(0.0, 1.0)
    base = vlo + weight * (vhi - vlo)
    tail_mask = flat_uu > q_max + 1e-9
    if not bool(tail_mask.any()):
        return base
    if upper_tail_policy == "UNRESOLVED":
        raise ContractError("M1_QUANTILE_UPPER_TAIL_UNRESOLVED")
    if upper_tail_policy == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS":
        raise ContractError("M1_QUANTILE_EXPLICIT_TAIL_CLASS_REQUIRED")
    if upper_tail_policy == "DECLARED_FROZEN":
        raise ContractError("M1_QUANTILE_UPPER_TAIL_RULE_NOT_IMPLEMENTED")
    if upper_tail_policy != "TEST_ONLY_LINEAR":
        raise ContractError(f"M1_QUANTILE_UPPER_TAIL_POLICY_UNKNOWN:{upper_tail_policy}")
    tail = tail_anchor + (flat_uu - q_max) * slope
    return torch.where(tail_mask, tail, base)


def quantile_value(
    quantiles: torch.Tensor,
    levels: tuple[float, ...],
    u: torch.Tensor,
    *,
    upper_tail_policy: str = "UNRESOLVED",
    upper_tail_policy_reference: str | None = None,
) -> torch.Tensor:
    """Piecewise-linear interpolation of the positive quantile function Q(u).

    ``quantiles`` has shape (B, Q) and is strictly increasing positive; the
    curve is anchored at Q(0) = 0.  ``u`` may be a scalar (same uniform for
    every row), a (B,) tensor (one uniform per row), or a (B, S) tensor of
    uniforms; the output mirrors the ``u`` shape (scalar ``u`` still returns
    one value per row, (B,)).

    Round 2.1 tail contract: for ``u > q_max`` the value is never silently
    clamped to ``Q(q_max)``.  ``upper_tail_policy`` follows
    ``HurdleQuantileContract.upper_tail_policy``:
    - ``UNRESOLVED`` (legacy unresolved state): raise
      ``M1_QUANTILE_UPPER_TAIL_UNRESOLVED``;
    - ``FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS``: raise
      ``M1_QUANTILE_EXPLICIT_TAIL_CLASS_REQUIRED``; callers must emit the
      explicit tail class and preserve the observed scalar separately;
    - ``TEST_ONLY_LINEAR``: linear extrapolation with the last-segment slope
      (synthetic smoke fixtures only);
    - ``DECLARED_FROZEN``: raise ``M1_QUANTILE_UPPER_TAIL_RULE_NOT_IMPLEMENTED``
      until a frozen tail rule is registered; ``upper_tail_policy_reference``
      is accepted for the future frozen-rule registry and otherwise unused.
    """
    batch, quantile_count = quantiles.shape
    if quantile_count != len(levels):
        raise ValueError("quantile tensor width must match declared levels")
    levels_t = torch.as_tensor(levels, dtype=quantiles.dtype, device=quantiles.device)
    grid = torch.cat([torch.zeros(1, dtype=levels_t.dtype, device=levels_t.device), levels_t])
    values = torch.cat([torch.zeros(batch, 1, dtype=quantiles.dtype, device=quantiles.device), quantiles], dim=-1)
    uu = torch.as_tensor(u, dtype=quantiles.dtype, device=quantiles.device)
    q_max, tail_anchor, slope = _quantile_tail_values(quantiles, levels)

    def _resolve(flat_uu, lo, hi, vlo, vhi, per_row_anchor, per_row_slope):
        return _apply_quantile_piecewise(
            flat_uu, lo, hi, vlo, vhi,
            q_max=q_max, tail_anchor=per_row_anchor, slope=per_row_slope,
            upper_tail_policy=upper_tail_policy,
        )

    if uu.dim() == 0:
        index = int(torch.searchsorted(grid, uu, right=False).clamp(1, quantile_count)) - 1
        lo = grid[index].expand(batch)
        hi = grid[index + 1].expand(batch)
        vlo = values[:, index]
        vhi = values[:, index + 1]
        return _resolve(uu.expand(batch), lo, hi, vlo, vhi, tail_anchor, slope)
    if uu.dim() == 1:
        if uu.shape[0] != batch:
            raise ValueError("one uniform per row required for 1-D quantile interpolation")
        index = torch.searchsorted(grid, uu, right=False).clamp(1, quantile_count) - 1
        rows = torch.arange(batch, device=uu.device)
        return _resolve(uu, grid[index], grid[index + 1],
                        values[rows, index], values[rows, index + 1],
                        tail_anchor, slope)
    if uu.dim() == 2:
        rows_count, scenarios = uu.shape
        if rows_count != batch:
            raise ValueError("quantile row count must match uniform row count")
        flat_u = uu.reshape(-1)
        total = flat_u.numel()
        grid_batch = grid.unsqueeze(0).expand(total, -1)
        index = (
            torch.searchsorted(grid_batch, flat_u.unsqueeze(-1), right=False)
            .squeeze(-1)
            .clamp(1, quantile_count)
            - 1
        )
        rows = torch.arange(total, device=uu.device) // scenarios
        flat_values = values.reshape(-1)
        vlo = flat_values[rows * (quantile_count + 1) + index]
        vhi = flat_values[rows * (quantile_count + 1) + index + 1]
        return _resolve(flat_u, grid[index], grid[index + 1], vlo, vhi,
                        tail_anchor[rows], slope[rows]).reshape(uu.shape)
    raise ValueError("quantile interpolation supports scalar, (B,), or (B, S) uniforms")
