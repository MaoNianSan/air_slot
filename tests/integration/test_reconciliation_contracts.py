from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
import torch
import yaml

from exp.common.contracts import ExperimentRunManifest, assert_final_test_immutable
from exp.exp1.variants import construct_exp1_variant
from exp.exp2.representations import point_collapse, shuffle_scenario_lineage
from exp.exp3.ablations import transformed_ablation
from exp.exp4.strata import decompose_principal_outputs
from model import M1, PRE
from model.M1.data import M1NormalizationArtifact
from model.M1.semantics import (
    DELAY_THRESHOLDS_MINUTES,
    FORMAL_FORECAST_HORIZONS_MINUTES,
    takeoff_delay_minutes,
)
from model.common.config import load_config_layers
from model.common.errors import ContractError
from model.common.identity import content_id
from tests.fixtures.pre.foundation_cases import build_request


def test_m1_forecast_horizons_are_not_delay_thresholds():
    assert FORMAL_FORECAST_HORIZONS_MINUTES == (0, 15, 60)
    assert DELAY_THRESHOLDS_MINUTES == (15, 30, 60)
    assert FORMAL_FORECAST_HORIZONS_MINUTES != DELAY_THRESHOLDS_MINUTES


def test_formal_m1_requires_explicit_hidden_size_selection():
    scientific = load_config_layers(Path("configs")).scientific
    normalization = M1NormalizationArtifact(fitted_split="train", values={})

    with pytest.raises(ValueError, match="M1_HIDDEN_SIZE_SELECTION_REQUIRED"):
        M1.M1Pipeline.from_scientific_config(
            scientific, input_size=4, normalization=normalization
        )
    with pytest.raises(ValueError, match="M1_HIDDEN_SIZE_NOT_IN_DEVELOPMENT_CANDIDATES"):
        M1.M1Pipeline.from_scientific_config(
            scientific, input_size=4, normalization=normalization, hidden_size=8
        )

    selected = M1.M1Pipeline.from_scientific_config(
        scientific, input_size=4, normalization=normalization, hidden_size=16
    )
    assert selected.model.hidden_size == 16


def test_legacy_additive_helper_is_not_the_v5_formal_delay_contract():
    assert takeoff_delay_minutes(12.5, 7.5) == 20.0
    assert takeoff_delay_minutes(None, 7.5) is None
    assert takeoff_delay_minutes(12.5, None) is None


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
    assert fast.state_age_minutes == 5.0


def test_exp1_variants_are_copy_isolated_from_formal_artifacts():
    formal = {"episodes": [{"episode_id": "e1", "values": [1, 2]}]}
    before = deepcopy(formal)
    variant = construct_exp1_variant(formal, "current")
    variant["episodes"][0]["values"].append(3)

    assert formal == before
    assert variant["evaluation_variant"] == "current"


def test_exp2_point_and_shuffle_reuse_the_frozen_m1_source():
    scenarios = (
        {"scenario_weight": 0.25, "r_ib_minutes": 4.0,
         "r_ob_minutes": 10.0, "t_tx_minutes": 2.0},
        {"scenario_weight": 0.75, "r_ib_minutes": 8.0,
         "r_ob_minutes": 20.0, "t_tx_minutes": 6.0},
    )
    source_hash = content_id(scenarios)

    point = point_collapse(scenarios)
    first, first_audit = shuffle_scenario_lineage(scenarios, seed=19)
    repeated, repeated_audit = shuffle_scenario_lineage(scenarios, seed=19)

    assert point["source_m1_artifact_hash"] == source_hash
    assert point["point_rule"] == "WEIGHTED_JOINT_SCENARIO_MEDOID"
    assert point["r_ib_minutes"] == 8.0
    assert point["r_ob_minutes"] == 20.0
    assert point["t_tx_minutes"] == 6.0
    assert point["d_to_minutes"] is None
    assert point["d_to_status"] == "REFERENCE_TERMS_REQUIRED"
    assert first == repeated
    assert first_audit == repeated_audit
    assert first_audit["source_m1_artifact_hash"] == source_hash
    assert first_audit["marginals_preserved"] is True
    assert content_id(scenarios) == source_hash


@pytest.mark.parametrize(
    "ablation", ("no_induced", "no_evidence_distinction", "no_coverage_restriction")
)
def test_exp3_ablations_transform_copies_only(ablation):
    formal = {
        "candidates": [{"induced": {"x": 1}, "induced_response": {"y": 2}}],
        "consequence_rows": [{"evidence_class": "DIRECT"}],
    }
    before = deepcopy(formal)
    transformed = transformed_ablation(formal, ablation)

    assert formal == before
    assert transformed is not formal
    assert transformed["evaluation_ablation"] == ablation


def test_exp4_strata_decompose_principal_outputs_without_retraining():
    config = yaml.safe_load(Path("configs/evaluation/exp4.yaml").read_text(encoding="utf-8"))
    principal = ({"episode_id": "e1", "disruption_severity": 2.0},)
    before = deepcopy(principal)
    strata = {
        "disruption_severity": {"label": "FROZEN_BIN"},
        "operational_stage": {"missing": "UNSUPPORTED"},
    }

    decomposed = decompose_principal_outputs(
        principal, development_frozen_strata=strata
    )

    assert config["retrain_by_stratum"] is False
    assert principal == before
    assert decomposed[0]["operational_strata"] == {
        "disruption_severity": "FROZEN_BIN",
        "operational_stage": "UNSUPPORTED",
    }


def test_final_test_tuning_and_contract_changes_invalidate_the_run():
    before = ExperimentRunManifest(
        experiment="exp1",
        dataset_instance_id="data2_2019",
        dataset_role="MAIN_TEXT_PRINCIPAL",
        variant_ids=("current",),
        input_manifest_hash="input",
        config_hash="config",
        status="PASS",
        split="FINAL_TEST",
        scientific_config_hash="science",
        evaluation_config_hash="evaluation",
        registry_manifest_hash="registry",
        split_contract_hash="split",
        cohort_hash="cohort",
        primary_metric="metric",
        scenario_count=1000,
    )
    tuned = before.model_copy(update={"tuning_events": ("changed_threshold",)})
    changed = before.model_copy(update={"evaluation_config_hash": "changed"})

    with pytest.raises(ContractError, match="FINAL_TEST_TUNING_INVALIDATES_PROMOTION"):
        tuned.final_test_guard()
    with pytest.raises(ContractError, match="FINAL_TEST_IMMUTABILITY_VIOLATION"):
        assert_final_test_immutable(before, changed)
