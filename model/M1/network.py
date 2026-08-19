import torch
from torch import nn

from .contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1_V2_HAZARD_COORDINATE,
    TargetBinContract,
)
from .loss import hazard_pmf, monotone_positive_quantiles


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



class StaticContextEncoder(nn.Module):
    """Minimal projection of supported static context to the shared dimension.

    IMPLEMENTATION_CHOICE (Round 2.1): a single linear projection to the
    recurrent hidden dimension (``hidden_size``, the natural shared dimension
    used by the frozen ``m1_hidden_size=32``); no hyperparameter search.
    Unsupported manuscript static fields never reach this encoder
    (``SUPPORT_ABSTAIN``); they enter as an explicit zero block through
    ``M1V2GRU.state_representation`` so no context is fabricated.
    """

    def __init__(self, input_size: int, hidden_size: int):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.projection = nn.Linear(input_size, hidden_size)

    def forward(self, static: torch.Tensor) -> torch.Tensor:
        return self.projection(static)


class M1V2GRU(nn.Module):
    """V2 principal M1 state estimator.

    Dependency graph (network, teacher forcing and ancestral sampler all obey
    this order):

        h = GRU(full admissible causal history)
        state = concat(recurrent_repr=h, static_repr=static_encoder(static))
        T_IB_A00 ~ p(. | state)             discrete hazard over remaining time
        D_OB     ~ p(. | T_IB_A00, state)   hurdle + positive conditional quantile
        D_TX     ~ p(. | T_IB_A00, D_OB, state) hurdle + positive conditional
                                              quantile
        D_TO = D_OB + D_TX                  derived, never a separate head

    The manuscript static context (schedule / route / aircraft / turnaround
    reference / taxi reference / carrier) is retained separately and fused
    before the common heads.  Only schedule timing is currently SUPPORTED by
    Data2/PRE; all other manuscript static fields stay ``SUPPORT_ABSTAIN``
    (zero static block, no fabricated context).  The ``optional_fast_repr``
    fusion remains human-gated (``M1_FAST_FUSION_INTERPRETATION_REQUIRED``).

    Signed DELTA_OB never enters the graph: D_TX conditions on the formal D_OB
    parent only.  The hazard head emits logits over the INTERNAL remaining-time
    coordinate ``T_IB_REMAINING_HAZARD``; the public event time is
    ``T_IB_A00 = decision_time + coordinate``.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        hazard: HazardBinContract,
        d_ob: HurdleQuantileContract,
        d_tx: HurdleQuantileContract,
        *,
        static_input_size: int = 0,
    ):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.hazard_contract = hazard
        self.d_ob_contract = d_ob
        self.d_tx_contract = d_tx
        self.static_input_size = int(static_input_size)
        # state_repr = concat(recurrent_repr, static_repr): the recurrent
        # hidden block plus the projected static block (zero when unsupported).
        self.state_width = hidden_size * 2
        self.static_encoder = (
            StaticContextEncoder(self.static_input_size, hidden_size)
            if self.static_input_size > 0 else None
        )
        self.gru = nn.GRU(
            input_size, hidden_size, num_layers=1, batch_first=True, bidirectional=False
        )
        self.hazard_head = nn.Linear(self.state_width, hazard.finite_class_count)
        self.ib_embedding = nn.Embedding(hazard.class_count, hidden_size)
        self.d_ob_zero_head = nn.Linear(self.state_width + hidden_size, 1)
        self.d_ob_quantile_head = nn.Linear(self.state_width + hidden_size, d_ob.quantile_count)
        self.d_ob_embedding = nn.Embedding(d_ob.class_count, hidden_size)
        self.d_tx_zero_head = nn.Linear(self.state_width + hidden_size * 2, 1)
        self.d_tx_quantile_head = nn.Linear(self.state_width + hidden_size * 2, d_tx.quantile_count)

    def encode_history(self, values: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        packed = nn.utils.rnn.pack_padded_sequence(
            values, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        _, hidden = self.gru(packed)
        return hidden[-1]

    def state_representation(
        self,
        history: torch.Tensor,
        static_features: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Fused state fed to every common head.

        ``state = concat(recurrent_repr, static_repr)``.  Supported static
        context (schedule timing) is projected by the static encoder; when no
        static features are available the static block is an explicit zero
        representation (SUPPORT_ABSTAIN — nothing is fabricated).
        """
        if static_features is not None and self.static_encoder is None:
            raise ValueError("M1_STATIC_PROJECTION_UNAVAILABLE")
        if static_features is None or self.static_encoder is None:
            static = torch.zeros_like(history)
        else:
            static = self.static_encoder(static_features)
        return torch.cat([history, static], dim=-1)

    def _as_index(self, index, device, batch_size: int) -> torch.Tensor:
        tensor = torch.as_tensor(index, dtype=torch.long, device=device).reshape(-1)
        if tensor.numel() == 1 and batch_size > 1:
            tensor = tensor.expand(batch_size)
        return tensor

    def _ib_conditioning(
        self,
        state: torch.Tensor,
        hazard_logits: torch.Tensor,
        ib_index: int | torch.Tensor | None,
        ib_active: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Embedding of the T_IB_A00 parent; marginal mixture when unresolved."""
        if ib_index is None:
            pmf = hazard_pmf(hazard_logits, self.hazard_contract)
            return pmf @ self.ib_embedding.weight
        ib = self._as_index(ib_index, state.device, state.shape[0])
        teacher = self.ib_embedding(ib)
        if ib_active is None:
            return teacher
        pmf = hazard_pmf(hazard_logits, self.hazard_contract)
        marginal = pmf @ self.ib_embedding.weight
        return torch.where(ib_active[:, None], teacher, marginal)

    def _ob_conditioning(
        self,
        state: torch.Tensor,
        d_ob_index: int | torch.Tensor | None,
        d_ob_active: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Embedding of the formal D_OB parent; masked zero when unsupported."""
        if d_ob_index is None:
            return torch.zeros(state.shape[0], self.hidden_size, device=state.device)
        index = self._as_index(d_ob_index, state.device, state.shape[0])
        teacher = self.d_ob_embedding(index)
        if d_ob_active is None:
            return teacher
        return torch.where(
            d_ob_active[:, None], teacher,
            torch.zeros_like(teacher),
        )

    def hazard_logits(self, state: torch.Tensor) -> torch.Tensor:
        """Hazard logits over the internal remaining-time coordinate."""
        return self.hazard_head(state)

    def d_ob_heads(
        self,
        state: torch.Tensor,
        ib_index: int | torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        ibc = self.ib_embedding(self._as_index(ib_index, state.device, state.shape[0]))
        features = torch.cat([state, ibc], -1)
        return self.d_ob_zero_head(features), self.d_ob_quantile_head(features)

    def d_tx_heads(
        self,
        state: torch.Tensor,
        ib_index: int | torch.Tensor,
        d_ob_index: int | torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        ibc = self.ib_embedding(self._as_index(ib_index, state.device, state.shape[0]))
        d_obc = self.d_ob_embedding(self._as_index(d_ob_index, state.device, state.shape[0]))
        features = torch.cat([state, ibc, d_obc], -1)
        return self.d_tx_zero_head(features), self.d_tx_quantile_head(features)

    def forward(
        self,
        values: torch.Tensor,
        lengths: torch.Tensor,
        teacher: dict[str, torch.Tensor] | None = None,
        static_features: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """Teacher-forced forward pass.

        ``teacher`` may carry internal target names {"T_IB_REMAINING_HAZARD",
        "D_OB", "D_TX"} parent bin indices plus "_active" per-target
        availability masks; unavailable parents fall back to the
        marginal/masked conditioning described above.  ``static_features``
        feeds the static encoder when supported static context is available.
        """
        history = self.encode_history(values, lengths)
        state = self.state_representation(history, static_features)
        active = {} if teacher is None else teacher.get("_active", {})
        hazard = self.hazard_head(state)
        ib_index = None if teacher is None else teacher.get(M1_V2_HAZARD_COORDINATE)
        ib_active = None if teacher is None else active.get(M1_V2_HAZARD_COORDINATE)
        ibc = self._ib_conditioning(state, hazard, ib_index, ib_active)
        d_ob_zero = self.d_ob_zero_head(torch.cat([state, ibc], -1))
        d_ob_quantile = self.d_ob_quantile_head(torch.cat([state, ibc], -1))
        d_ob_index = None if teacher is None else teacher.get("D_OB")
        d_ob_active = None if teacher is None else active.get("D_OB")
        d_obc = self._ob_conditioning(state, d_ob_index, d_ob_active)
        d_tx_zero = self.d_tx_zero_head(torch.cat([state, ibc, d_obc], -1))
        d_tx_quantile = self.d_tx_quantile_head(torch.cat([state, ibc, d_obc], -1))
        return {
            M1_V2_HAZARD_COORDINATE: hazard,
            "D_OB_zero": d_ob_zero,
            "D_OB_quantile": d_ob_quantile,
            "D_TX_zero": d_tx_zero,
            "D_TX_quantile": d_tx_quantile,
        }
