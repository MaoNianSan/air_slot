from __future__ import annotations

from src.core.contracts import ResumeContract
from src.core.resume_contract import read_resume_manifest, select_compatible_staging
from src.core.writer import begin_staging


def _contract() -> ResumeContract:
    return ResumeContract(
        contract_id="AIR_CHAIN_CORE_V2",
        schema_version="air-chain-core-2.0",
        research_code_revision="AIR_CHAIN_CORE_V2_R2",
        frozen_config_hash="a" * 64,
        source_manifest_hash="b" * 64,
        source_schema_hash="c" * 64,
        request_contract_hash="d" * 64,
        request_rows_hash="e" * 64,
        episode_interval_hash="f" * 64,
        implementation_hash="3" * 64,
        implementation_hash_status="PASS",
        implementation_file_count=3,
        git_commit="1" * 40,
        cache_key="4" * 64,
        expected_partitions=("source=state/observation_date=2022-05-02",),
    )


def test_staging_resume_requires_exact_contract(tmp_path) -> None:
    output = tmp_path / "AIR_CHAIN_CORE_V2"
    contract = _contract()
    staging = begin_staging(output, resume=True, resume_contract=contract)
    assert read_resume_manifest(staging) == contract
    selected, audit = select_compatible_staging(output, contract)
    assert selected == staging
    assert audit["rejected"] == []
