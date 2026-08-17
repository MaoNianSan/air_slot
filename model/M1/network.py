import torch
from torch import nn

from .contracts import TargetBinContract


class OrderedEventGRU(nn.Module):
    """One-layer causal GRU with the signed ordered M1 factorization."""

    def __init__(self, input_size: int, hidden_size: int, bins: dict[str, TargetBinContract]):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.bins = bins
        self.gru = nn.GRU(input_size, hidden_size, num_layers=1, batch_first=True, bidirectional=False)
        self.ib_head = nn.Linear(hidden_size, bins["R_IB"].class_count)
        self.ib_embedding = nn.Embedding(bins["R_IB"].class_count, hidden_size)
        self.delta_ob_head = nn.Linear(hidden_size * 2, bins["DELTA_OB"].class_count)
        self.delta_ob_embedding = nn.Embedding(bins["DELTA_OB"].class_count, hidden_size)
        self.tx_head = nn.Linear(hidden_size * 3, bins["T_TX"].class_count)

    def _condition(self, logits, embedding, target, active=None):
        marginal = torch.softmax(logits, -1) @ embedding.weight
        if target is None:
            return marginal
        teacher = embedding(target)
        if active is None:
            return teacher
        return torch.where(active[:, None], teacher, marginal)

    def encode_history(self, values: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        packed = nn.utils.rnn.pack_padded_sequence(values, lengths.cpu(), batch_first=True, enforce_sorted=False)
        _, hidden = self.gru(packed)
        return hidden[-1]

    def conditioned_logits(
        self,
        history: torch.Tensor,
        target: str,
        ib_index: int | torch.Tensor | None = None,
        delta_ob_index: int | torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Evaluate one head under explicit sampled or observed signed parents."""
        if target == "R_IB":
            return self.ib_head(history)
        if ib_index is None:
            raise ValueError("DELTA_OB/T_TX require an R_IB parent category")
        ib = torch.as_tensor(ib_index, dtype=torch.long, device=history.device).reshape(-1)
        if ib.numel() == 1 and history.shape[0] > 1:
            ib = ib.expand(history.shape[0])
        ibc = self.ib_embedding(ib)
        if target == "DELTA_OB":
            return self.delta_ob_head(torch.cat([history, ibc], -1))
        if target != "T_TX":
            raise ValueError("unknown ordered target")
        if delta_ob_index is None:
            # DELTA_OB can be object-specifically unsupported; zero is not a proxy value.
            delta_obc = torch.zeros_like(ibc)
        else:
            delta_ob = torch.as_tensor(delta_ob_index, dtype=torch.long, device=history.device).reshape(-1)
            if delta_ob.numel() == 1 and history.shape[0] > 1:
                delta_ob = delta_ob.expand(history.shape[0])
            delta_obc = self.delta_ob_embedding(delta_ob)
        return self.tx_head(torch.cat([history, ibc, delta_obc], -1))

    def forward(self, values: torch.Tensor, lengths: torch.Tensor, teacher: dict[str, torch.Tensor] | None = None):
        history = self.encode_history(values, lengths)
        active = {} if teacher is None else teacher.get("_active", {})
        ib = self.ib_head(history)
        ibc = self._condition(
            ib, self.ib_embedding, None if teacher is None else teacher.get("R_IB"), active.get("R_IB")
        )
        delta_ob = self.delta_ob_head(torch.cat([history, ibc], -1))
        delta_obc = self._condition(
            delta_ob,
            self.delta_ob_embedding,
            None if teacher is None else teacher.get("DELTA_OB"),
            active.get("DELTA_OB"),
        )
        tx = self.tx_head(torch.cat([history, ibc, delta_obc], -1))
        return {"R_IB": ib, "DELTA_OB": delta_ob, "T_TX": tx}
