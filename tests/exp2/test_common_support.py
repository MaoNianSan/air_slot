from types import SimpleNamespace

import pytest

from exp.exp2.common_support import (
    compute_common_support_mass,
    conditional_node_summary,
    identify_common_supported_scenarios,
    support_flags,
)
from exp.exp2.model_inputs import active_model_contract
from exp.exp2.protocol import COMPONENTS
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import SupportState
from model.common.estimand import FormalEstimandStatus


class _CompatibleCU:
    def __init__(self, compatible=True):
        self.compatible = compatible

    def compatible_with_registry(self, registry):
        return self.compatible


def _support_records(count, supported, weights=None):
    weights = weights or [1 / count] * count
    return tuple(
        {
            "scenario_id": index,
            "scenario_weight": weights[index],
            "common_supported": index < supported,
            "unsupported_reasons": () if index < supported else ("D_TO",),
            "delay_to": float(index + 1) if index < supported else None,
            "component_rows": tuple(
                SimpleNamespace(
                    native_quantity=float(index + component_index),
                    constructed_value_cu=float(index + component_index) / 2,
                )
                for component_index, _ in enumerate(COMPONENTS)
            ),
            "formal_scenario_status": "FORMAL_AVAILABLE",
        }
        for index in range(count)
    )


def _aligned_pair(*, weight=1.0, d_to=10.0, unsupported_component=None):
    typed = SimpleNamespace(
        episode_id="e",
        decision_node_id="n",
        scenario_id=0,
        scenario_weight=weight,
        d_to_support=(
            SupportState.SUPPORTED if d_to is not None else SupportState.ABSTAIN
        ),
        d_to_minutes=d_to,
    )
    rows = []
    for component in COMPONENTS:
        supported = component != unsupported_component
        rows.append(
            SimpleNamespace(
                component_id=component,
                support_state=(
                    SupportState.SUPPORTED if supported else SupportState.ABSTAIN
                ),
                native_quantity=0.0 if supported else None,
                constructed_value_cu=0.0 if supported else None,
                cu_status=(
                    CUNormalizationStatus.CU_FROZEN
                    if supported
                    else CUNormalizationStatus.CU_UNSUPPORTED
                ),
                cu_quantity=_CompatibleCU(supported),
            )
        )
    all_supported = unsupported_component is None
    mapped = SimpleNamespace(
        episode_id="e",
        decision_node_id="n",
        scenario_id=0,
        scenario_weight=weight,
        component_vector=SimpleNamespace(rows=tuple(rows)),
        formal_estimand_value=SimpleNamespace(
            status=(
                FormalEstimandStatus.FORMAL_AVAILABLE
                if all_supported
                else FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
            )
        ),
    )
    return typed, mapped


def test_uniform_250_historical_equivalence_and_thresholds():
    assert compute_common_support_mass(_support_records(250, 225)) == pytest.approx(
        225 / 250
    )
    assert support_flags(compute_common_support_mass(_support_records(250, 225)))[
        "support_primary"
    ]
    assert not support_flags(
        compute_common_support_mass(_support_records(250, 224))
    )["support_primary"]
    assert support_flags(compute_common_support_mass(_support_records(250, 125)))[
        "support_sensitivity"
    ]
    assert not support_flags(
        compute_common_support_mass(_support_records(250, 124))
    )["support_sensitivity"]


def test_uniform_64_current_equivalence_and_thresholds():
    assert compute_common_support_mass(_support_records(64, 58)) == pytest.approx(
        58 / 64
    )
    assert support_flags(compute_common_support_mass(_support_records(64, 58)))[
        "support_primary"
    ]
    assert not support_flags(compute_common_support_mass(_support_records(64, 57)))[
        "support_primary"
    ]
    assert support_flags(compute_common_support_mass(_support_records(64, 32)))[
        "support_sensitivity"
    ]
    assert not support_flags(compute_common_support_mass(_support_records(64, 31)))[
        "support_sensitivity"
    ]


def test_nonuniform_weights_use_probability_mass_not_count_ratio():
    records = _support_records(3, 1, weights=[0.6, 0.2, 0.2])
    assert compute_common_support_mass(records) == pytest.approx(0.6)
    assert compute_common_support_mass(records) != pytest.approx(1 / 3)


def test_common_support_identity_valid_zero_and_missing():
    _, registry, _ = active_model_contract()
    typed, mapped = _aligned_pair()
    records = identify_common_supported_scenarios((typed,), (mapped,), registry)
    assert records[0]["common_supported"] is True
    assert records[0]["component_rows"][0].native_quantity == 0.0

    typed_missing, mapped_complete = _aligned_pair(d_to=None)
    records = identify_common_supported_scenarios(
        (typed_missing,), (mapped_complete,), registry
    )
    assert records[0]["common_supported"] is False
    assert records[0]["delay_to"] is None

    typed_complete, mapped_missing = _aligned_pair(
        unsupported_component="P_itinerary"
    )
    records = identify_common_supported_scenarios(
        (typed_complete,), (mapped_missing,), registry
    )
    assert records[0]["common_supported"] is False
    assert "P_itinerary" in records[0]["unsupported_reasons"]


def test_conditional_weighting_and_full_support_equivalence():
    records = _support_records(3, 2, weights=[0.2, 0.3, 0.5])
    summary = conditional_node_summary(records)
    assert summary["common_support_mass"] == pytest.approx(0.5)
    assert summary["delay_to_mean_cs"] == pytest.approx((0.2 * 1 + 0.3 * 2) / 0.5)
    assert summary["formal_delay_mean_if_full"] is None

    full = conditional_node_summary(_support_records(2, 2, weights=[0.25, 0.75]))
    assert full["support_full"] is True
    assert full["delay_to_mean_cs"] == pytest.approx(full["formal_delay_mean_if_full"])
    for component in COMPONENTS:
        assert full[f"{component}_native_cs"] == pytest.approx(
            full[f"{component}_native_if_full"]
        )
        assert full[f"Z_{component}_cs"] == pytest.approx(
            full[f"Z_{component}_if_full"]
        )


def test_m2_formal_no_drop_rule_is_unchanged():
    frozen, _, _ = active_model_contract()
    assert frozen.support_rule == "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY"
