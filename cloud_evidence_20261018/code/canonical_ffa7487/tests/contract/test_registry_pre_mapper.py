from pathlib import Path

import pytest

from model.common.errors import ContractError
from model.PRE.canonical.normalization import canonicalize_metar_row
from model.PRE.mapping import RegistryPREMapper


def _weather():
    return canonicalize_metar_row({"station":"LSZH", "valid":"2019-01-01 00:20+00:00",
        "tmpf":"32", "dwpf":"23", "drct":"180", "sknt":"10", "gust":"M",
        "mslp":"M", "vsby":"10", "metar":"LSZH 010020Z 18010KT Q1013"},
        replay_lag_minutes=5)


def test_mapper_uses_registry_not_caller_metadata():
    mapped = RegistryPREMapper.from_path(Path("registries")).map_record(_weather())
    assert mapped.scientific_variable == "current_weather"
    assert mapped.pre_family == "current_state"
    assert mapped.value.evidence_class.value == "DERIVED"
    assert mapped.value.support_ceiling.value == "DIRECT"
    assert mapped.value.value["mslp_hpa"] is None
    assert "mslp_hpa" != mapped.scientific_variable


def test_unknown_rule_and_role_contradiction_fail_explicitly():
    mapper = RegistryPREMapper.from_path(Path("registries"))
    with pytest.raises(ContractError, match="UNKNOWN_REGISTRY_RULE"):
        mapper.map_record(_weather().model_copy(update={"provenance_rule_id":"UNKNOWN"}))
    with pytest.raises(ContractError, match="REGISTRY_DECISION_ROLE_CONTRADICTION"):
        mapper.map_record(_weather().model_copy(update={"decision_time_role":"FROZEN_REFERENCE"}))
