"""Train-empirical continuation for the positive hurdle tail.

The continuation is deliberately separate from the frozen neural checkpoint.
It supplies only the scalar realization for ``u_positive > q_max``; the
neural quantile grid, hurdle temperatures, support bins, and model weights
remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from model.common.errors import ContractError
from model.common.identity import content_id


TAIL_METHOD = "TRAIN_EMPIRICAL_EXCEEDANCE_CONTINUATION"
MINIMUM_TAIL_OBSERVATIONS = 30


@dataclass(frozen=True)
class EmpiricalTailContinuation:
    target: str
    fit_partition: str
    fit_start: str
    fit_end: str
    positive_n: int
    tail_n: int
    train_positive_q90: float
    quantile_levels: tuple[float, ...]
    excess_values: tuple[float, ...]
    source_hashes: Mapping[str, str]
    artifact_id: str
    artifact_hash: str
    method: str = TAIL_METHOD
    parametric_tail: bool = False
    continuous_parametric_extrapolation: bool = False

    def __post_init__(self) -> None:
        if self.method != TAIL_METHOD:
            raise ValueError(f"M1_TAIL_METHOD_INVALID:{self.method}")
        if self.fit_partition != "train":
            raise ValueError("M1_TAIL_FIT_PARTITION_INVALID")
        if self.positive_n <= 0 or self.tail_n < MINIMUM_TAIL_OBSERVATIONS:
            raise ContractError("TAIL_CONTINUATION_INSUFFICIENT_TRAIN_SUPPORT")
        if len(self.quantile_levels) != len(self.excess_values):
            raise ValueError("M1_TAIL_KNOT_WIDTH_MISMATCH")
        if not self.quantile_levels or self.quantile_levels[0] != 0.0:
            raise ValueError("M1_TAIL_ANCHOR_REQUIRED")
        if abs(self.quantile_levels[-1] - 1.0) > 1e-12:
            raise ValueError("M1_TAIL_ENDPOINT_REQUIRED")
        if any(right <= left for left, right in zip(self.quantile_levels, self.quantile_levels[1:])):
            raise ValueError("M1_TAIL_KNOT_LEVELS_NOT_INCREASING")
        if any(value < 0 for value in self.excess_values):
            raise ValueError("M1_TAIL_EXCESS_NEGATIVE")
        if any(right < left for left, right in zip(self.excess_values, self.excess_values[1:])):
            raise ValueError("M1_TAIL_EXCESS_NOT_MONOTONE")
        if abs(self.excess_values[0]) > 1e-12:
            raise ValueError("M1_TAIL_ZERO_ANCHOR_INVALID")
        if not np.isfinite(self.train_positive_q90):
            raise ValueError("M1_TAIL_Q90_NOT_FINITE")

    @property
    def tail_continuation_id(self) -> str:
        return self.artifact_id

    @property
    def tail_reference_hash(self) -> str:
        return self.artifact_hash

    @property
    def max_excess(self) -> float:
        return float(self.excess_values[-1])

    @classmethod
    def from_exceedances(
        cls,
        *,
        target: str,
        positive_values: np.ndarray,
        fit_start: str,
        fit_end: str,
        source_hashes: Mapping[str, str],
        fit_partition: str = "train",
    ) -> "EmpiricalTailContinuation":
        values = np.asarray(positive_values, dtype=float).reshape(-1)
        values = values[np.isfinite(values) & (values > 0)]
        if values.size == 0:
            raise ContractError("TAIL_CONTINUATION_INSUFFICIENT_TRAIN_SUPPORT")
        q90 = float(np.quantile(values, 0.90, method="linear"))
        exceedances = np.sort(values[values > q90] - q90)
        if exceedances.size < MINIMUM_TAIL_OBSERVATIONS:
            raise ContractError("TAIL_CONTINUATION_INSUFFICIENT_TRAIN_SUPPORT")
        levels = np.concatenate(([0.0], np.arange(1, exceedances.size + 1, dtype=float) / exceedances.size))
        knots = np.concatenate(([0.0], exceedances))
        base = {
            "target": target,
            "fit_partition": fit_partition,
            "fit_start": fit_start,
            "fit_end": fit_end,
            "positive_n": int(values.size),
            "tail_n": int(exceedances.size),
            "train_positive_q90": q90,
            "quantile_levels": levels.tolist(),
            "excess_values": knots.tolist(),
            "source_hashes": dict(sorted(source_hashes.items())),
            "method": TAIL_METHOD,
            "parametric_tail": False,
            "continuous_parametric_extrapolation": False,
        }
        artifact_id = f"M1_{target}_TRAIN_EMPIRICAL_TAIL_V1"
        artifact_hash = content_id(base)
        return cls(
            target=target,
            fit_partition=fit_partition,
            fit_start=fit_start,
            fit_end=fit_end,
            positive_n=int(values.size),
            tail_n=int(exceedances.size),
            train_positive_q90=q90,
            quantile_levels=tuple(float(x) for x in levels),
            excess_values=tuple(float(x) for x in knots),
            source_hashes=dict(source_hashes),
            artifact_id=artifact_id,
            artifact_hash=artifact_hash,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EmpiricalTailContinuation":
        fields = dict(payload)
        fields.setdefault("method", TAIL_METHOD)
        fields.setdefault("parametric_tail", False)
        fields.setdefault("continuous_parametric_extrapolation", False)
        return cls(
            target=str(fields["target"]),
            fit_partition=str(fields["fit_partition"]),
            fit_start=str(fields["fit_start"]),
            fit_end=str(fields["fit_end"]),
            positive_n=int(fields["positive_n"]),
            tail_n=int(fields["tail_n"]),
            train_positive_q90=float(fields["train_positive_q90"]),
            quantile_levels=tuple(float(x) for x in fields["quantile_levels"]),
            excess_values=tuple(float(x) for x in fields["excess_values"]),
            source_hashes=dict(fields.get("source_hashes", {})),
            artifact_id=str(fields.get("artifact_id", f"M1_{fields['target']}_TRAIN_EMPIRICAL_TAIL_V1")),
            artifact_hash=str(fields["artifact_hash"]),
            method=str(fields.get("method", TAIL_METHOD)),
            parametric_tail=bool(fields.get("parametric_tail", False)),
            continuous_parametric_extrapolation=bool(fields.get("continuous_parametric_extrapolation", False)),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "M1_EMPIRICAL_POSITIVE_TAIL_CONTINUATION_TARGET_V1",
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "target": self.target,
            "fit_partition": self.fit_partition,
            "fit_start": self.fit_start,
            "fit_end": self.fit_end,
            "positive_n": self.positive_n,
            "tail_n": self.tail_n,
            "train_positive_q90": self.train_positive_q90,
            "min_excess": self.excess_values[1],
            "median_excess": float(np.median(self.excess_values[1:])),
            "max_excess": self.excess_values[-1],
            "quantile_levels": list(self.quantile_levels),
            "excess_values": list(self.excess_values),
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "method": self.method,
            "evidence_class": "EMPIRICAL_TRAIN_REFERENCE",
            "parametric_tail": self.parametric_tail,
            "continuous_parametric_extrapolation": self.continuous_parametric_extrapolation,
        }

    def excess_at(self, v: float) -> float:
        value = float(v)
        if not np.isfinite(value) or value < 0.0 or value > 1.0:
            raise ValueError("M1_TAIL_UNIFORM_OUTSIDE_0_1")
        return float(np.interp(value, self.quantile_levels, self.excess_values))


def load_tail_continuations(path) -> dict[str, EmpiricalTailContinuation]:
    """Load target payloads from a continuation manifest or target JSON."""
    import json
    from pathlib import Path

    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if "targets" in payload:
        output = {}
        for target, target_payload in payload["targets"].items():
            output[target] = EmpiricalTailContinuation.from_payload(target_payload)
        return output
    item = EmpiricalTailContinuation.from_payload(payload)
    return {item.target: item}


__all__ = [
    "EmpiricalTailContinuation",
    "MINIMUM_TAIL_OBSERVATIONS",
    "TAIL_METHOD",
    "load_tail_continuations",
]
