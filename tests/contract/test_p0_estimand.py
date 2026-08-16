import pytest
from pydantic import ValidationError

from model.common.estimand import ConsequenceScope, DecisionDomain, ScopeStatus


def test_scope_is_local_episode_versioned_and_hash_verified():
    scope = ConsequenceScope.create(
        estimand_id="LOCAL-FLIGHT",
        estimand_version="1.0.0",
        included_components=("F_execution",),
        aggregation_rule_id="SUM-V1",
        valuation_registry_id="VALUATION-V1",
        material_coverage_contract_id="COVERAGE-V1",
        scope_status=ScopeStatus.FORMAL_READY,
    )
    assert scope.decision_domain is DecisionDomain.LOCAL_EPISODE
    assert scope.scope_hash.startswith("sha256:")
    with pytest.raises(ValidationError, match="CONSEQUENCE_SCOPE_HASH_MISMATCH"):
        ConsequenceScope(**{**scope.model_dump(), "scope_hash": "sha256:" + "0" * 64})


def test_global_and_airline_network_are_not_scientific_domain_types():
    assert tuple(item.value for item in DecisionDomain) == ("LOCAL_EPISODE",)
    with pytest.raises(ValueError):
        DecisionDomain("GLOBAL")
    with pytest.raises(ValueError):
        DecisionDomain("AIRLINE_NETWORK")
