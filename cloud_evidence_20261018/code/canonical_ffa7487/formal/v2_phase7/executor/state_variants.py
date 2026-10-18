"""``STATE_VARIANTS`` stage: the frozen M1 representations per canonical node.

The four primary variants are the frozen Phase-7 main design:

* ``HISTORY_JOINT``     - frozen History pipeline sampling (H16 primary),
* ``CURRENT_JOINT``     - frozen Current comparator pipeline sampling,
* ``HISTORY_POINT``     - M1 weighted joint medoid of the History sample,
* ``HISTORY_MARGINAL``  - M1 deterministic coordinate permutation of the
                          History sample (never a claim of independence).

Every scenario draw comes from :meth:`M1Pipeline.sample_from_pre` with the frozen
scenario count, the frozen sampling seed and the frozen tail continuations. The
executor never re-implements an M1 sampling rule.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import torch

from model.M1.state_representation import (
    MARGINAL_IDENTITY_NOTE,
    build_marginal_representation,
    build_point_representation,
)
from model.common.decision_contracts import (
    StateRepresentationSpec,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
)
from model.common.enums import OperationalStage
from validation.v2_phase5.common import (
    representation_spec,
    state_set_from_m1_scenarios,
)

from ..errors import _require
from . import stages as S
from .codec import representation_to_payload, state_set_to_payload
from .nodes import CanonicalNode, restore_pre_environment
from .services import FrozenScienceServices


VARIANT_SOURCES: dict[str, str] = {
    "HISTORY_JOINT": "M1_FROZEN_H16_HISTORY_PIPELINE",
    "CURRENT_JOINT": "M1_FROZEN_CURRENT_COMPARATOR_PIPELINE",
    "HISTORY_POINT": "M1_WEIGHTED_JOINT_MEDOID_FROM_HISTORY_JOINT",
    "HISTORY_MARGINAL": "M1_DETERMINISTIC_COORDINATE_PERMUTATION_FROM_HISTORY_JOINT",
}

SAMPLED_VARIANTS = ("HISTORY_JOINT", "CURRENT_JOINT")
DERIVED_VARIANTS = ("HISTORY_POINT", "HISTORY_MARGINAL")


def variant_representations() -> dict[str, StateRepresentationSpec]:
    """Frozen representation identity of every primary variant."""

    return {
        "HISTORY_JOINT": representation_spec(
            TemporalKind.HISTORY, UncertaintyKind.JOINT
        ),
        "CURRENT_JOINT": representation_spec(
            TemporalKind.CURRENT, UncertaintyKind.JOINT
        ),
        "HISTORY_POINT": representation_spec(
            TemporalKind.HISTORY, UncertaintyKind.POINT
        ),
        "HISTORY_MARGINAL": representation_spec(
            TemporalKind.HISTORY, UncertaintyKind.MARGINAL
        ),
    }


def _sampled_state_set(
    node: CanonicalNode,
    *,
    pipeline: Any,
    representation: StateRepresentationSpec,
    services: FrozenScienceServices,
) -> StateScenarioSet:
    pre_state = restore_pre_environment(node.pre_state)
    values = torch.as_tensor(node.history_values, dtype=torch.float32)
    scenarios = pipeline.sample_from_pre(
        pre_state,
        values.unsqueeze(0),
        torch.tensor([len(values)]),
        observed=dict(node.observed),
        count=services.scenario_count,
        seed=services.scenario_seed,
        taxi_reference=services.taxi_reference,
    )
    _require(
        len(scenarios) == services.scenario_count,
        "PHASE7_STATE_VARIANT_SCENARIO_COUNT_MISMATCH",
        {"node_id": node.node_id, "scenarios": len(scenarios)},
    )
    return state_set_from_m1_scenarios(
        scenarios,
        episode_id=node.episode_id,
        chain_id=node.chain_id,
        node_id=node.node_id,
        stage=OperationalStage(node.stage),
        representation=representation,
    )


def build_state_variants(
    nodes: Sequence[CanonicalNode],
    *,
    services: FrozenScienceServices,
) -> dict[str, Any]:
    """Sample/derive every primary variant for every canonical node."""

    _require(bool(nodes), "PHASE7_STATE_VARIANTS_EMPTY_NODE_SET")
    representations = variant_representations()
    rows: dict[str, list[dict[str, Any]]] = {
        variant: [] for variant in S.PRIMARY_STATE_VARIANTS
    }
    for node in nodes:
        history_joint = _sampled_state_set(
            node,
            pipeline=services.h16_pipeline,
            representation=representations["HISTORY_JOINT"],
            services=services,
        )
        current_joint = _sampled_state_set(
            node,
            pipeline=services.current_pipeline,
            representation=representations["CURRENT_JOINT"],
            services=services,
        )
        resolved = {
            "HISTORY_JOINT": history_joint,
            "CURRENT_JOINT": current_joint,
            "HISTORY_POINT": build_point_representation(history_joint),
            "HISTORY_MARGINAL": build_marginal_representation(history_joint),
        }
        for variant in S.PRIMARY_STATE_VARIANTS:
            state_set = resolved[variant]
            rows[variant].append(
                {
                    "node_id": node.node_id,
                    "episode_id": node.episode_id,
                    "state_set": state_set_to_payload(state_set),
                }
            )
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "node_count": len(nodes),
        "variants": [
            {
                "variant": variant,
                "representation": representation_to_payload(representations[variant]),
                "representation_id": representations[variant].representation_id,
                "source": VARIANT_SOURCES[variant],
                "node_count": len(rows[variant]),
                "nodes": rows[variant],
            }
            for variant in S.PRIMARY_STATE_VARIANTS
        ],
        "sampling": {
            "scenario_count": services.scenario_count,
            "seed": services.scenario_seed,
            "seed_source": "M1_FROZEN_MANIFEST_TRAINING_SEED",
            "tail_manifest_path": services.provenance.get("tail_manifest_path"),
            "tail_manifest_hash": services.provenance.get("tail_manifest_hash"),
            "taxi_reference_id": services.provenance.get("taxi_reference_id"),
            "taxi_reference_hash": services.provenance.get("taxi_reference_hash"),
            "h16_model_id": services.provenance.get("h16_model_id"),
            "current_model_id": services.provenance.get("current_model_id"),
            "history_mode": "FULL_ADAPTIVE_CAUSAL_PREFIX",
            "comparator_history_mode": "NO_HISTORY_CURRENT_OBSERVATION",
        },
        "sensitivity": dict(S.SENSITIVITY_VARIANTS),
        "fixed_window_sensitivity_status": S.FIXED_WINDOW_SENSITIVITY_STATUS,
        "marginal_identity_note": MARGINAL_IDENTITY_NOTE,
    }


def variant_rows(
    payload: Mapping[str, Any], variant: str
) -> tuple[Mapping[str, Any], ...]:
    for block in payload["variants"]:
        if block["variant"] == variant:
            return tuple(block["nodes"])
    raise KeyError(variant)


def state_sets_by_node(
    payload: Mapping[str, Any], variant: str
) -> dict[str, StateScenarioSet]:
    from .codec import state_set_from_payload

    return {
        str(row["node_id"]): state_set_from_payload(row["state_set"])
        for row in variant_rows(payload, variant)
    }


__all__ = [
    "DERIVED_VARIANTS",
    "SAMPLED_VARIANTS",
    "VARIANT_SOURCES",
    "build_state_variants",
    "state_sets_by_node",
    "variant_representations",
    "variant_rows",
]
