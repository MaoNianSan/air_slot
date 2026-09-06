"""Evaluation-only Point, Marginal, and Joint state representations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Mapping, Sequence


def _weights(weights: Sequence[float]) -> tuple[float, ...]:
    if not weights:
        raise ValueError("EXP1_EMPTY_SCENARIO_DISTRIBUTION")
    values = tuple(float(w) for w in weights)
    if any(not isfinite(w) or w <= 0 for w in values):
        raise ValueError("EXP1_SCENARIO_WEIGHTS_MUST_BE_POSITIVE_FINITE")
    total = sum(values)
    if total <= 0 or not isfinite(total):
        raise ValueError("EXP1_SCENARIO_WEIGHTS_INVALID")
    return tuple(w / total for w in values)


@dataclass(frozen=True)
class ScenarioState:
    scenario_id: int
    r_ib: float
    d_ob: float
    d_tx: float
    weight: float

    @property
    def d_to(self) -> float:
        value = self.d_ob + self.d_tx
        if value < 0 or not isfinite(value):
            raise ValueError("EXP1_D_TO_INVALID")
        return value

    @property
    def vector(self) -> tuple[float, float, float]:
        return (self.r_ib, self.d_ob, self.d_tx)


@dataclass(frozen=True)
class JointRepresentation:
    scenarios: tuple[ScenarioState, ...]

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise ValueError("EXP1_JOINT_EMPTY")
        ids = [s.scenario_id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("EXP1_DUPLICATE_SCENARIO_ID")
        weights = tuple(float(s.weight) for s in self.scenarios)
        if any(not isfinite(w) or w <= 0 for w in weights):
            raise ValueError("EXP1_JOINT_WEIGHTS_MUST_BE_POSITIVE_FINITE")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("EXP1_JOINT_WEIGHTS_NOT_NORMALIZED")

    @property
    def values(self) -> tuple[tuple[float, float, float], ...]:
        return tuple(s.vector for s in self.scenarios)

    @property
    def weights(self) -> tuple[float, ...]:
        return tuple(s.weight for s in self.scenarios)

    def marginal(self, axis: int) -> tuple[tuple[float, float], ...]:
        return tuple((v[axis], w) for v, w in zip(self.values, self.weights))


@dataclass(frozen=True)
class PointRepresentation:
    scenario: ScenarioState

    @property
    def values(self) -> tuple[tuple[float, float, float], ...]:
        return (self.scenario.vector,)

    @property
    def weights(self) -> tuple[float, ...]:
        return (1.0,)


@dataclass(frozen=True)
class MarginalRepresentation:
    marginals: tuple[tuple[tuple[float, float], ...], ...]

    def __post_init__(self) -> None:
        if len(self.marginals) != 3:
            raise ValueError("EXP1_MARGINAL_REQUIRES_3_PRIMITIVES")
        normalized = []
        for marginal in self.marginals:
            values = tuple(float(value) for value, _ in marginal)
            weights = _weights([weight for _, weight in marginal])
            normalized.append(tuple(zip(values, weights)))
        object.__setattr__(self, "marginals", tuple(normalized))

    @property
    def values(self) -> tuple[tuple[float, float, float], ...]:
        """Return Cartesian product values for callers that need explicit draws."""
        out: list[tuple[float, float, float]] = []
        for r, _ in self.marginals[0]:
            for o, _ in self.marginals[1]:
                for x, _ in self.marginals[2]:
                    out.append((r, o, x))
        return tuple(out)

    @property
    def weights(self) -> tuple[float, ...]:
        out: list[float] = []
        for _, wr in self.marginals[0]:
            for _, wo in self.marginals[1]:
                for _, wx in self.marginals[2]:
                    out.append(wr * wo * wx)
        return tuple(out)

    def marginal(self, axis: int) -> tuple[tuple[float, float], ...]:
        return self.marginals[axis]


def build_point(
    joint: JointRepresentation,
    supports: Sequence[float] | None = None,
) -> PointRepresentation:
    if supports is None:
        raise ValueError("EXP1_POINT_SUPPORTS_REQUIRED")
    if len(supports) != 3 or any(float(s) <= 0 or not isfinite(float(s)) for s in supports):
        raise ValueError("EXP1_M1_SUPPORTS_MUST_BE_POSITIVE")
    best = None
    best_distance = None
    for candidate in joint.scenarios:
        distance = sum(
            other.weight
            * sum(abs(a - b) / float(scale) for a, b, scale in zip(candidate.vector, other.vector, supports))
            for other in joint.scenarios
        )
        key = (distance, candidate.scenario_id)
        if best is None or key < (best_distance, best.scenario.scenario_id):
            best, best_distance = PointRepresentation(candidate), distance
    assert best is not None
    return best


def build_marginal(joint: JointRepresentation) -> MarginalRepresentation:
    return MarginalRepresentation(tuple(joint.marginal(axis) for axis in range(3)))


def ensure_d_to_identity(scenarios: Iterable[ScenarioState], *, tolerance: float = 1e-9) -> None:
    for scenario in scenarios:
        if abs(scenario.d_to - (scenario.d_ob + scenario.d_tx)) > tolerance:
            raise ValueError("EXP1_D_TO_IDENTITY_VIOLATION")


def from_mapping_rows(rows: Iterable[Mapping[str, float]]) -> JointRepresentation:
    """Build a Joint representation from already-materialized typed rows.

    This helper intentionally accepts rows only; it does not parse raw Data2 or
    infer factual support.
    """
    scenarios = tuple(
        ScenarioState(
            scenario_id=int(row["scenario_id"]),
            r_ib=float(row["r_ib"]),
            d_ob=float(row["d_ob"]),
            d_tx=float(row["d_tx"]),
            weight=float(row["weight"]),
        )
        for row in rows
    )
    return JointRepresentation(scenarios)
