from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from src.m4 import adapt_m4_inputs, build_evidence_context, validate_m2_inputs, validate_m3_artifact
from src.m4.contracts import M4ContractError, M4UpstreamBlocked


def test_accepts_m2_v2_and_m3_v4(m4_input_factory, m3_artifact) -> None:
    bundle, losses = m4_input_factory()
    adapted = adapt_m4_inputs(bundle, losses, m3_artifact)
    assert adapted.metadata.m3_contract_version == "M3_RESPONSE_V4_ATOMIC_SUBITEM"
    assert len(adapted.sample_losses) == 4


def test_rejects_legacy_m2_channel_arrays(m3_artifact) -> None:
    with pytest.raises(M4ContractError, match="LEGACY_M2"):
        adapt_m4_inputs({"F": np.ones(2)}, tuple(), m3_artifact)


def test_rejects_legacy_m3_channel_recovery_contract(m4_input_factory) -> None:
    bundle, losses = m4_input_factory()
    with pytest.raises(M4ContractError, match="LEGACY_M3"):
        adapt_m4_inputs(bundle, losses, {"F": np.ones(2)})


def test_rejects_missing_subitem(m4_input_factory, replace_loss) -> None:
    bundle, losses = m4_input_factory()
    bad = dict(losses[0].subitem_loss_rmb)
    bad.pop("R_TAXI")
    broken = (replace_loss(losses[0], subitem_loss_rmb=bad), *losses[1:])
    with pytest.raises(M4ContractError, match="SUBITEM_SCHEMA_MISMATCH"):
        validate_m2_inputs(bundle, broken)


def test_rejects_invalid_artifact_shape(m3_artifact) -> None:
    recovery = dict(m3_artifact.subitem_recovery_rates)
    recovery["A11"] = recovery["A11"][:, :8]
    broken = replace(m3_artifact, subitem_recovery_rates=recovery)
    with pytest.raises(M4ContractError, match="RECOVERY_SHAPE_INVALID"):
        validate_m3_artifact(broken, formal_mode=False)


def test_rejects_nonzero_A00_recovery(m3_artifact) -> None:
    recovery = dict(m3_artifact.subitem_recovery_rates)
    recovery["A00"] = recovery["A00"].copy()
    recovery["A00"][0, 0] = 0.1
    with pytest.raises(M4ContractError, match="A00_RECOVERY"):
        validate_m3_artifact(replace(m3_artifact, subitem_recovery_rates=recovery), formal_mode=False)


def test_rejects_nonzero_A00_cost(m3_artifact) -> None:
    costs = dict(m3_artifact.implementation_costs_rmb)
    costs["A00"] = costs["A00"].copy()
    costs["A00"][0, 0] = 1.0
    with pytest.raises(M4ContractError, match="A00_COST"):
        validate_m3_artifact(replace(m3_artifact, implementation_costs_rmb=costs), formal_mode=False)


def test_rejects_test_fixture_in_formal_mode(m3_artifact) -> None:
    with pytest.raises(M4UpstreamBlocked, match="TEST_ONLY_ARTIFACT"):
        validate_m3_artifact(m3_artifact, formal_mode=True)


def test_pre_r2_not_mislabeled_r3(m4_input_factory) -> None:
    bundle, _ = m4_input_factory(
        schema="air-chain-core-2.0",
        revision="AIR_CHAIN_CORE_V2_R2",
        include_registries=False,
    )
    evidence = build_evidence_context(bundle)
    assert evidence.is_r2
    assert not evidence.is_formal_r3
    assert "PRE_R2_COMPATIBILITY_ONLY" in evidence.reason_codes


def test_pre_r3_registry_required_for_formal(m4_input_factory) -> None:
    bundle, _ = m4_input_factory(include_registries=False)
    evidence = build_evidence_context(bundle)
    assert not evidence.is_formal_r3
    assert "PRE_R3_REGISTRY_MISSING" in evidence.reason_codes
