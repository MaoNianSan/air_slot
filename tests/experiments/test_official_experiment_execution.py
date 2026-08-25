from pathlib import Path

import pytest

from exp.common.official_execution import (
    load_official_frozen_binding,
    repository_root,
    require_active_path,
    require_development_safety,
    require_hash,
)
from exp.exp1.run import main as exp1_main
from exp.exp2.run import main as exp2_main
from exp.exp3.run import main as exp3_main
from exp.exp4.run import main as exp4_main
from model.common.errors import ContractError


def test_official_frozen_binding_is_complete():
    binding = load_official_frozen_binding(repository_root())
    assert all(value.startswith("sha256:") for value in binding.as_dict().values())
    assert binding.model_hash != binding.mapping_hash


@pytest.mark.parametrize(
    "entrypoint",
    (exp1_main, exp2_main, exp3_main, exp4_main),
)
def test_official_entrypoint_check_passes(entrypoint):
    assert entrypoint(["--check"]) == 0


def test_archive_fallback_is_rejected():
    root = repository_root()
    with pytest.raises(ContractError, match="OFFICIAL_ARCHIVE_FALLBACK_FORBIDDEN"):
        require_active_path(root / "archive" / "old_experiments", root)


def test_missing_hash_is_rejected():
    with pytest.raises(ContractError, match="TEST_HASH_MISSING"):
        require_hash("", "TEST_HASH_MISSING")


@pytest.mark.parametrize(
    "payload,code",
    (
        ({"safety": {"FINAL_TEST_ACCESS_COUNT": 1, "PAPER_FULL_RUN": False}}, "TEST_FINAL_TEST_ACCESS_NONZERO"),
        ({"safety": {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": True}}, "TEST_PAPER_FULL_FORBIDDEN"),
        ({"safety": {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "FULL": True}}, "TEST_FULL_EXECUTION_FORBIDDEN"),
    ),
)
def test_forbidden_execution_boundaries_fail_closed(payload, code):
    with pytest.raises(ContractError, match=code):
        require_development_safety(payload, label="TEST")
