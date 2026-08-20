from __future__ import annotations

import pytest

from exp.exp2.artifacts.artifact_schema import (
    EXP2_ARTIFACT_SCHEMA_VERSION,
    ArtifactSupportStatus,
    Exp2ActionManifest,
    Exp2MonetaryMappingBundle,
    Exp2ResponseBundle,
    Exp2ResponseSource,
    Exp2ResponseSupport,
    Exp2RiskPolicyBundle,
)
from exp.exp2.execution.artifact_loader import (
    CULineage,
    CutoffProvenance,
    LoadedM1Artifact,
    LoadedM2Artifact,
)
from exp.exp2.execution.execution_manifest import ArtifactKind, ArtifactReference
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id


def hashed(model_type, payload, *, hash_field):
    return model_type(**payload, **{hash_field: content_id(payload)})


def response_bundle(
    action_id: str,
    *,
    support_class: Exp2ResponseSupport,
    source_type: Exp2ResponseSource,
) -> Exp2ResponseBundle:
    payload = {
        "action_id": action_id,
        "response_rule_id": f"RULE_{action_id}",
        "support_class": support_class,
        "source_type": source_type,
        "source_reference": f"TEST_FIXTURE_SOURCE_{action_id}",
        "parameter_version": "TEST_FIXTURE_V1",
        "freeze_id": "TEST_FIXTURE_FREEZE",
    }
    return hashed(Exp2ResponseBundle, payload, hash_field="rule_hash")


@pytest.fixture
def valid_action_manifest():
    return Exp2ActionManifest(
        manifest_id="EXP2_ACTION_TEST_FIXTURE",
        schema_version=EXP2_ARTIFACT_SCHEMA_VERSION,
        dataset_id="DATA2_TEST_FIXTURE",
        split="DEVELOPMENT_TEST_FIXTURE",
        cohort_hash="sha256:" + "1" * 64,
        action_ids=("A00", "A11"),
        action_registry_id="ACTION_TEMPLATES_V1",
        action_registry_hash="sha256:" + "2" * 64,
        response_registry_id="M3_RESPONSE_SCENARIO_V1",
        response_registry_hash="sha256:" + "3" * 64,
    )


@pytest.fixture
def valid_responses():
    return (
        response_bundle(
            "A00",
            support_class=Exp2ResponseSupport.SUPPORTED,
            source_type=Exp2ResponseSource.OPERATIONAL_RULE,
        ),
        response_bundle(
            "A11",
            support_class=Exp2ResponseSupport.SCENARIO_ASSUMPTION,
            source_type=Exp2ResponseSource.SCENARIO_ASSUMPTION,
        ),
    )


@pytest.fixture
def valid_mapping():
    payload = {
        "mapping_id": "EXP2_MAPPING_TEST_FIXTURE",
        "schema_version": EXP2_ARTIFACT_SCHEMA_VERSION,
        "component_ids": tuple(CONSEQUENCE_COMPONENTS),
        "mapping_function_reference": {
            component: f"TEST_FIXTURE_FUNCTION:{component}"
            for component in CONSEQUENCE_COMPONENTS
        },
        "source_reference": {
            component: (f"TEST_FIXTURE_SOURCE:{component}",)
            for component in CONSEQUENCE_COMPONENTS
        },
        "version": "TEST_FIXTURE_V1",
        "support_status": ArtifactSupportStatus.FROZEN,
        "interpretation": "CONSTRUCTED_INTERNAL_LOSS_UNIT",
    }
    return hashed(Exp2MonetaryMappingBundle, payload, hash_field="hash")


@pytest.fixture
def valid_risk_policy():
    payload = {
        "policy_id": "EXP2_RISK_TEST_FIXTURE",
        "tail_policy": "TEST_FIXTURE_UPPER_LOSS_TAIL",
        "CVaR_policy": "TEST_FIXTURE_WEIGHTED_CVAR",
        "parameters": {
            "alpha": 0.5,
            "expected_loss_coefficient": 0.5,
            "cvar_coefficient": 0.5,
        },
        "version": "TEST_FIXTURE_V1",
        "support_status": ArtifactSupportStatus.FROZEN,
    }
    return hashed(Exp2RiskPolicyBundle, payload, hash_field="hash")


@pytest.fixture
def loaded_m1_m2():
    m1_reference = ArtifactReference(
        artifact_kind=ArtifactKind.M1,
        path="m1_test_fixture.json",
        artifact_version="M1_TEST_FIXTURE_V1",
        artifact_hash="sha256:" + "4" * 64,
    )
    m2_reference = ArtifactReference(
        artifact_kind=ArtifactKind.M2,
        path="m2_test_fixture.json",
        artifact_version="M2_TEST_FIXTURE_V1",
        artifact_hash="sha256:" + "5" * 64,
    )
    m1 = LoadedM1Artifact(
        reference=m1_reference,
        scenarios=({"scenario_id": 0, "scenario_weight": 1.0},),
        cutoff_provenance=CutoffProvenance(
            decision_node_id="TEST_NODE",
            decision_time_utc="2026-08-20T08:00:00+00:00",
            information_cutoff_utc="2026-08-20T08:00:00+00:00",
            availability_rule="AVAILABILITY_TIME_LE_INFORMATION_CUTOFF",
            source_manifest_hash="sha256:" + "6" * 64,
        ),
        scenario_hash="sha256:" + "7" * 64,
    )
    m2 = LoadedM2Artifact(
        reference=m2_reference,
        consequences=({"scenario_id": 0, "scenario_weight": 1.0},),
        cu_lineage=CULineage(
            registry_id="M2_TEST_FIXTURE",
            registry_hash="sha256:" + "8" * 64,
            freeze_id="M2_TEST_FIXTURE_FREEZE",
            reference_period="TEST_FIXTURE",
        ),
        consequence_hash="sha256:" + "9" * 64,
    )
    return m1, m2


@pytest.fixture
def valid_gate_inputs(
    loaded_m1_m2,
    valid_action_manifest,
    valid_responses,
    valid_mapping,
    valid_risk_policy,
):
    m1, m2 = loaded_m1_m2
    return {
        "m1_artifact": m1,
        "m2_artifact": m2,
        "action_manifest": valid_action_manifest,
        "response_bundles": valid_responses,
        "monetary_mapping": valid_mapping,
        "risk_policy": valid_risk_policy,
    }
