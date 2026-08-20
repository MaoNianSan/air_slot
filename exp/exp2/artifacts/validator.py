"""Fail-closed readiness gate over prepared Exp2 scientific artifacts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from exp.exp2.execution.artifact_loader import LoadedM1Artifact, LoadedM2Artifact
from exp.exp2.execution.execution_manifest import ArtifactKind

from .artifact_schema import (
    ArtifactSupportStatus,
    Exp2ActionManifest,
    Exp2MonetaryMappingBundle,
    Exp2ResponseBundle,
    Exp2ResponseSupport,
    Exp2RiskPolicyBundle,
)


class Exp2ExecutionGateStatus(str, Enum):
    READY = "READY"
    BLOCKED_MISSING_ARTIFACT = "BLOCKED_MISSING_ARTIFACT"
    BLOCKED_UNSUPPORTED_MAPPING = "BLOCKED_UNSUPPORTED_MAPPING"
    BLOCKED_UNSUPPORTED_RESPONSE = "BLOCKED_UNSUPPORTED_RESPONSE"


class Exp2ExecutionGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Exp2ExecutionGateStatus
    reason_codes: tuple[str, ...]
    scientific_scope: str = "SCENARIO_CONDITIONED_REPRESENTATION_SENSITIVITY"
    ranking_scope: str = "CONDITIONAL_NON_AUTHORITATIVE"


class Exp2ExecutionGate:
    """Validate complete prepared bundles without synthesizing any value."""

    @staticmethod
    def _result(
        status: Exp2ExecutionGateStatus, *reason_codes: str
    ) -> Exp2ExecutionGateResult:
        return Exp2ExecutionGateResult(
            status=status,
            reason_codes=tuple(reason_codes),
        )

    def validate(
        self,
        *,
        m1_artifact: LoadedM1Artifact | dict[str, Any] | None,
        m2_artifact: LoadedM2Artifact | dict[str, Any] | None,
        action_manifest: Exp2ActionManifest | dict[str, Any] | None,
        response_bundles: tuple[Exp2ResponseBundle | dict[str, Any], ...] | None,
        monetary_mapping: Exp2MonetaryMappingBundle | dict[str, Any] | None,
        risk_policy: Exp2RiskPolicyBundle | dict[str, Any] | None,
    ) -> Exp2ExecutionGateResult:
        missing = tuple(
            name
            for name, value in (
                ("M1", m1_artifact),
                ("M2", m2_artifact),
                ("M3_ACTION_MANIFEST", action_manifest),
                (
                    "M3_RESPONSE_BUNDLE",
                    response_bundles if response_bundles else None,
                ),
                ("M4_MAPPING", monetary_mapping),
                ("M4_RISK_POLICY", risk_policy),
            )
            if value is None
        )
        if missing:
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_MISSING_ARTIFACT,
                *(f"MISSING:{name}" for name in missing),
            )

        try:
            loaded_m1 = LoadedM1Artifact.model_validate(m1_artifact)
            loaded_m2 = LoadedM2Artifact.model_validate(m2_artifact)
        except (TypeError, ValueError):
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_MISSING_ARTIFACT,
                "M1_OR_M2_ARTIFACT_NOT_LOADER_VALIDATED",
            )
        if (
            loaded_m1.reference.artifact_kind is not ArtifactKind.M1
            or loaded_m2.reference.artifact_kind is not ArtifactKind.M2
        ):
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_MISSING_ARTIFACT,
                "M1_OR_M2_ARTIFACT_KIND_MISMATCH",
            )

        try:
            manifest = Exp2ActionManifest.model_validate(action_manifest)
            responses = tuple(
                Exp2ResponseBundle.model_validate(bundle)
                for bundle in response_bundles or ()
            )
        except (TypeError, ValueError) as exc:
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE,
                f"M3_ARTIFACT_INVALID:{type(exc).__name__}",
            )
        response_ids = tuple(bundle.action_id for bundle in responses)
        if response_ids != manifest.action_ids:
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE,
                "M3_RESPONSE_ACTION_ORDER_OR_COVERAGE_MISMATCH",
            )
        if any(
            bundle.support_class is Exp2ResponseSupport.ABSTAIN
            for bundle in responses
        ):
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE,
                "M3_RESPONSE_ABSTAIN_IN_COMPARISON_SET",
            )
        if any(
            bundle.action_id != "A00"
            and bundle.support_class is not Exp2ResponseSupport.SCENARIO_ASSUMPTION
            for bundle in responses
        ):
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE,
                "M3_RESPONSE_OUTSIDE_FROZEN_SCENARIO_ASSUMPTION_SCOPE",
            )

        try:
            mapping = Exp2MonetaryMappingBundle.model_validate(monetary_mapping)
            policy = Exp2RiskPolicyBundle.model_validate(risk_policy)
        except (TypeError, ValueError) as exc:
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_MAPPING,
                f"M4_ARTIFACT_INVALID:{type(exc).__name__}",
            )
        if mapping.support_status is not ArtifactSupportStatus.FROZEN:
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_MAPPING,
                f"M4_MAPPING_NOT_FROZEN:{mapping.support_status.value}",
            )
        if policy.support_status is not ArtifactSupportStatus.FROZEN:
            return self._result(
                Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_MAPPING,
                f"M4_RISK_POLICY_NOT_FROZEN:{policy.support_status.value}",
            )

        return self._result(Exp2ExecutionGateStatus.READY, "ALL_ARTIFACT_GATES_PASS")


__all__ = [
    "Exp2ExecutionGate",
    "Exp2ExecutionGateResult",
    "Exp2ExecutionGateStatus",
]
