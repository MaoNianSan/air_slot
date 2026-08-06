from __future__ import annotations

from copy import deepcopy

import pytest

from action_contract import load_action_contract
from src.m3 import (
    EXPECTED_ACTION_IDS,
    FORBIDDEN_ACTION_IDS,
    M3_ACTION_LIBRARY_VERSION,
    M3_CONTRACT_VERSION,
    OutcomeCoverage,
    ParameterStatus,
    load_m3_contract,
)


def test_explicit_contract_versions_and_unknown_failure() -> None:
    assert load_action_contract("V2")["action_ids"][0] == "A00"
    assert load_action_contract("V3")["action_library_version"] == "M3_RESPONSE_V3_EXPANDED_PROVISIONAL"
    assert load_action_contract("V4")["identity"]["name"] == M3_CONTRACT_VERSION
    with pytest.raises(ValueError, match="M3_CONTRACT_MISMATCH"):
        load_action_contract("V5")


def test_v4_has_version_bound_atomic_actions(m3_contract) -> None:
    assert tuple(m3_contract.catalog) == EXPECTED_ACTION_IDS
    identities = {
        (item.action_library_version, item.action_id)
        for item in m3_contract.catalog.values()
    }
    assert len(identities) == 21
    assert m3_contract.action_library_version == M3_ACTION_LIBRARY_VERSION
    assert not FORBIDDEN_ACTION_IDS.intersection(m3_contract.catalog)
    text = " ".join(
        f"{item.action_name} {item.action_family} {item.mechanism}"
        for item in m3_contract.catalog.values()
    ).lower()
    assert "combined" not in text
    assert "integrated" not in text


def test_aircraft_actions_are_partial_and_unconfigured(m3_contract, cfg) -> None:
    assert cfg.scientific["m3"]["action_count"] == 21
    assert FORBIDDEN_ACTION_IDS == frozenset({"A54", "A55"})
    for action_id in ("A51", "A52", "A53"):
        catalog = m3_contract.catalog[action_id]
        response = m3_contract.response_parameters[action_id]
        cost = m3_contract.cost_parameters[action_id]
        assert catalog.action_family == "aircraft_recovery"
        assert catalog.outcome_coverage is OutcomeCoverage.PARTIAL_SUPPORTED
        assert catalog.parameter_status is ParameterStatus.NOT_CONFIGURED
        assert response.parameter_status is ParameterStatus.NOT_CONFIGURED
        assert response.response_mean is None
        assert response.response_concentration is None
        assert response.secondary_multiplier is None
        assert response.failure_probability is None
        assert cost.parameter_status is ParameterStatus.NOT_CONFIGURED
        assert cost.cost_cv is None
        assert all(value is None for value in cost.fixed_mean_rmb.values())
        assert all(
            status is ParameterStatus.NOT_CONFIGURED
            for status in cost.channel_status.values()
        )


@pytest.mark.parametrize("forbidden_id", ("A54", "A55"))
def test_forbidden_action_ids_are_rejected(cfg, forbidden_id) -> None:
    source = deepcopy(cfg.scientific)
    source["m3"]["actions"][-1]["action_id"] = forbidden_id
    with pytest.raises(ValueError, match="M3_CONTRACT_MISMATCH"):
        load_m3_contract(source)


def test_combination_semantics_are_rejected_in_mechanism(cfg) -> None:
    source = deepcopy(cfg.scientific)
    source["m3"]["actions"][1]["mechanism"] = "balanced_integrated_recovery"
    with pytest.raises(ValueError, match="M3_CONTRACT_MISMATCH:combined action"):
        load_m3_contract(source)


def test_v4_is_the_only_active_formal_contract(cfg) -> None:
    assert cfg.scientific["m3"]["identity"]["name"] == M3_CONTRACT_VERSION
    assert cfg.scientific["m3"]["config_path"] == "config/m3_response_v4_atomic_subitem.yaml"
    assert "response_parameters" not in cfg.scientific["m3"]


def test_scenario_actions_are_excluded_from_formal_selection(m3_contract) -> None:
    for action_id in ("A64", "A71", "A72"):
        assert m3_contract.catalog[action_id].outcome_coverage is OutcomeCoverage.SCENARIO_ONLY
        assert action_id not in m3_contract.formal_action_ids
    assert "A00" in m3_contract.formal_action_ids
