import torch
from torch import nn
from .contracts import TargetBinContract


class OrderedEventGRU(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, bins: dict[str, TargetBinContract]):
        super().__init__(); self.input_size=input_size; self.hidden_size=hidden_size; self.bins=bins
        self.gru = nn.GRU(input_size, hidden_size, num_layers=1, batch_first=True, bidirectional=False)
        self.ib_head = nn.Linear(hidden_size, bins["R_IB"].class_count)
        self.ib_embedding = nn.Embedding(bins["R_IB"].class_count, hidden_size)
        self.ob_head = nn.Linear(hidden_size * 2, bins["R_OB"].class_count)
        self.ob_embedding = nn.Embedding(bins["R_OB"].class_count, hidden_size)
        self.tx_head = nn.Linear(hidden_size * 3, bins["T_TX"].class_count)

    def _condition(self, logits, embedding, target, active=None):
        marginal=torch.softmax(logits,-1) @ embedding.weight
        if target is None:return marginal
        teacher=embedding(target)
        if active is None:return teacher
        return torch.where(active[:,None],teacher,marginal)

    def encode_history(self, values: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        packed = nn.utils.rnn.pack_padded_sequence(values, lengths.cpu(), batch_first=True, enforce_sorted=False)
        _, hidden = self.gru(packed)
        return hidden[-1]

    def conditioned_logits(self, history: torch.Tensor, target: str,
                           ib_index: int | torch.Tensor | None = None,
                           ob_index: int | torch.Tensor | None = None) -> torch.Tensor:
        """Evaluate one categorical head under explicit sampled/observed parents."""
        if target == "R_IB":
            return self.ib_head(history)
        if ib_index is None:
            raise ValueError("R_OB/T_TX require an IB parent category")
        ib = torch.as_tensor(ib_index, dtype=torch.long, device=history.device).reshape(-1)
        if ib.numel() == 1 and history.shape[0] > 1:
            ib = ib.expand(history.shape[0])
        ibc = self.ib_embedding(ib)
        if target == "R_OB":
            return self.ob_head(torch.cat([history, ibc], -1))
        if target != "T_TX":
            raise ValueError("unknown ordered target")
        if ob_index is None:
            # R_OB may be object-specifically unsupported. Its support mask is
            # encoded in history; a zero parent embedding is not a proxy value.
            obc = torch.zeros_like(ibc)
        else:
            ob = torch.as_tensor(ob_index, dtype=torch.long, device=history.device).reshape(-1)
            if ob.numel() == 1 and history.shape[0] > 1:
                ob = ob.expand(history.shape[0])
            obc = self.ob_embedding(ob)
        return self.tx_head(torch.cat([history, ibc, obc], -1))

    def forward(self, values: torch.Tensor, lengths: torch.Tensor, teacher: dict[str, torch.Tensor] | None = None):
        h = self.encode_history(values, lengths)
        active={} if teacher is None else teacher.get("_active",{})
        ib = self.ib_head(h); ibc = self._condition(ib,self.ib_embedding,None if teacher is None else teacher.get("R_IB"),active.get("R_IB"))
        ob = self.ob_head(torch.cat([h, ibc], -1)); obc = self._condition(ob,self.ob_embedding,None if teacher is None else teacher.get("R_OB"),active.get("R_OB"))
        tx = self.tx_head(torch.cat([h, ibc, obc], -1))
        return {"R_IB":ib, "R_OB":ob, "T_TX":tx}
