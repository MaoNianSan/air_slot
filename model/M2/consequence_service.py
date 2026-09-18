"""M2 public consequence service (Phase 3 callback).

This module is the **only** callback M3 uses: a post-transition
:class:`StateScenario` goes in, and the same seven native consequence formulas
plus the CU transformation come out. Action effects are therefore produced by a
state transition followed by this common consequence map, never by
action-specific percentage reductions.

Native formulas follow the manuscript section 4 definitions:

``F_continuity = max(0, T_IB - turnaround_reference)``, ``F_execution = D_OB``,
``F_propagation = D_TO * expected_downstream_exposure``,
``P_time = N_pax * D_TO``, ``P_itinerary = N_pax * s_conn * 1(D_TO > 45)``,
``P_service = N_pax * 1(D_TO >= 180)``, ``R_operating = D_TX``.

CU mapping is ``C_k^CU = q_k / c_k^CU`` with the train-frozen scales from the
active CU registry (V5: five principal positive Train medians plus two
assumption-grounded event normalizations). Monetary mapping is deliberately not
part of this service.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import Field

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.decision_contracts import (
    ConsequenceScenario,
    ConsequenceScenarioSet,
    StateScenario,
    StateScenarioSet,
)
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.native_formulas import (
    p_itinerary_native,
    p_service_native,
    p_time_native,
)
from model.common.value_objects import FrozenModel
from model.M2.cu.registry import M2Data2FormalCuRegistry


__all__ = [
    "ConsequenceReferenceBinding",
    "M2ConsequenceService",
    "native_consequence_vector",
]


class ConsequenceReferenceBinding(FrozenModel):
    """Frozen node/chain references required by the native consequence map."""

    reference_id: str = Field(min_length=1)
    turnaround_reference_minutes: float = Field(ge=0.0)
    taxi_reference_minutes: float = Field(ge=0.0)
    expected_pax: float = Field(ge=0.0)
    connection_share: float = Field(ge=0.0, le=1.0)
    downstream_exposure: float = Field(ge=0.0)
    itinerary_threshold_minutes: float = Field(default=45.0, gt=0.0)
    service_threshold_minutes: float = Field(default=180.0, gt=0.0)


def _required(value: float | None, name: str, node_id: str) -> float:
    if value is None:
        raise ContractError(f"M2_CONSEQUENCE_MISSING_STATE_QUANTITY:{node_id}:{name}")
    return float(value)


def native_consequence_vector(
    state: StateScenario, binding: ConsequenceReferenceBinding
) -> dict[str, float]:
    """Evaluate the seven native consequence quantities on one scenario state."""

    node_id = str(state.scenario_id)
    d_ob = _required(state.d_ob_minutes, "D_OB", node_id)
    d_tx = _required(state.d_tx_minutes, "D_TX", node_id)
    t_ib = _required(state.t_ib_minutes, "T_IB", node_id)
    d_to = d_ob + d_tx
    if state.d_to_minutes is not None:
        carried = float(state.d_to_minutes)
        if abs(carried - d_to) > 1e-6:
            raise ContractError(f"M2_CONSEQUENCE_D_TO_IDENTITY_VIOLATION:{node_id}")
    return {
        "F_continuity": max(0.0, t_ib - binding.turnaround_reference_minutes),
        "F_execution": d_ob,
        "F_propagation": d_to * binding.downstream_exposure,
        "P_time": p_time_native(binding.expected_pax, d_to),
        "P_itinerary": p_itinerary_native(
            binding.expected_pax,
            binding.connection_share,
            d_to,
            binding.itinerary_threshold_minutes,
        ),
        "P_service": p_service_native(
            binding.expected_pax, d_to, binding.service_threshold_minutes
        ),
        "R_operating": d_tx,
    }


class M2ConsequenceService:
    """Production ``state -> consequence`` service bound to one CU registry.

    References are keyed by decision-node id. A missing binding fails closed with
    a typed contract error instead of an implicit zero consequence.
    """

    def __init__(
        self,
        registry: M2Data2FormalCuRegistry,
        references: Mapping[str, ConsequenceReferenceBinding],
    ) -> None:
        self.registry = registry
        self.references = dict(references)
        self.registry_id = registry.registry_id
        self.registry_hash = registry.registry_hash
        self._scales = {
            component: float(registry.scale(component))
            for component in CONSEQUENCE_COMPONENTS
        }

    def binding(self, node_id: str) -> ConsequenceReferenceBinding:
        try:
            return self.references[node_id]
        except KeyError as error:
            raise ContractError(f"M2_CONSEQUENCE_REFERENCE_MISSING:{node_id}") from error

    def to_cu(self, native_components: Mapping[str, float]) -> dict[str, float]:
        """``C_k^CU = q_k / c_k^CU`` with the frozen registry scales."""

        missing = [
            component
            for component in CONSEQUENCE_COMPONENTS
            if component not in native_components
        ]
        if missing:
            raise ContractError("M2_CONSEQUENCE_NATIVE_INCOMPLETE:" + ",".join(missing))
        return {
            component: float(native_components[component]) / self._scales[component]
            for component in CONSEQUENCE_COMPONENTS
        }

    def consequence_scenario(
        self,
        state: StateScenario,
        *,
        node_id: str,
        support: SupportState = SupportState.SUPPORTED,
    ) -> ConsequenceScenario:
        binding = self.binding(node_id)
        native = native_consequence_vector(state, binding)
        return ConsequenceScenario(
            scenario_id=state.scenario_id,
            scenario_weight=state.scenario_weight,
            native_components=native,
            cu_components=self.to_cu(native),
            support=support,
        )

    def consequence_set(self, state_set: StateScenarioSet) -> ConsequenceScenarioSet:
        scenarios = tuple(
            self.consequence_scenario(
                scenario, node_id=state_set.node_id, support=scenario.support
            )
            for scenario in state_set.scenarios
        )
        return ConsequenceScenarioSet(
            episode_id=state_set.episode_id,
            chain_id=state_set.chain_id,
            node_id=state_set.node_id,
            stage=state_set.stage,
            representation=state_set.representation,
            registry_id=self.registry_id,
            registry_hash=self.registry_hash,
            scenarios=scenarios,
            support=SupportState.SUPPORTED,
        )
