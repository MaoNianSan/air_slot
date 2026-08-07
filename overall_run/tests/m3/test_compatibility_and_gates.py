from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from src.failures import M3ContractMismatch, M3ParameterNotFrozen, M4ContractMismatch
from src.m3 import validate_m2_compatibility
from src.m4 import evaluate_m4, fit_m4, screen_physical_actions
from src.pipeline import inspect_m3_runtime_status, run_experiment


def test_m2_v2_compatibility_passes_without_zeroing_unsupported(m3_contract, cfg) -> None:
    m2 = deepcopy(cfg.scientific["m2"])
    result = validate_m2_compatibility(m3_contract, m2)
    assert result.status == "PASS"
    assert m3_contract.footprints["A31"].roles["P_CONNECTION"].value == "PRIMARY"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda m2: m2.update(identity="LEGACY_SCALAR"), "M3_M2_CONTRACT_MISMATCH"),
        (lambda m2: m2.update(subitem_contract_version="OLD"), "M3_M2_CONTRACT_MISMATCH"),
        (lambda m2: m2["constructed_units"].update(version="CU_V1"), "M3_M2_CONTRACT_MISMATCH"),
        (lambda m2: m2.pop("valuation_version"), "M3_M2_CONTRACT_MISMATCH"),
    ],
)
def test_m2_compatibility_mismatches_are_explicit(m3_contract, cfg, mutation, code) -> None:
    m2 = deepcopy(cfg.scientific["m2"])
    mutation(m2)
    with pytest.raises(RuntimeError, match=code):
        validate_m2_compatibility(m3_contract, m2)


def test_pipeline_reports_real_upstream_readiness_gate(cfg) -> None:
    status = inspect_m3_runtime_status(cfg)
    assert status.contract_ready is True
    assert status.compatibility_ready is True
    assert status.parameters_frozen is False
    with pytest.raises(M3ParameterNotFrozen, match="M3_PARAMETER_NOT_FROZEN"):
        run_experiment(cfg, "fast")


def test_pipeline_rejects_invalid_v4_contract_before_parameter_gate(cfg) -> None:
    merged = deepcopy(cfg.merged)
    merged["m3"]["identity"]["name"] = "M3_RESPONSE_V4_INVALID"
    invalid = replace(cfg, merged=merged)
    status = inspect_m3_runtime_status(invalid)
    assert status.contract_ready is False
    with pytest.raises(M3ContractMismatch, match="M3_CONTRACT_MISMATCH"):
        run_experiment(invalid, "fast")


def test_legacy_m4_api_is_retired_after_v2_migration(cfg, m3_contract, fixture_artifact) -> None:
    with pytest.raises(M4ContractMismatch, match="M4_LEGACY_CONTRACT_RETIRED"):
        fit_m4(cfg.scientific, response_library=fixture_artifact)
    with pytest.raises(M4ContractMismatch, match="M4_LEGACY_CONTRACT_RETIRED"):
        evaluate_m4(None, {}, None, {}, fixture_artifact, None)
    with pytest.raises(M4ContractMismatch, match="M4_LEGACY_CONTRACT_RETIRED"):
        screen_physical_actions(
            rules=None,
            snapshots=None,
            actions=dict(m3_contract.catalog),
            trigger=[],
        )
