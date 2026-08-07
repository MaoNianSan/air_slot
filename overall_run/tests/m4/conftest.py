from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import load_config
from src.m2.contracts import (
    ActivationStatus,
    AuditContext,
    AvailabilityStatus,
    FlightContext,
    M2InputBundle,
    M2InputStatus,
    M2Metadata,
    M2SampleLoss,
    ParameterStatus,
    PassengerContext,
    ResourceContext,
    SubitemActivation,
    ValuationContext,
)
from src.m3 import generate_test_fixture_library, load_m3_contract
from src.m3.contracts import SUBITEMS_M2_V2


UTC = timezone.utc


@pytest.fixture(scope="session")
def cfg():
    return load_config(Path(__file__).resolve().parents[2], "fast")


@pytest.fixture(scope="session")
def m3_contract(cfg):
    return load_m3_contract(cfg.scientific)


@pytest.fixture(scope="session")
def m3_artifact(cfg, m3_contract):
    return generate_test_fixture_library(
        m3_contract,
        n_draws=64,
        base_seed=20260807,
        m2_contract=cfg.scientific["m2"],
    )


def _provenance(
    *,
    schema: str = "air-chain-core-2.1",
    revision: str = "AIR_CHAIN_CORE_V2_R3",
    include_registries: bool = True,
    stage: str = "TURNAROUND",
) -> dict[str, dict[str, object]]:
    lineage = {
        "pre_contract_id": "AIR_CHAIN_CORE_V2",
        "pre_schema_version": schema,
        "pre_research_revision": revision,
        "availability_policy_status": "LATEST_LEGAL_AVAILABLE",
    }
    if include_registries:
        lineage.update({
            "input_rule_registry_hash": "1" * 64,
            "formula_registry_hash": "2" * 64,
        })
    return {
        "__pre_lineage__": lineage,
        "__stage__": {"flight_chain_stage": stage},
        "execution_window_margin": {"evidence_type": "DERIVED", "proxy_status": "NONE"},
        "airport_flow_pressure": {"evidence_type": "DERIVED", "proxy_status": "NONE"},
        "connection_slack": {"evidence_type": "EMPIRICAL_REFERENCE", "proxy_status": "EXPLICIT_PROXY"},
        "connection_pressure": {"evidence_type": "EMPIRICAL_REFERENCE", "proxy_status": "EXPLICIT_PROXY"},
        "passenger_load_proxy": {"evidence_type": "EMPIRICAL_REFERENCE", "proxy_status": "EXPLICIT_PROXY"},
        "passenger_care_rule": {"evidence_type": "EXTERNAL_STANDARD", "assumption_match_status": "MATCH"},
        "taxi_reference": {"evidence_type": "UNSUPPORTED"},
        "rebooking_scarcity": {"evidence_type": "UNSUPPORTED"},
        "gate_availability": {"evidence_type": "UNSUPPORTED"},
        "ground_handler_availability": {"evidence_type": "UNSUPPORTED"},
        "tow_resource_availability": {"evidence_type": "UNSUPPORTED"},
        "aircraft_resource_availability": {"evidence_type": "SCENARIO_PARAMETER"},
        "standby_aircraft_availability": {"evidence_type": "SCENARIO_PARAMETER"},
        "crew_resource_availability": {"evidence_type": "SCENARIO_PARAMETER"},
        "standby_crew_availability": {"evidence_type": "SCENARIO_PARAMETER"},
        "continuity_exposure": {"evidence_type": "EMPIRICAL_REFERENCE", "future_observed_chain_used": False},
        "downstream_leg_count": {"evidence_type": "EMPIRICAL_REFERENCE", "future_observed_chain_used": False},
    }


def _loss(sample_id: int, weight: float) -> M2SampleLoss:
    subitems = {
        name: float((sample_id + 1) * (index + 1))
        for index, name in enumerate(SUBITEMS_M2_V2)
    }
    channels = {
        "F": sum(subitems[name] for name in SUBITEMS_M2_V2[:3]),
        "P": sum(subitems[name] for name in SUBITEMS_M2_V2[3:6]),
        "R": sum(subitems[name] for name in SUBITEMS_M2_V2[6:9]),
    }
    return M2SampleLoss(
        episode_id="ep-m4",
        snapshot_id="snap-m4",
        sample_id=sample_id,
        sample_weight=weight,
        turn_deficit_minutes=1.0,
        turn_deficit_semantics="TEST_ONLY",
        extra_offblock_wait_minutes=1.0,
        extra_taxi_minutes=1.0,
        takeoff_delay_minutes=1.0,
        event_status={},
        event_semantics={},
        event_source={},
        quantities={name: 1.0 for name in SUBITEMS_M2_V2},
        constructed_units={name: subitems[name] for name in SUBITEMS_M2_V2},
        channel_constructed_units=channels,
        subitem_loss_rmb=subitems,
        channel_loss_rmb=channels,
        total_pre_action_loss_rmb=sum(subitems.values()),
        resolved_only_total_pre_action_loss_rmb=sum(subitems.values()),
        m2_input_status=M2InputStatus.VALID,
        tail_resolution_status="RESOLVED",
        evidence_status={name: "TEST_ONLY_SUPPORTED" for name in SUBITEMS_M2_V2},
        proxy_status={name: "NONE" for name in SUBITEMS_M2_V2},
        audit_status="VALIDATED",
    )


