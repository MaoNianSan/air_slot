import torch


def categorical_metrics(probabilities: torch.Tensor, labels: torch.Tensor) -> dict[str,float]:
    chosen=probabilities.gather(1,labels[:,None]).clamp_min(1e-12)
    return {"nll":float(-chosen.log().mean()),"accuracy":float((probabilities.argmax(1)==labels).float().mean())}
