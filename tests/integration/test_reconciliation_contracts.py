from datetime import timedelta
from pathlib import Path

import pytest
import torch
from model import M1, PRE
from model.M1.data import M1NormalizationArtifact
from model.M1.semantics import (
    DELAY_THRESHOLDS_MINUTES,
    FORMAL_FORECAST_HORIZONS_MINUTES,
    total_takeoff_delay_minutes,
)
from model.common.config import load_config_layers
from model.common.errors import ContractError
from tests.fixtures.pre.foundation_cases import build_request


def test_m1_forecast_horizons_are_not_delay_thresholds():
    assert FORMAL_FORECAST_HORIZONS_MINUTES == (0, 15, 60)
    assert DELAY_THRESHOLDS_MINUTES == (15, 30, 60)
    assert FORMAL_FORECAST_HORIZONS_MINUTES != DELAY_THRESHOLDS_MINUTES


def test_formal_m1_uses_development_frozen_hidden_size_selection():
    scientific = load_config_layers(Path("configs")).scientific
    normalization = M1NormalizationArtifact(fitted_split="train", values={})

    primary = M1.M1Pipeline.from_scientific_config(
        scientific, input_size=4, normalization=normalization
    )
    assert primary.model.hidden_size == 8
    with pytest.raises(ValueError, match="M1_HIDDEN_SIZE_NOT_IN_FROZEN_MODEL_SETTINGS"):
        M1.M1Pipeline.from_scientific_config(
            scientific, input_size=4, normalization=normalization, hidden_size=4
        )

    selected = M1.M1Pipeline.from_scientific_config(
        scientific, input_size=4, normalization=normalization, hidden_size=8
    )
    assert selected.model.hidden_size == 8


def test_signed_takeoff_delay_requires_the_train_frozen_taxi_reference():
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=12.5, t_tx_minutes=7.5, taxi_reference_minutes=5.0
    ) == 15.0
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=None, t_tx_minutes=7.5, taxi_reference_minutes=5.0
    ) is None
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=12.5, t_tx_minutes=7.5, taxi_reference_minutes=None
    ) is None


def test_m1_service_labels_fast_and_state_paths_explicitly():
    pre_state = PRE.build_pre_state(build_request()).pre_state
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    unconfigured = M1.M1Service(M1.M1Pipeline.smoke(), model_version="fixture")

    with pytest.raises(ContractError, match="M1_FAST_PATH_NOT_CONFIGURED"):
        unconfigured.predict_now(pre_state, values, lengths, mode="fast")

    service = M1.M1Service(
        M1.M1Pipeline.smoke(),
        model_version="fixture",
        fast_predictor=lambda *_: {"path": "fixture-fast"},
    )
    service.scheduled_update(pre_state)
    generated_at = pre_state.decision_node.decision_time + timedelta(minutes=5)
    fast = service.predict_now(
        pre_state, values, lengths, mode="fast", generated_at=generated_at
    )
    state = service.predict_now(
        pre_state, values, lengths, mode="state", generated_at=generated_at
    )

    assert fast.model_path is M1.M1ModelPath.FAST
    assert fast.fallback_status == "EXPLICIT_FAST_QUERY"
    assert fast.distributions == {"path": "fixture-fast"}
    assert state.model_path is M1.M1ModelPath.STATE_AWARE
    assert state.fallback_status == "NONE"
    assert fast.forecast_horizons_minutes == FORMAL_FORECAST_HORIZONS_MINUTES
    assert fast.delay_thresholds_minutes == DELAY_THRESHOLDS_MINUTES
    assert fast.decision_time == pre_state.decision_node.decision_time
    assert fast.information_cutoff == pre_state.decision_node.information_cutoff
    assert fast.roll_minutes == pre_state.decision_node.roll_minutes
    assert fast.model_version == "fixture"
    assert fast.scenario_count == 64
    assert "model_path=FAST" in fast.lineage
    assert fast.state_age_minutes == 5.0
    assert state.state_updated_at == fast.state_updated_at


def test_direct_query_does_not_reset_scheduled_update_timeline():
    pre_state = PRE.build_pre_state(build_request()).pre_state
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    service = M1.M1Service(M1.M1Pipeline.smoke(), model_version="fixture")
    service.scheduled_update(pre_state)
    first = service.predict_now(
        pre_state,
        values,
        lengths,
        generated_at=pre_state.decision_node.decision_time + timedelta(minutes=5),
    )
    second = service.predict_now(
        pre_state,
        values,
        lengths,
        generated_at=pre_state.decision_node.decision_time + timedelta(minutes=10),
    )
    assert first.state_updated_at == second.state_updated_at
    assert first.state_age_minutes == 5.0
    assert second.state_age_minutes == 10.0


