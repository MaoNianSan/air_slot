from exp.exp2.artifacts.artifact_schema import (
    ArtifactSupportStatus,
    Exp2MonetaryMappingBundle,
    Exp2ResponseBundle,
    Exp2ResponseSource,
    Exp2ResponseSupport,
)
from exp.exp2.artifacts.validator import (
    Exp2ExecutionGate,
    Exp2ExecutionGateStatus,
)
from model.common.identity import content_id


def _rehash(model_type, item, **updates):
    payload = item.model_dump(mode="python", exclude={"hash", "rule_hash"})
    payload.update(updates)
    hash_field = "rule_hash" if model_type is Exp2ResponseBundle else "hash"
    return model_type(**payload, **{hash_field: content_id(payload)})


def test_complete_conditional_bundle_is_engineering_ready(valid_gate_inputs):
    result = Exp2ExecutionGate().validate(**valid_gate_inputs)

    assert result.status is Exp2ExecutionGateStatus.READY
    assert result.scientific_scope == "SCENARIO_CONDITIONED_REPRESENTATION_SENSITIVITY"
    assert result.ranking_scope == "CONDITIONAL_NON_AUTHORITATIVE"


def test_missing_artifact_returns_explicit_blocked_status(valid_gate_inputs):
    inputs = {**valid_gate_inputs, "m1_artifact": None}
    result = Exp2ExecutionGate().validate(**inputs)

    assert result.status is Exp2ExecutionGateStatus.BLOCKED_MISSING_ARTIFACT
    assert "MISSING:M1" in result.reason_codes

    result = Exp2ExecutionGate().validate(
        **{**valid_gate_inputs, "response_bundles": ()}
    )
    assert result.status is Exp2ExecutionGateStatus.BLOCKED_MISSING_ARTIFACT
    assert "MISSING:M3_RESPONSE_BUNDLE" in result.reason_codes


def test_abstain_or_scope_upgrade_is_blocked_as_unsupported_response(
    valid_gate_inputs,
):
    responses = valid_gate_inputs["response_bundles"]
    abstain = _rehash(
        Exp2ResponseBundle,
        responses[1],
        support_class=Exp2ResponseSupport.ABSTAIN,
        source_type=Exp2ResponseSource.SCENARIO_ASSUMPTION,
    )
    result = Exp2ExecutionGate().validate(
        **{**valid_gate_inputs, "response_bundles": (responses[0], abstain)}
    )
    assert result.status is Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE

    supported = _rehash(
        Exp2ResponseBundle,
        responses[1],
        support_class=Exp2ResponseSupport.SUPPORTED,
        source_type=Exp2ResponseSource.OPERATIONAL_RULE,
    )
    result = Exp2ExecutionGate().validate(
        **{**valid_gate_inputs, "response_bundles": (responses[0], supported)}
    )
    assert result.status is Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE
    assert "M3_RESPONSE_OUTSIDE_FROZEN_SCENARIO_ASSUMPTION_SCOPE" in result.reason_codes


def test_unfrozen_mapping_returns_unsupported_mapping(valid_gate_inputs):
    mapping = _rehash(
        Exp2MonetaryMappingBundle,
        valid_gate_inputs["monetary_mapping"],
        support_status=ArtifactSupportStatus.NOT_FROZEN,
    )
    result = Exp2ExecutionGate().validate(
        **{**valid_gate_inputs, "monetary_mapping": mapping}
    )

    assert result.status is Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_MAPPING
    assert "M4_MAPPING_NOT_FROZEN:NOT_FROZEN" in result.reason_codes


def test_response_bundle_must_match_manifest_order_and_coverage(valid_gate_inputs):
    responses = valid_gate_inputs["response_bundles"]
    result = Exp2ExecutionGate().validate(
        **{**valid_gate_inputs, "response_bundles": tuple(reversed(responses))}
    )

    assert result.status is Exp2ExecutionGateStatus.BLOCKED_UNSUPPORTED_RESPONSE
    assert "M3_RESPONSE_ACTION_ORDER_OR_COVERAGE_MISMATCH" in result.reason_codes
