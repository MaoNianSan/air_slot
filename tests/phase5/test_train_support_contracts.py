"""Phase 5 Train-support contract guardrails."""

from __future__ import annotations

import json

import pytest

from model.M3.stage2 import action_grid
from model.M3.support import (
    FLOOR_TO_MINUTES,
    HEADROOM_QUANTILE_NOMINAL,
    HEADROOM_QUANTILE_SENSITIVITY,
    QUANTILE_RULE,
    TURNAROUND_QUANTILE_NOMINAL,
    TURNAROUND_QUANTILE_SENSITIVITY,
)
from model.common.errors import ContractError
from validation.v2_phase5.train_support import (
    MAX_A2_STREAMING_BOUNDARY_DELTA,
    TURNAROUND_COUNT_AUTHORITY_ARTIFACT,
    TURNAROUND_REFERENCE_ARTIFACT,
    headroom_minutes,
    population_gates,
)


def _payloads():
    reference = json.loads(TURNAROUND_REFERENCE_ARTIFACT.read_text(encoding="utf-8"))
    authority = json.loads(
        TURNAROUND_COUNT_AUTHORITY_ARTIFACT.read_text(encoding="utf-8")
    )
    return reference, authority


def test_train_support_gate_uses_corrected_a2_reference_and_full_h1_count():
    reference, authority = _payloads()
    gates = population_gates(
        sample_count=2668531,
        sample_median=57.0,
        reference_payload=reference,
        count_authority_payload=authority,
    )
    assert gates["semantic_correction_match"] is True
    assert gates["reference_id"].startswith("sha256:")
    assert gates["expected_sample_count"] == 2668531
    assert gates["observed_sample_count"] == 2668531
    assert gates["sample_count_match"] is True
    assert gates["expected_median_minutes"] == pytest.approx(57.0)
    assert gates["median_match"] is True
    assert gates["a2_streaming_sample_count"] == 2668529
    assert gates["a2_streaming_boundary_delta"] == 2
    assert gates["a2_streaming_boundary_delta_consistent"] is True
    assert gates["a2_streaming_boundary_delta"] <= MAX_A2_STREAMING_BOUNDARY_DELTA


def test_train_support_gate_fails_on_wrong_median_count_or_correction():
    reference, authority = _payloads()
    with pytest.raises(ContractError, match="PHASE5_TRAIN_POPULATION_GATE_FAILED"):
        population_gates(
            sample_count=2668531,
            sample_median=51.0,
            reference_payload=reference,
            count_authority_payload=authority,
        )
    with pytest.raises(ContractError, match="PHASE5_TRAIN_POPULATION_GATE_FAILED"):
        population_gates(
            sample_count=2668000,
            sample_median=57.0,
            reference_payload=reference,
            count_authority_payload=authority,
        )
    broken = dict(reference)
    broken["semantic_correction"] = "WRONG_SEMANTICS"
    with pytest.raises(ContractError, match="PHASE5_TRAIN_POPULATION_GATE_FAILED"):
        population_gates(
            sample_count=2668531,
            sample_median=57.0,
            reference_payload=broken,
            count_authority_payload=authority,
        )


def test_manuscript_quantile_and_action_grid_contracts():
    assert TURNAROUND_QUANTILE_NOMINAL == 0.20
    assert TURNAROUND_QUANTILE_SENSITIVITY == (0.10, 0.30)
    assert HEADROOM_QUANTILE_NOMINAL == 0.90
    assert HEADROOM_QUANTILE_SENSITIVITY == (0.80, 0.95)
    assert FLOOR_TO_MINUTES == 5.0
    assert QUANTILE_RULE == "LINEAR_INTERPOLATION_SORTED_TRAIN"
    assert action_grid(45.0) == tuple(float(value) for value in range(0, 50, 5))
    with pytest.raises(ContractError, match="M3_ACTION_GRID_U_MAX_NOT_ON_FLOOR_GRID"):
        action_grid(42.0)


def test_factual_headroom_uses_turnaround_lower_bound_and_nonnegative_part():
    population = {
        "actual_departure_epoch_minutes": [100.0, 200.0],
        "scheduled_departure_epoch_minutes": [90.0, 210.0],
        "actual_arrival_epoch_minutes": [60.0, 170.0],
    }
    values = headroom_minutes(population, turnaround_lower_bound=20.0)
    assert values == pytest.approx([10.0, 0.0])