@pytest.fixture
def m4_input_factory():
    def factory(
        *,
        schema: str = "air-chain-core-2.1",
        revision: str = "AIR_CHAIN_CORE_V2_R3",
        include_registries: bool = True,
        stage: str = "TURNAROUND",
        provenance_updates: dict[str, dict[str, object]] | None = None,
    ):
        query = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
        losses = tuple(_loss(index, weight) for index, weight in enumerate((0.1, 0.2, 0.3, 0.4)))
        scenarios = tuple(
            SimpleNamespace(sample_id=index, episode_id="ep-m4", snapshot_id="snap-m4")
            for index in range(len(losses))
        )
        activations = {
            name: SubitemActivation(
                subitem=name,
                channel=name[0],
                status=ActivationStatus.ACTIVE,
                support_reason="TEST_ONLY_SUPPORTED",
                input_evidence_level="TEST_ONLY",
                rule_version="TEST_RULE_V1",
                value_parameter_version="TEST_VALUE_V1",
            )
            for name in SUBITEMS_M2_V2
        }
        provenance = _provenance(
            schema=schema,
            revision=revision,
            include_registries=include_registries,
            stage=stage,
        )
        for key, value in (provenance_updates or {}).items():
            provenance[key] = value
        support = {
            key: (
                AvailabilityStatus.PROXY_AVAILABLE
                if value.get("evidence_type") == "EMPIRICAL_REFERENCE"
                else AvailabilityStatus.AVAILABLE
                if value.get("evidence_type") in {"DERIVED", "EXTERNAL_STANDARD"}
                else AvailabilityStatus.UNSUPPORTED
            )
            for key, value in provenance.items()
            if not key.startswith("__")
        }
        bundle = M2InputBundle(
            metadata=M2Metadata(
                episode_id="ep-m4",
                snapshot_id="snap-m4",
                snapshot_version=1,
                query_time=query,
                information_cutoff=query,
                pre_bundle_id="a" * 64,
                m1_bundle_id="m1-test-bundle",
                m1_model_version="m1-test-model",
                m1_sampling_version="M1_SAMPLING_V2",
            ),
            joint_scenarios=scenarios,
            flight_context=FlightContext(
                turnaround_reference_minutes=30.0,
                turnaround_reference_type="TEST_ONLY",
                continuity_exposure=1.0,
                downstream_leg_count=1,
                execution_window_margin=1.0,
            ),
            passenger_context=PassengerContext(
                passenger_load_proxy=100.0,
                connection_pressure=0.5,
                connection_slack=0.5,
                rebooking_scarcity=None,
            ),
            resource_context=ResourceContext(airport_flow_pressure=0.8),
            context_support=support,
            context_provenance=provenance,
            normalization_version="TEST_NORMALIZATION_V1",
            subitem_activation=activations,
            valuation_context=ValuationContext(
                valuation_version="TEST_VALUES_V1",
                parameter_status=ParameterStatus.CONFIGURED,
                currency_mapping_version="IDENTITY_TEST_V1",
                currency_mapping_mode="IDENTITY",
                channel_rates={"F": 1.0, "P": 1.0, "R": 1.0},
                test_only=True,
                source="SYNTHETIC_FIXTURE",
            ),
            audit_context=AuditContext(
                evidence_status={name: "TEST_ONLY_SUPPORTED" for name in SUBITEMS_M2_V2},
                proxy_status={name: "NONE" for name in SUBITEMS_M2_V2},
                overflow_status="NONE",
                tail_resolution_status="RESOLVED",
                parameter_status="CONFIGURED",
                currency_mapping_status="CONFIGURED",
                formal_reconstruction_gate="PASS",
                audit_status="VALIDATED",
            ),
            input_status=M2InputStatus.VALID,
        )
        return bundle, losses
    return factory


@pytest.fixture
def opportunity_overrides(m3_contract):
    return {action_id: 1.0 for action_id in m3_contract.catalog if action_id != "A00"}


@pytest.fixture
def replace_loss():
    return replace
