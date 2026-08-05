from __future__ import annotations

import json
from pathlib import Path

from src.core.contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
    ResumeContract,
)
from src.pipeline_config import load_config


def test_contract_identity_has_one_code_authority() -> None:
    cfg = load_config(mode="fast")
    schema = cfg["core_schema"]
    assert schema["contract_id"] == CONTRACT_ID
    assert schema["schema_version"] == SCHEMA_VERSION
    assert schema["research_code_revision"] == RESEARCH_CODE_REVISION

    source_root = Path(__file__).resolve().parents[1] / "src"
    authority = source_root / "core" / "contracts.py"
    for path in source_root.rglob("*.py"):
        if path == authority:
            continue
        text = path.read_text(encoding="utf-8")
        assert CONTRACT_ID not in text, path
        assert SCHEMA_VERSION not in text, path
        assert RESEARCH_CODE_REVISION not in text, path


def test_resume_and_published_status_use_authoritative_identity() -> None:
    contract = ResumeContract(
        contract_id=CONTRACT_ID,
        schema_version=SCHEMA_VERSION,
        research_code_revision=RESEARCH_CODE_REVISION,
        frozen_config_hash="a" * 64,
        source_manifest_hash="b" * 64,
        source_schema_hash="c" * 64,
        request_contract_hash="d" * 64,
        request_rows_hash="e" * 64,
        episode_interval_hash="f" * 64,
        cache_key="1" * 64,
        expected_partitions=(),
    )
    assert contract.as_dict()["contract_id"] == CONTRACT_ID

    status_path = (
        Path(__file__).resolve().parents[1]
        / "reports"
        / "published"
        / "core_v2"
        / "PRE_CORE_V2_STATUS.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["contract_id"] == CONTRACT_ID
    assert status["schema_version"] == SCHEMA_VERSION
    assert status["research_code_revision"] == RESEARCH_CODE_REVISION
