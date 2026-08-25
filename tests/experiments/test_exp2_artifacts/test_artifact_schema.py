import pytest
from pydantic import ValidationError

from exp.exp2.artifacts.artifact_schema import (
    ArtifactSupportStatus,
    Exp2ActionManifest,
    Exp2MonetaryMappingBundle,
    Exp2ResponseBundle,
    Exp2RiskPolicyBundle,
)
from model.common.identity import content_id


def test_action_manifest_requires_a00_two_actions_and_deterministic_order(
    valid_action_manifest,
):
    restored = Exp2ActionManifest.model_validate_json(
        valid_action_manifest.model_dump_json()
    )
    assert restored == valid_action_manifest
    assert restored.manifest_hash.startswith("sha256:")

    missing_a00 = valid_action_manifest.model_dump(mode="python")
    missing_a00["action_ids"] = ("A11", "A13")
    with pytest.raises(ValidationError, match="A00_REQUIRED"):
        Exp2ActionManifest.model_validate(missing_a00)

    one_action = valid_action_manifest.model_dump(mode="python")
    one_action["action_ids"] = ("A00",)
    with pytest.raises(ValidationError, match="at least 2|NON_A00_REQUIRED"):
        Exp2ActionManifest.model_validate(one_action)

    nondeterministic = valid_action_manifest.model_dump(mode="python")
    nondeterministic["action_ids"] = ("A00", "A13", "A11")
    with pytest.raises(ValidationError, match="ORDER_NOT_DETERMINISTIC"):
        Exp2ActionManifest.model_validate(nondeterministic)


@pytest.mark.parametrize(
    ("fixture_name", "model_type", "hash_field", "error"),
    (
        ("valid_responses", Exp2ResponseBundle, "rule_hash", "RULE_HASH_MISMATCH"),
        ("valid_mapping", Exp2MonetaryMappingBundle, "hash", "MAPPING_HASH_MISMATCH"),
        ("valid_risk_policy", Exp2RiskPolicyBundle, "hash", "RISK_POLICY_HASH_MISMATCH"),
    ),
)
def test_content_hashes_are_validated(
    request, fixture_name, model_type, hash_field, error
):
    item = request.getfixturevalue(fixture_name)
    if fixture_name == "valid_responses":
        item = item[1]
    payload = item.model_dump(mode="python")
    payload[hash_field] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match=error):
        model_type.model_validate(payload)


def test_mapping_rejects_test_only_fallback_and_incomplete_coverage(valid_mapping):
    payload = valid_mapping.model_dump(mode="python", exclude={"hash"})

    test_only = {**payload, "support_status": ArtifactSupportStatus.TEST_ONLY}
    test_only["hash"] = content_id(test_only)
    with pytest.raises(ValidationError, match="TEST_ONLY_MAPPING_FORBIDDEN"):
        Exp2MonetaryMappingBundle.model_validate(test_only)

    fallback = {
        **payload,
        "mapping_function_reference": {
            **payload["mapping_function_reference"],
            "F_continuity": "FALLBACK_MAPPING",
        },
    }
    fallback["hash"] = content_id(fallback)
    with pytest.raises(ValidationError, match="FALLBACK_MAPPING_FORBIDDEN"):
        Exp2MonetaryMappingBundle.model_validate(fallback)

    incomplete = {
        **payload,
        "component_ids": payload["component_ids"][:-1],
    }
    incomplete["hash"] = content_id(incomplete)
    with pytest.raises(ValidationError, match="EXACT_COMPONENT_COVERAGE_REQUIRED"):
        Exp2MonetaryMappingBundle.model_validate(incomplete)

    wrong_interpretation = {
        **payload,
        "interpretation": "RMB",
    }
    wrong_interpretation["hash"] = content_id(wrong_interpretation)
    with pytest.raises(ValidationError, match="CONSTRUCTED_INTERNAL_LOSS_UNIT"):
        Exp2MonetaryMappingBundle.model_validate(wrong_interpretation)


def test_risk_policy_has_no_implicit_alpha_or_defaults(valid_risk_policy):
    payload = valid_risk_policy.model_dump(mode="python", exclude={"hash"})
    del payload["parameters"]["alpha"]
    payload["hash"] = content_id(payload)
    with pytest.raises(ValidationError, match="RISK_PARAMETERS_INCOMPLETE"):
        Exp2RiskPolicyBundle.model_validate(payload)

    payload = valid_risk_policy.model_dump(mode="python", exclude={"hash"})
    payload["tail_policy"] = "DEFAULT"
    payload["hash"] = content_id(payload)
    with pytest.raises(ValidationError, match="IMPLICIT_RISK_POLICY_FORBIDDEN"):
        Exp2RiskPolicyBundle.model_validate(payload)
