from __future__ import annotations

import json
from pathlib import Path

import pytest

from exp.exp2.execution.execution_manifest import (
    ArtifactKind,
    ArtifactReference,
    Exp2ExecutionManifest,
)
from model.M3.action_response import ActionEvaluationEnvelope, ActionResponseRule
from model.M4.residual_risk import RankingAuthority, RiskEvaluationEnvelope
from model.common.identity import content_id


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "exp2_smoke"
ENVELOPE_FILES = {
    ArtifactKind.M1: "m1_scenario_fixture.json",
    ArtifactKind.M2: "m2_consequence_fixture.json",
    ArtifactKind.M3: "m3_action_manifest_fixture.json",
    ArtifactKind.M4: "m4_mapping_fixture.json",
}


def _read(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def smoke_package():
    envelopes = {kind: _read(name) for kind, name in ENVELOPE_FILES.items()}
    responses = _read("m3_response_bundle_fixture.json")
    risk_policy = _read("m4_risk_policy_fixture.json")
    references = {
        kind: ArtifactReference(
            artifact_kind=kind,
            path=ENVELOPE_FILES[kind],
            artifact_version=envelope["artifact_version"],
            artifact_hash=envelope["artifact_hash"],
        )
        for kind, envelope in envelopes.items()
    }
    manifest = Exp2ExecutionManifest(
        dataset_id="TEST_ONLY_SMOKE",
        split="SMOKE",
        seed=0,
        m1_artifact=references[ArtifactKind.M1],
        m2_artifact=references[ArtifactKind.M2],
        m3_artifact=references[ArtifactKind.M3],
        m4_artifact=references[ArtifactKind.M4],
        variant_id="EXP2A_JOINT",
        config_hash="sha256:" + "7" * 64,
    )
    return {
        "root": FIXTURE_ROOT,
        "envelopes": envelopes,
        "responses": responses,
        "risk_policy": risk_policy,
        "manifest": manifest,
    }


@pytest.fixture(scope="session")
def smoke_model_versions():
    return {
        name: f"TEST_ONLY_SMOKE_{name}_V1"
        for name in ("M1", "M2", "M3", "M4")
    }


@pytest.fixture
def smoke_downstream(smoke_package):
    calls: list[dict] = []
    response_by_action = {
        item["action_id"]: item for item in smoke_package["responses"]["responses"]
    }
    alpha = smoke_package["risk_policy"]["parameters"]["alpha"]
    variant_scores: dict[str, float] = {}

    def m3_executor(*, variant_id, scenarios, consequences, m3_artifact):
        calls.append({
            "stage": "M3",
            "variant_id": variant_id,
            "scenario_variant": scenarios.variant_id,
            "consequence_variant": consequences.variant_id,
            "scenario_hash": scenarios.representation_hash,
            "consequence_hash": consequences.representation_hash,
        })
        variant_scores[variant_id] = float(
            len(scenarios.samples) + len(consequences.scenarios)
        )
        return tuple(
            ActionEvaluationEnvelope.model_construct(
                action_id=action_id,
                action_family="TEST_ONLY_SMOKE",
                response_rule=ActionResponseRule.model_construct(
                    rule_hash=response_by_action[action_id]["rule_hash"]
                ),
                input_scenario_ids=tuple(range(len(scenarios.samples))),
            )
            for action_id in m3_artifact.action_ids
        )

    def m4_evaluator(*, variant_id, m3_envelopes, m4_artifact):
        calls.append({
            "stage": "M4",
            "variant_id": variant_id,
            "m3_hashes": tuple(item.envelope_hash for item in m3_envelopes),
        })
        base = variant_scores[variant_id]
        return tuple(
            RiskEvaluationEnvelope.model_construct(
                action_id=envelope.action_id,
                m3_envelope_hash=envelope.envelope_hash,
                monetary_system_id="TEST_ONLY_SMOKE",
                monetary_mapping_registry_hash=m4_artifact.monetary_mapping_hash,
                risk_policy_hash=m4_artifact.risk_policy_hash,
                alpha=alpha,
                ranking_authority=RankingAuthority.CONDITIONAL,
                residual_risk_objective=base + index,
                monetary_loss_cvar_alpha=base + index + 0.5,
            )
            for index, envelope in enumerate(m3_envelopes)
        )

    return calls, m3_executor, m4_evaluator


def build_production_manifest_copy(
    tmp_path: Path,
    smoke_package: dict,
    *,
    keep_test_only_m4: bool = False,
    drop_m3_response: bool = False,
    drop_m4_risk_policy: bool = False,
) -> Exp2ExecutionManifest:
    references = {}
    for kind, source in smoke_package["envelopes"].items():
        envelope = json.loads(json.dumps(source))
        envelope["artifact_scope"] = (
            "TEST_ONLY_SMOKE"
            if kind is ArtifactKind.M4 and keep_test_only_m4
            else "SCIENTIFIC"
        )
        if kind is ArtifactKind.M3 and drop_m3_response:
            envelope["payload"].pop("response_registry_hash")
        if kind is ArtifactKind.M4:
            if not keep_test_only_m4:
                envelope["payload"]["monetary_mapping_status"] = "FROZEN"
                envelope["payload"]["risk_policy_status"] = "FROZEN"
            if drop_m4_risk_policy:
                envelope["payload"].pop("risk_policy_hash")
                envelope["payload"].pop("risk_policy_status")
        envelope["artifact_hash"] = content_id(envelope["payload"])
        path = tmp_path / ENVELOPE_FILES[kind]
        path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        references[kind] = ArtifactReference(
            artifact_kind=kind,
            path=path.name,
            artifact_version=envelope["artifact_version"],
            artifact_hash=envelope["artifact_hash"],
        )
    return Exp2ExecutionManifest(
        dataset_id="TEST_ONLY_SMOKE_PRODUCTION_GATE_PROBE",
        split="DEVELOPMENT_GATE_PROBE",
        seed=0,
        m1_artifact=references[ArtifactKind.M1],
        m2_artifact=references[ArtifactKind.M2],
        m3_artifact=references[ArtifactKind.M3],
        m4_artifact=references[ArtifactKind.M4],
        variant_id="EXP2A_JOINT",
        config_hash="sha256:" + "8" * 64,
    )
