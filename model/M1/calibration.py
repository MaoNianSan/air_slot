import torch


def fit_temperature(logits: torch.Tensor, labels: torch.Tensor, active: torch.Tensor, steps: int = 50) -> float:
    log_temperature=torch.zeros((),requires_grad=True); optimizer=torch.optim.LBFGS([log_temperature],max_iter=steps)
    def closure():
        optimizer.zero_grad(); temperature=log_temperature.exp().clamp(0.05,20)
        loss=torch.nn.functional.cross_entropy(logits[active]/temperature,labels[active]); loss.backward(); return loss
    if active.any(): optimizer.step(closure)
    return float(log_temperature.exp().detach().clamp(0.05,20))
