"""M1 V2 training lifecycle over hazard + hurdle-quantile heads.

The V2 estimator trains the discrete-hazard predecessor head (T_IB_A00) and
the hurdle + conditional-quantile successor heads (D_OB, D_TX) with teacher
forcing that follows the formal dependency order T_IB_A00 -> D_OB -> D_TX.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import torch

from .calibration import fit_temperature
from .loss import (
    hazard_interval_nll,
    hurdle_quantile_loss,
)
from .pipeline import M1Pipeline
from .contracts import M1V2TargetLabel, M1_V2_HAZARD_COORDINATE, V2_TARGETS
from .data import static_features_from_sequence
from .semantics import M1_V2_HAZARD_COORDINATE_TARGET
from model.PRE.contracts.pre_state import TargetSupportState

# V1 support names -> V2 internal training-target names (the hazard label is
# the internal remaining-time coordinate, never the public absolute T_IB_A00).
_V1_TO_V2_TRAINING_TARGETS = {
    "R_IB": M1_V2_HAZARD_COORDINATE_TARGET,
    "DELTA_OB": "D_OB",
    "T_TX": "D_TX",
}


@dataclass(frozen=True)
class M1TrainingExample:
    """One V2 node-level training example.

    ``targets`` holds the nonnegative minute value per primitive target
    (T_IB_A00 remaining time, D_OB minutes, D_TX minutes) or None when the
    value is unavailable/unsupported; ``active`` gates the per-target loss.
    """

    episode_id: str
    episode_date: date
    values: torch.Tensor
    targets: dict[str, float | None]
    active: dict[str, bool]
    decision_node_id: str | None = None

    @classmethod
    def from_pre_support(cls, *, episode_id, episode_date, values, targets,
                         target_support: tuple[TargetSupportState, ...]):
        active = {}
        for item in target_support:
            name = _V1_TO_V2_TRAINING_TARGETS.get(item.target_name, item.target_name)
            active[name] = item.active \
                and str(item.support_state.value) != "ABSTAIN"
        return cls(episode_id=episode_id, episode_date=episode_date, values=values,
                   targets=targets, active=active)

    @classmethod
    def from_v2_target_labels(cls, *, values: torch.Tensor,
                              labels: tuple[M1V2TargetLabel, ...]):
        if {item.target_name for item in labels} != set(V2_TARGETS):
            raise ValueError("M1_TYPED_TARGET_SET_INCOMPLETE")
        episodes = {item.episode_id for item in labels}
        dates = {item.episode_date for item in labels}
        if len(episodes) != 1 or len(dates) != 1:
            raise ValueError("M1_TYPED_TARGET_IDENTITY_MISMATCH")
        node_ids = {item.decision_node_id for item in labels}
        if len(node_ids) != 1:
            raise ValueError("M1_TYPED_TARGET_NODE_IDENTITY_MISMATCH")
        targets = {}
        active = {}
        for item in labels:
            active[item.target_name] = item.active
            targets[item.target_name] = item.exact_minutes if item.active else None
        return cls(episode_id=next(iter(episodes)), episode_date=next(iter(dates)),
                   values=values, targets=targets, active=active,
                   decision_node_id=next(iter(node_ids)))


def chronological_split(examples):
    boundaries = (("train", date(2019, 6, 30)), ("calibration", date(2019, 7, 31)),
                  ("development", date(2019, 9, 30)), ("test", date.max))
    output = {name: [] for name, _ in boundaries}
    membership = {}
    for example in sorted(examples, key=lambda row: (row.episode_date, row.episode_id)):
        split = next(name for name, end in boundaries if example.episode_date <= end)
        previous = membership.setdefault(example.episode_id, split)
        if previous != split:
            raise ValueError("episode crosses chronological split")
        output[split].append(example)
    return output


class M1Lifecycle:
    def __init__(self, pipeline, *, device="cpu"):
        self.pipeline = pipeline
        self.device = self._resolve_device(device)
        self.pipeline.model.to(self.device)

    @staticmethod
    def _resolve_device(device):
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        resolved = torch.device(device)
        if resolved.type == "cuda" and not torch.cuda.is_available():
            raise ValueError("M1_CUDA_REQUESTED_BUT_UNAVAILABLE")
        if resolved.type not in {"cpu", "cuda"}:
            raise ValueError(f"M1_DEVICE_UNSUPPORTED:{resolved.type}")
        return resolved

    @staticmethod
    def _encode(values, contracts, device):
        """V2 label encodings for teacher forcing and losses."""
        hazard = contracts[M1_V2_HAZARD_COORDINATE]
        d_ob = contracts["D_OB"]
        d_tx = contracts["D_TX"]
        ib_bin = torch.full((len(values),), -1, dtype=torch.long, device=device)
        d_ob_bin = torch.full((len(values),), -1, dtype=torch.long, device=device)
        d_tx_bin = torch.full((len(values),), -1, dtype=torch.long, device=device)
        ib_minutes = torch.full((len(values),), float("nan"), dtype=torch.float32, device=device)
        d_ob_minutes = torch.full((len(values),), float("nan"), dtype=torch.float32, device=device)
        d_tx_minutes = torch.full((len(values),), float("nan"), dtype=torch.float32, device=device)
        d_ob_zero = torch.zeros(len(values), dtype=torch.bool, device=device)
        d_tx_zero = torch.zeros(len(values), dtype=torch.bool, device=device)
        active = {name: torch.zeros(len(values), dtype=torch.bool, device=device)
                  for name in V2_TARGETS}
        for index, row in enumerate(values):
            for name in V2_TARGETS:
                active[name][index] = row.active.get(name, False)
            if row.targets.get(M1_V2_HAZARD_COORDINATE) is not None:
                minutes = max(0.0, float(row.targets[M1_V2_HAZARD_COORDINATE]))
                ib_minutes[index] = minutes
                ib_bin[index] = hazard.encode(minutes)
            if row.targets.get("D_OB") is not None:
                minutes = float(row.targets["D_OB"])
                d_ob_minutes[index] = minutes
                d_ob_zero[index] = minutes == 0.0
                d_ob_bin[index] = d_ob.encode(minutes)
            if row.targets.get("D_TX") is not None:
                minutes = float(row.targets["D_TX"])
                d_tx_minutes[index] = minutes
                d_tx_zero[index] = minutes == 0.0
                d_tx_bin[index] = d_tx.encode(minutes)
        return {
            "ib_bin": ib_bin, "d_ob_bin": d_ob_bin, "d_tx_bin": d_tx_bin,
            "ib_minutes": ib_minutes, "d_ob_minutes": d_ob_minutes,
            "d_tx_minutes": d_tx_minutes, "d_ob_zero": d_ob_zero,
            "d_tx_zero": d_tx_zero, "active": active,
        }

    @staticmethod
    def _batch(examples, contracts, *, device=None):
        target = torch.device("cpu") if device is None else torch.device(device)
        lengths = torch.tensor([row.values.shape[0] for row in examples], dtype=torch.long)
        values = torch.nn.utils.rnn.pad_sequence(
            [row.values for row in examples], batch_first=True).to(target)
        encoded = M1Lifecycle._encode(examples, contracts, target)
        return values, lengths, encoded

    @staticmethod
    def _batch_indices(examples, batch_size, *, bucketed):
        if batch_size is None:
            return (tuple(range(len(examples))),)
        if batch_size <= 0:
            raise ValueError("M1_BATCH_SIZE_MUST_BE_POSITIVE")
        order = list(range(len(examples)))
        if bucketed:
            order.sort(key=lambda index: (examples[index].values.shape[0], index))
        return tuple(tuple(order[start:start + batch_size])
                     for start in range(0, len(order), batch_size))

    @classmethod
    def batching_diagnostics(cls, examples, *, batch_size, bucketed=True):
        batches = cls._batch_indices(examples, batch_size, bucketed=bucketed)
        actual = sum(int(examples[index].values.shape[0])
                     for batch in batches for index in batch)
        padded = sum(max(int(examples[index].values.shape[0])
                         for index in batch) * len(batch)
                     for batch in batches if batch)
        return {"batches": len(batches), "padded_rows": padded,
                "actual_rows": actual,
                "padding_fraction": 0.0 if padded == 0 else 1.0 - actual / padded}

    @staticmethod
    def _global_loss_counts(examples):
        """Global active counts used to normalize loss terms across batches."""
        ib_count = 0
        ob_zero_count = 0
        ob_positive_count = 0
        tx_zero_count = 0
        tx_positive_count = 0
        for row in examples:
            if row.active.get(M1_V2_HAZARD_COORDINATE):
                ib_count += 1
            if row.active.get("D_OB"):
                ob_zero_count += 1
                if row.targets.get("D_OB") is not None and float(row.targets["D_OB"]) > 0:
                    ob_positive_count += 1
            if row.active.get("D_TX"):
                tx_zero_count += 1
                if row.targets.get("D_TX") is not None and float(row.targets["D_TX"]) > 0:
                    tx_positive_count += 1
        return {
            "ib": ib_count,
            "ob_zero": ob_zero_count,
            "ob_positive": ob_positive_count,
            "tx_zero": tx_zero_count,
            "tx_positive": tx_positive_count,
        }

    def _loss(self, logits, encoded, contracts, counts):
        """Batch-split invariant loss share of the global epoch loss.

        Every term is a sum over the batch's active rows divided by the
        corresponding global active count, so micro-batching reproduces the
        full-batch loss and gradient exactly.
        """
        active = encoded["active"]
        ib_loss = hazard_interval_nll(
            logits[M1_V2_HAZARD_COORDINATE], contracts[M1_V2_HAZARD_COORDINATE],
            lower=encoded["ib_minutes"], upper=encoded["ib_minutes"],
            active=active[M1_V2_HAZARD_COORDINATE], denominator=counts["ib"],
        )
        d_ob_loss = hurdle_quantile_loss(
            logits["D_OB_zero"], logits["D_OB_quantile"], contracts["D_OB"],
            zero=encoded["d_ob_zero"], value=encoded["d_ob_minutes"],
            active=active["D_OB"], zero_denominator=counts["ob_zero"],
            positive_denominator=counts["ob_positive"],
        )
        d_tx_loss = hurdle_quantile_loss(
            logits["D_TX_zero"], logits["D_TX_quantile"], contracts["D_TX"],
            zero=encoded["d_tx_zero"], value=encoded["d_tx_minutes"],
            active=active["D_TX"], zero_denominator=counts["tx_zero"],
            positive_denominator=counts["tx_positive"],
        )
        return ib_loss + d_ob_loss + d_tx_loss

    def train(self, examples, *, epochs, learning_rate, batch_size=None,
              bucketed=True, seed=None, teacher_forcing=True):
        if not examples:
            raise ValueError("empty training split")
        if seed is not None:
            torch.manual_seed(seed)
        optimizer = torch.optim.Adam(self.pipeline.model.parameters(), lr=learning_rate)
        history = []
        for epoch in range(epochs):
            batches = self._batch_indices(examples, batch_size, bucketed=bucketed)
            counts = M1Lifecycle._global_loss_counts(examples)
            # Gradients accumulate across microbatches; the optimizer steps
            # once per epoch so microbatch and full-batch training agree.
            optimizer.zero_grad()
            total = torch.zeros((), dtype=torch.float32)
            for indices in batches:
                batch = [examples[index] for index in indices]
                values, lengths, encoded = self._batch(batch, self.pipeline.contracts,
                                                       device=self.device)
                teacher = None
                if teacher_forcing:
                    teacher = {
                        M1_V2_HAZARD_COORDINATE: encoded["ib_bin"],
                        "D_OB": encoded["d_ob_bin"],
                        "D_TX": encoded["d_tx_bin"],
                        "_active": {
                            M1_V2_HAZARD_COORDINATE: encoded["ib_bin"] >= 0,
                            "D_OB": encoded["d_ob_bin"] >= 0,
                            "D_TX": encoded["d_tx_bin"] >= 0,
                        },
                    }
                logits = self.pipeline.model(
                    values, lengths, teacher=teacher,
                    static_features=static_features_from_sequence(values, lengths))
                loss = self._loss(logits, encoded, self.pipeline.contracts, counts)
                total = total + loss.detach()
                loss.backward()
            optimizer.step()
            history.append({
                "epoch": epoch + 1,
                "loss": float(total.item()),
                "optimizer_steps": 1,
                "microbatch_count": len(batches),
                "active_counts": {
                    name: sum(int(row.active.get(name, False)) for row in examples)
                    for name in V2_TARGETS
                },
            })
        return history


    def batched_logits(self, examples, *, batch_size=None, bucketed=True,
                       teacher_forcing=True):
        output = None
        all_labels = {name: torch.empty(len(examples), dtype=torch.long) for name in V2_TARGETS}
        all_active = {name: torch.empty(len(examples), dtype=torch.bool) for name in V2_TARGETS}
        self.pipeline.model.eval()
        with torch.no_grad():
            for indices in self._batch_indices(examples, batch_size, bucketed=bucketed):
                batch = [examples[index] for index in indices]
                values, lengths, encoded = self._batch(batch, self.pipeline.contracts,
                                                       device=self.device)
                teacher = None if not teacher_forcing else {
                    M1_V2_HAZARD_COORDINATE: encoded["ib_bin"],
                    "D_OB": encoded["d_ob_bin"],
                    "D_TX": encoded["d_tx_bin"],
                    "_active": {
                        M1_V2_HAZARD_COORDINATE: encoded["ib_bin"] >= 0,
                        "D_OB": encoded["d_ob_bin"] >= 0,
                        "D_TX": encoded["d_tx_bin"] >= 0,
                    },
                }
                logits = self.pipeline.model(
                    values, lengths, teacher=teacher,
                    static_features=static_features_from_sequence(values, lengths))
                target_indices = torch.tensor(indices, dtype=torch.long)
                if output is None:
                    output = {name: torch.empty(
                        (len(examples), logits[name].shape[1]),
                        dtype=logits[name].dtype) for name in logits}
                for name, value in logits.items():
                    value = value.detach().cpu()
                    output[name][target_indices] = value
                label_map = {M1_V2_HAZARD_COORDINATE: "ib_bin",
                             "D_OB": "d_ob_bin", "D_TX": "d_tx_bin"}
                for name in V2_TARGETS:
                    all_labels[name][target_indices] = encoded[label_map[name]].detach().cpu()
                    all_active[name][target_indices] = encoded["active"][name].detach().cpu()
        return output, all_labels, all_active

    def calibrate(self, examples, *, batch_size=None):
        if not examples:
            raise ValueError("empty calibration split")
        # V2 temperature calibration applies to the discrete-hazard head only;
        # hurdle-quantile heads keep temperature 1.0 (no frozen V2 selection).
        logits, labels, active = self.batched_logits(
            examples, batch_size=batch_size, teacher_forcing=True)
        temperatures = {name: 1.0 for name in V2_TARGETS}
        hazard = self.pipeline.contracts[M1_V2_HAZARD_COORDINATE]
        encoded_active = active[M1_V2_HAZARD_COORDINATE]
        if encoded_active.any():
            temperatures[M1_V2_HAZARD_COORDINATE] = fit_temperature(
                logits[M1_V2_HAZARD_COORDINATE],
                labels[M1_V2_HAZARD_COORDINATE], encoded_active)
        self.pipeline.temperatures = temperatures
        return dict(self.pipeline.temperatures)

    def infer(self, values, lengths):
        return self.pipeline.predict_distributions(values, lengths)

    def sample(self, pre_state, values, lengths, **kwargs):
        return self.pipeline.sample_from_pre(pre_state, values, lengths, **kwargs)

    def save(self, path: Path):
        self.pipeline.save(path)

    @classmethod
    def load(cls, path: Path, *, device="cpu"):
        return cls(M1Pipeline.load(path), device=device)
