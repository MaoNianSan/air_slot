"""Exact weighted marginal coupling for M1 sensitivity experiments.

The historical ``build_marginal_representation`` function is retained for
sealed compatibility.  It reorders values into a fixed slot container and
therefore cannot preserve weighted coordinate marginals when slot weights are
unequal.  This module provides a separate, typed representation for analyses
that require exact weighted marginal preservation.

The product coupling is a representation rule.  It preserves each primitive
weighted marginal but does not assert physical independence or feasibility of
the resulting joint states.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite
from typing import Iterator

from model.common.decision_contracts import (
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
    WEIGHT_TOLERANCE,
)
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError

from .state_representation import COORDINATE_ORDER


EXACT_PRODUCT_IDENTITY_NOTE = (
    "EXACT_DISCRETE_PRODUCT_COUPLING_PRESERVES_WEIGHTED_PRIMITIVE_MARGINALS_"
    "NOT_PHYSICAL_INDEPENDENCE"
)


@dataclass(frozen=True)
class WeightedAtom:
    """One value and its aggregated probability mass in a primitive marginal."""

    value: float
    mass: float


def _aggregate(values: list[tuple[float, float]]) -> tuple[WeightedAtom, ...]:
    masses: dict[float, float] = {}
    for value, mass in values:
        if not isfinite(value) or not isfinite(mass) or mass <= 0.0:
            raise ContractError("M1_MARGINAL_NONFINITE_OR_NONPOSITIVE_ATOM")
        masses[value] = masses.get(value, 0.0) + mass
    atoms = tuple(WeightedAtom(value=value, mass=masses[value]) for value in sorted(masses))
    total = sum(atom.mass for atom in atoms)
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise ContractError("M1_MARGINAL_WEIGHT_SUM_VIOLATION")
    return atoms


@dataclass(frozen=True)
class ExactWeightedMarginalDistribution:
    """Lazy exact product coupling of the three weighted primitive marginals."""

    episode_id: str
    chain_id: str
    node_id: str
    stage: OperationalStage
    representation: StateRepresentationSpec
    atoms: tuple[tuple[WeightedAtom, ...], ...]
    identity_note: str = EXACT_PRODUCT_IDENTITY_NOTE

    def __post_init__(self) -> None:
        if len(self.atoms) != len(COORDINATE_ORDER):
            raise ContractError("M1_MARGINAL_COORDINATE_COUNT_VIOLATION")
        if self.representation.temporal is not TemporalKind.HISTORY:
            raise ContractError("M1_MARGINAL_SOURCE_NOT_HISTORY")
        if self.representation.uncertainty is not UncertaintyKind.MARGINAL:
            raise ContractError("M1_MARGINAL_ADAPTER_REQUIRES_MARGINAL_SPEC")
        if any(not marginal for marginal in self.atoms):
            raise ContractError("M1_MARGINAL_EMPTY_COORDINATE_SUPPORT")

    @classmethod
    def from_source(cls, source: StateScenarioSet) -> "ExactWeightedMarginalDistribution":
        if source.representation.temporal is not TemporalKind.HISTORY:
            raise ContractError("M1_REPRESENTATION_SOURCE_NOT_HISTORY")
        if source.representation.uncertainty is not UncertaintyKind.JOINT:
            raise ContractError("M1_REPRESENTATION_SOURCE_NOT_JOINT")
        coordinate_values: list[list[tuple[float, float]]] = [
            [] for _ in COORDINATE_ORDER
        ]
        for scenario in source.scenarios:
            for index, coordinate in enumerate(COORDINATE_ORDER):
                value = getattr(scenario, coordinate)
                if value is None:
                    raise ContractError(
                        f"M1_SCENARIO_COORDINATE_MISSING:{scenario.scenario_id}:{coordinate}"
                    )
                coordinate_values[index].append((float(value), scenario.scenario_weight))
        spec = StateRepresentationSpec(
            temporal=source.representation.temporal,
            uncertainty=UncertaintyKind.MARGINAL,
            history_capacity=source.representation.history_capacity,
            history_scope=source.representation.history_scope,
        )
        return cls(
            episode_id=source.episode_id,
            chain_id=source.chain_id,
            node_id=source.node_id,
            stage=source.stage,
            representation=spec,
            atoms=tuple(_aggregate(values) for values in coordinate_values),
        )

    @property
    def scenario_count(self) -> int:
        """Number of product states without materializing them."""

        count = 1
        for marginal in self.atoms:
            count *= len(marginal)
        return count

    def weighted_atoms(self, coordinate: str) -> tuple[WeightedAtom, ...]:
        """Return one exact weighted marginal by coordinate name."""

        try:
            index = COORDINATE_ORDER.index(coordinate)
        except ValueError as exc:
            raise ContractError(f"M1_MARGINAL_UNKNOWN_COORDINATE:{coordinate}") from exc
        return self.atoms[index]

    def iter_scenarios(self) -> Iterator[StateScenario]:
        """Lazily enumerate product states with exact product weights."""

        support = SupportState.SUPPORTED
        for index, values in enumerate(product(*self.atoms)):
            t_ib, d_ob, d_tx = (atom.value for atom in values)
            weight = 1.0
            for atom in values:
                weight *= atom.mass
            yield StateScenario(
                scenario_id=index,
                scenario_weight=weight,
                stage=self.stage,
                t_ib_minutes=t_ib,
                d_ob_minutes=d_ob,
                d_tx_minutes=d_tx,
                d_to_minutes=d_ob + d_tx,
                support=support,
            )

    def materialize(self, *, max_scenarios: int | None = None) -> StateScenarioSet:
        """Materialize the coupling when a downstream contract requires scenarios."""

        if max_scenarios is not None and self.scenario_count > max_scenarios:
            raise ContractError("M1_MARGINAL_MATERIALIZATION_LIMIT_EXCEEDED")
        return StateScenarioSet(
            episode_id=self.episode_id,
            chain_id=self.chain_id,
            node_id=self.node_id,
            stage=self.stage,
            representation=self.representation,
            scenarios=tuple(self.iter_scenarios()),
        )


__all__ = [
    "EXACT_PRODUCT_IDENTITY_NOTE",
    "ExactWeightedMarginalDistribution",
    "WeightedAtom",
]
