"""``CONSEQUENCE_VARIANTS`` stage: frozen M2 consequences and Stage-I signals.

For every canonical node and every primary state variant the executor calls the
frozen M2 consequence service, forms the M2-owned comparison support
(``Omega^CS`` with the nominal ``m^CS >= 0.90`` requirement) and derives the two
Stage-I priority signals:

* ``P^D`` - the parallel delay comparator (common-support conditional mean of
  ``D^TO``),
* ``P^C = Phi_C(C^CU)`` - the unique consequence-based priority authority.

Both signals share one comparison-support attestation and one candidate queue.
Nodes below the common-support requirement keep a typed
``ABSTAIN_NO_COMMON_SUPPORT`` record; they are never zero-filled.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from model.M2.comparison_support import (
    PRIMARY_AGGREGATION_VIEW,
    delay_priority_signal,
    expected_cu_vector,
    consequence_priority_signal,
)
from model.common.decision_contracts import (
    ComparisonSupport,
    ConsequenceScenarioSet,
    PrioritySignal,
)
from model.common.decision_contracts import (
    NOMINAL_COMMON_SUPPORT_MASS,
    PREDEFINED_COMMON_SUPPORT_SENSITIVITY,
)
from validation.v2_phase5.common import (
    comparison_support_for,
    consequence_set,
)

from ..errors import _require
from . import stages as S
from .codec import (
    consequence_set_to_payload,
    priority_signal_to_payload,
)
from .nodes import CanonicalNode
from .services import FrozenScienceServices, binding_from_node
from .state_variants import state_sets_by_node


def build_consequence_variants(
    nodes: Sequence[CanonicalNode],
    *,
    state_variants: Mapping[str, Any],
    services: FrozenScienceServices,
) -> dict[str, Any]:
    """Form consequences, comparison support and Stage-I signals per variant."""

    rows: list[dict[str, Any]] = []
    state_sets = {
        variant: state_sets_by_node(state_variants, variant)
        for variant in S.PRIMARY_STATE_VARIANTS
    }
    for node in nodes:
        service = services.consequence_service(
            {node.node_id: binding_from_node(node)}
        )
        for variant in S.PRIMARY_STATE_VARIANTS:
            state_set = state_sets[variant][node.node_id]
            consequences = consequence_set(service, state_set)
            support = comparison_support_for(
                state_set,
                consequences,
                threshold=NOMINAL_COMMON_SUPPORT_MASS,
            )
            delay = delay_priority_signal(state_set, support)
            effect = consequence_priority_signal(
                consequences, support, view=PRIMARY_AGGREGATION_VIEW
            )
            rows.append(
                {
                    "node_id": node.node_id,
                    "episode_id": node.episode_id,
                    "chain_id": node.chain_id,
                    "stage": node.stage,
                    "variant": variant,
                    "representation_id": state_set.representation.representation_id,
                    "support": _support_payload(support),
                    "expected_cu": (
                        expected_cu_vector(consequences, support)
                        if support.included
                        else None
                    ),
                    "delay_signal": priority_signal_to_payload(delay),
                    "consequence_signal": priority_signal_to_payload(effect),
                    "consequence_set": consequence_set_to_payload(consequences),
                }
            )
    included = sum(1 for row in rows if row["support"]["included"])
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "row_count": len(rows),
        "common_support_rule": {
            "rule_id": _rule_id(rows),
            "estimand": _estimand(rows),
            "threshold": NOMINAL_COMMON_SUPPORT_MASS,
            "authority": "M2_COMPARISON_SUPPORT",
            "predefined_sensitivity_values": list(
                PREDEFINED_COMMON_SUPPORT_SENSITIVITY
            ),
            "sensitivity_status": "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES",
        },
        "cu_registry": dict(services.provenance),
        "aggregation_view": PRIMARY_AGGREGATION_VIEW,
        "priority_authority": {
            "consequence_based_priority_authority": "P^C = Phi_C(C^CU)",
            "delay_comparator": "P^D = E[D^TO | Omega^CS]",
            "shared_stage1_selector": True,
            "shared_candidate_queue": True,
        },
        "included_row_count": included,
        "abstaining_row_count": len(rows) - included,
        "rows": rows,
    }


def _support_payload(support: ComparisonSupport) -> dict[str, Any]:
    return {
        "rule_id": support.rule_id,
        "estimand": support.estimand,
        "supported_mass": support.supported_mass,
        "supported_scenario_ids": list(support.supported_scenario_ids),
        "scenario_count_total": support.scenario_count_total,
        "threshold": support.threshold,
        "included": support.included,
        "status": support.status.value,
        "reason_codes": list(support.reason_codes),
    }


def _rule_id(rows: Sequence[Mapping[str, Any]]) -> str:
    _require(bool(rows), "PHASE7_CONSEQUENCE_VARIANTS_EMPTY")
    return str(rows[0]["support"]["rule_id"])


def _estimand(rows: Sequence[Mapping[str, Any]]) -> str:
    return str(rows[0]["support"]["estimand"])


def rows_by_variant(
    payload: Mapping[str, Any], variant: str
) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["node_id"]): row
        for row in payload["rows"]
        if row["variant"] == variant
    }


def signals_by_variant(
    payload: Mapping[str, Any], variant: str
) -> dict[str, tuple[PrioritySignal, PrioritySignal]]:
    from .codec import priority_signal_from_payload

    resolved: dict[str, tuple[PrioritySignal, PrioritySignal]] = {}
    for node_id, row in rows_by_variant(payload, variant).items():
        resolved[node_id] = (
            priority_signal_from_payload(row["delay_signal"]),
            priority_signal_from_payload(row["consequence_signal"]),
        )
    return resolved


def consequence_sets_by_variant(
    payload: Mapping[str, Any], variant: str
) -> dict[str, ConsequenceScenarioSet]:
    from .codec import consequence_set_from_payload

    return {
        node_id: consequence_set_from_payload(row["consequence_set"])
        for node_id, row in rows_by_variant(payload, variant).items()
    }


__all__ = [
    "build_consequence_variants",
    "consequence_sets_by_variant",
    "rows_by_variant",
    "signals_by_variant",
]
