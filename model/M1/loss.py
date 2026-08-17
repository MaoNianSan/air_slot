import torch
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
