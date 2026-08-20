"""Identity-locked binding of Exp2 representations to supplied M3/M4 callables."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from model.M3.action_response import ActionEvaluationEnvelope
from model.M4.residual_risk import RiskEvaluationEnvelope
from model.common.identity import content_id

from ..protocol import Exp2DownstreamInterface
from ..representation import ConsequenceRepresentation, ScenarioRepresentation
from ..variants import EXP2_VARIANT_REGISTRY
from .artifact_loader import Exp2LoadedArtifacts
from .execution_manifest import (
    ExecutionReadinessStatus,
    Exp2ExecutionManifest,
    validate_variant_manifests,
)


M3Executor = Callable[..., Iterable[ActionEvaluationEnvelope]]
M4Evaluator = Callable[..., Iterable[RiskEvaluationEnvelope]]


def _callable_identity(value: Callable[..., Any]) -> str:
    module = getattr(value, "__module__", type(value).__module__)
    name = getattr(value, "__qualname__", type(value).__qualname__)
    return f"{module}:{name}"


class Exp2DownstreamExecutor(Exp2DownstreamInterface):
    """One M3 executor and one M4 evaluator shared by all Exp2 variants.

    The supplied callables must already be bound to human-approved scientific
    objects. This adapter checks identities; it never selects parameters.
    """

    def __init__(
        self,
        *,
        manifest: Exp2ExecutionManifest,
        artifacts: Exp2LoadedArtifacts,
        m3_executor: M3Executor,
        m4_evaluator: M4Evaluator,
    ):
        if not isinstance(manifest, Exp2ExecutionManifest):
            raise TypeError("EXP2_EXECUTION_MANIFEST_REQUIRED")
        if not isinstance(artifacts, Exp2LoadedArtifacts):
            raise TypeError("EXP2_LOADED_ARTIFACTS_REQUIRED")
        if artifacts.status is not ExecutionReadinessStatus.READY:
            raise ValueError("EXP2_DOWNSTREAM_ARTIFACTS_NOT_READY")
        if not callable(m3_executor) or not callable(m4_evaluator):
            raise TypeError("EXP2_DOWNSTREAM_CALLABLES_REQUIRED")
        expected = (
            (manifest.m1_artifact, artifacts.m1.reference),
            (manifest.m2_artifact, artifacts.m2.reference),
            (manifest.m3_artifact, artifacts.m3.reference),
            (manifest.m4_artifact, artifacts.m4.reference),
        )
        if any(left != right for left, right in expected):
            raise ValueError("EXP2_DOWNSTREAM_MANIFEST_ARTIFACT_IDENTITY_MISMATCH")
        self.manifest = manifest
        self.artifacts = artifacts
        self._m3_executor = m3_executor
        self._m4_evaluator = m4_evaluator
        self._response_rule_identity: tuple[tuple[str, str], ...] | None = None

    @property
    def status(self) -> ExecutionReadinessStatus:
        return ExecutionReadinessStatus.READY

    @property
    def m3_executor_identity(self) -> str:
        return _callable_identity(self._m3_executor)

    @property
    def m4_evaluator_identity(self) -> str:
        return _callable_identity(self._m4_evaluator)

    @property
    def binding_hash(self) -> str:
        return content_id({
            "fixed_manifest_identity": tuple(
                item.model_dump(mode="json")
                if hasattr(item, "model_dump")
                else item
                for item in self.manifest.fixed_binding_identity
            ),
            "action_ids": self.artifacts.m3.action_ids,
            "action_registry_hash": self.artifacts.m3.action_registry_hash,
            "response_registry_hash": self.artifacts.m3.response_registry_hash,
            "monetary_mapping_hash": self.artifacts.m4.monetary_mapping_hash,
            "risk_policy_hash": self.artifacts.m4.risk_policy_hash,
            "m3_executor_identity": self.m3_executor_identity,
            "m4_evaluator_identity": self.m4_evaluator_identity,
        })

    def assert_variant_manifests(
        self, manifests: tuple[Exp2ExecutionManifest, ...]
    ) -> None:
        validate_variant_manifests(manifests)
        for manifest in manifests:
            self.manifest.assert_variant_compatible(manifest)

    def _validate_representation_sources(
        self,
        scenarios: ScenarioRepresentation,
        consequences: ConsequenceRepresentation,
    ) -> None:
        if not isinstance(scenarios, ScenarioRepresentation):
            raise TypeError("EXP2_SCENARIO_REPRESENTATION_REQUIRED")
        if not isinstance(consequences, ConsequenceRepresentation):
            raise TypeError("EXP2_CONSEQUENCE_REPRESENTATION_REQUIRED")
        if scenarios.source_scenario_hash != self.artifacts.m1.scenario_hash:
            raise ValueError("EXP2_VARIANT_M1_ARTIFACT_CHANGED")
        if consequences.source_artifact_hash != self.artifacts.m2.consequence_hash:
            raise ValueError("EXP2_VARIANT_M2_ARTIFACT_CHANGED")
        if scenarios.artifact_version != self.artifacts.m1.reference.artifact_version:
            raise ValueError("EXP2_VARIANT_M1_VERSION_CHANGED")
        if consequences.artifact_version != self.artifacts.m2.reference.artifact_version:
            raise ValueError("EXP2_VARIANT_M2_VERSION_CHANGED")

    def run_m3(
        self,
        *,
        variant_id: str,
        scenarios: ScenarioRepresentation,
        consequences: ConsequenceRepresentation,
    ) -> tuple[ActionEvaluationEnvelope, ...]:
        EXP2_VARIANT_REGISTRY.get(variant_id)
        self._validate_representation_sources(scenarios, consequences)
        outputs = tuple(self._m3_executor(
            variant_id=variant_id,
            scenarios=scenarios,
            consequences=consequences,
            m3_artifact=self.artifacts.m3,
        ))
        if any(not isinstance(item, ActionEvaluationEnvelope) for item in outputs):
            raise TypeError("EXP2_M3_ACTION_EVALUATION_ENVELOPE_REQUIRED")
        if tuple(item.action_id for item in outputs) != self.artifacts.m3.action_ids:
            raise ValueError("EXP2_VARIANT_ACTION_SET_CHANGED")
        rule_identity = tuple(
            (item.action_id, item.response_rule.rule_hash) for item in outputs
        )
        if self._response_rule_identity is None:
            self._response_rule_identity = rule_identity
        elif rule_identity != self._response_rule_identity:
            raise ValueError("EXP2_VARIANT_RESPONSE_RULE_CHANGED")
        return outputs

    def run_m4(
        self,
        *,
        variant_id: str,
        m3_envelopes: tuple[ActionEvaluationEnvelope, ...],
    ) -> tuple[RiskEvaluationEnvelope, ...]:
        EXP2_VARIANT_REGISTRY.get(variant_id)
        if any(not isinstance(item, ActionEvaluationEnvelope) for item in m3_envelopes):
            raise TypeError("EXP2_M3_ACTION_EVALUATION_ENVELOPE_REQUIRED")
        if tuple(item.action_id for item in m3_envelopes) != self.artifacts.m3.action_ids:
            raise ValueError("EXP2_VARIANT_ACTION_SET_CHANGED")
        outputs = tuple(self._m4_evaluator(
            variant_id=variant_id,
            m3_envelopes=m3_envelopes,
            m4_artifact=self.artifacts.m4,
        ))
        if any(not isinstance(item, RiskEvaluationEnvelope) for item in outputs):
            raise TypeError("EXP2_M4_RISK_EVALUATION_ENVELOPE_REQUIRED")
        if tuple(item.action_id for item in outputs) != self.artifacts.m3.action_ids:
            raise ValueError("EXP2_VARIANT_ACTION_SET_CHANGED")
        if any(
            item.monetary_mapping_registry_hash
            != self.artifacts.m4.monetary_mapping_hash
            for item in outputs
        ):
            raise ValueError("EXP2_VARIANT_MONETARY_MAPPING_CHANGED")
        if any(
            item.risk_policy_hash != self.artifacts.m4.risk_policy_hash
            for item in outputs
        ):
            raise ValueError("EXP2_VARIANT_RISK_POLICY_CHANGED")
        m3_hashes = {item.action_id: item.envelope_hash for item in m3_envelopes}
        if any(item.m3_envelope_hash != m3_hashes[item.action_id] for item in outputs):
            raise ValueError("EXP2_M4_DID_NOT_CONSUME_BOUND_M3_OUTPUT")
        return outputs


__all__ = [
    "Exp2DownstreamExecutor",
    "M3Executor",
    "M4Evaluator",
]
