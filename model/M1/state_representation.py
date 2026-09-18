"""M1 state-representation ownership (Phase 2).

M1 owns ``E_{<=t} -> S_hat_{i,t}``. The temporal dimension (CURRENT/HISTORY) and
the uncertainty dimension (POINT/MARGINAL/JOINT) are separate; Delay is never a
state representation.

All three uncertainty representations derive from one frozen HISTORY joint
source (``HISTORY_H16_PRIMARY`` primary, ``HISTORY_H8`` lower-capacity
sensitivity):

- Joint    : aligned scenarios + weights, unchanged.
- Point    : the frozen weighted joint medoid (one coherent scenario), never a
             combination of independent coordinate means/medians.
- Marginal : weighted coordinate marginals emitted as a deterministic
             ascending-value permutation per coordinate. The joint scenario
             alignment is destroyed by construction. This is **not** a claim of
             physical independence and must never be labelled as such.

Realized milestones replace uncertainty: a fully realized node collapses to one
weight-1.0 POINT scenario (enforced by the shared contracts).
"""

from __future__ import annotations

from typing import Iterable

from model.common.decision_contracts import (
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
    WEIGHT_TOLERANCE,
)
from model.common.errors import ContractError


__all__ = [
    "COORDINATE_ORDER",
    "MARGINAL_IDENTITY_NOTE",
    "build_joint_representation",
    "build_marginal_representation",
    "build_point_representation",
    "canonical_slot_order",
]


COORDINATE_ORDER: tuple[str, ...] = ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes")

#: Machine-readable reminder for artifacts and reports.
MARGINAL_IDENTITY_NOTE = (
    "DETERMINISTIC_COORDINATE_PERMUTATION_NOT_PHYSICAL_INDEPENDENCE"
)


def _require_history_joint(source: StateScenarioSet) -> None:
    if source.representation.temporal is not TemporalKind.HISTORY:
        raise ContractError("M1_REPRESENTATION_SOURCE_NOT_HISTORY")
    if source.representation.uncertainty is not UncertaintyKind.JOINT:
        raise ContractError("M1_REPRESENTATION_SOURCE_NOT_JOINT")


def _with_uncertainty(
    spec: StateRepresentationSpec, uncertainty: UncertaintyKind
) -> StateRepresentationSpec:
    return StateRepresentationSpec(
        temporal=spec.temporal,
        uncertainty=uncertainty,
        history_capacity=spec.history_capacity,
        history_scope=spec.history_scope,
    )


def _require_coordinates(source: StateScenarioSet) -> None:
    for scenario in source.scenarios:
        for name in COORDINATE_ORDER:
            if getattr(scenario, name) is None:
                raise ContractError(
                    "M1_SCENARIO_COORDINATE_MISSING:"
                    f"{scenario.scenario_id}:{name}"
                )


def _resolved(scenario: StateScenario) -> tuple[float, float, float]:
    return (
        float(scenario.t_ib_minutes),
        float(scenario.d_ob_minutes),
        float(scenario.d_tx_minutes),
    )


def canonical_slot_order(source: StateScenarioSet) -> tuple[StateScenario, ...]:
    """Deterministic slot order: decreasing weight, then increasing scenario id."""

    return tuple(
        sorted(
            source.scenarios,
            key=lambda item: (-item.scenario_weight, item.scenario_id),
        )
    )


def build_joint_representation(source: StateScenarioSet) -> StateScenarioSet:
    """Return the aligned joint representation unchanged."""

    _require_history_joint(source)
    return source


def build_point_representation(source: StateScenarioSet) -> StateScenarioSet:
    """Collapse the frozen weighted joint to its coherent medoid scenario.

    The medoid minimises the weight-weighted L1 distance to the joint cloud, so
    the retained scenario is a real joint draw: coherent in ``(T_IB, D_OB, D_TX)``
    and satisfying ``D_TO = D_OB + D_TX``. Coordinate-wise means/medians are not
    used, and the returned scenario keeps its own milestone-observation flags.
    """

    _require_history_joint(source)
    _require_coordinates(source)
    scenarios = tuple(source.scenarios)
    totals: list[float] = []
    for candidate in scenarios:
        point = _resolved(candidate)
        distance = 0.0
        for other in scenarios:
            distance += other.scenario_weight * sum(
                abs(a - b) for a, b in zip(point, _resolved(other))
            )
        totals.append(distance)
    best_index = min(
        range(len(scenarios)),
        key=lambda index: (totals[index], scenarios[index].scenario_id),
    )
    chosen = scenarios[best_index]
    medoid = StateScenario(
        scenario_id=chosen.scenario_id,
        scenario_weight=1.0,
        stage=chosen.stage,
        t_ib_minutes=chosen.t_ib_minutes,
        d_ob_minutes=chosen.d_ob_minutes,
        d_tx_minutes=chosen.d_tx_minutes,
        d_to_minutes=chosen.d_to_minutes,
        tx_reference_minutes=chosen.tx_reference_minutes,
        support=chosen.support,
        ib_observed=chosen.ib_observed,
        ob_observed=chosen.ob_observed,
    )
    return StateScenarioSet(
        episode_id=source.episode_id,
        chain_id=source.chain_id,
        node_id=source.node_id,
        stage=source.stage,
        representation=_with_uncertainty(source.representation, UncertaintyKind.POINT),
        scenarios=(medoid,),
    )


def build_marginal_representation(
    source: StateScenarioSet,
    *,
    coordinate_order: Iterable[str] = COORDINATE_ORDER,
) -> StateScenarioSet:
    """Emit weighted coordinate marginals as a deterministic permutation.

    Slot order is canonical (decreasing weight, then scenario id). For every
    coordinate the values are re-emitted in ascending order into the canonical
    slots, so the coordinate value multiset and the slot weight vector are both
    preserved exactly. With equal scenario weights the weighted marginal is
    therefore preserved exactly as well; with unequal weights the weight vector
    and the coordinate support are preserved while the order-statistic pairing
    follows the canonical slots, which is recorded rather than hidden.

    The joint alignment is destroyed by construction. The result is *not* a
    claim of physical independence.
    """

    _require_history_joint(source)
    _require_coordinates(source)
    order = tuple(coordinate_order)
    unknown = set(order) - set(COORDINATE_ORDER)
    if unknown:
        raise ContractError(
            "M1_MARGINAL_UNKNOWN_COORDINATE:" + ",".join(sorted(unknown))
        )
    if set(order) != set(COORDINATE_ORDER):
        missing = set(COORDINATE_ORDER) - set(order)
        raise ContractError(
            "M1_MARGINAL_COORDINATE_ORDER_INCOMPLETE:" + ",".join(sorted(missing))
        )
    slots = canonical_slot_order(source)
    permuted: list[StateScenario] = []
    columns: list[dict[str, float]] = [{} for _ in slots]
    for coordinate in order:
        values = [float(getattr(slot, coordinate)) for slot in slots]
        ranked = sorted(range(len(values)), key=lambda index: (values[index], index))
        for index in range(len(values)):
            columns[index][coordinate] = values[ranked[index]]
    for index, slot in enumerate(slots):
        values = columns[index]
        permuted.append(
            StateScenario(
                scenario_id=slot.scenario_id,
                scenario_weight=slot.scenario_weight,
                stage=slot.stage,
                t_ib_minutes=values["t_ib_minutes"],
                d_ob_minutes=values["d_ob_minutes"],
                d_tx_minutes=values["d_tx_minutes"],
                d_to_minutes=values["d_ob_minutes"] + values["d_tx_minutes"],
                tx_reference_minutes=slot.tx_reference_minutes,
                support=slot.support,
                ib_observed=slot.ib_observed,
                ob_observed=slot.ob_observed,
            )
        )
    return StateScenarioSet(
        episode_id=source.episode_id,
        chain_id=source.chain_id,
        node_id=source.node_id,
        stage=source.stage,
        representation=_with_uncertainty(
            source.representation, UncertaintyKind.MARGINAL
        ),
        scenarios=tuple(permuted),
    )
