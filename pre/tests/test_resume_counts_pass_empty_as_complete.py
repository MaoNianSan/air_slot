from __future__ import annotations

from src.core.resume_contract import select_compatible_staging
from src.core.writer import begin_staging
from src.input import write_json
from test_staging_resume_contract import _contract


def test_resume_counts_pass_empty_as_complete_for_both_datasets(tmp_path) -> None:
    output = tmp_path / "AIR_CHAIN_CORE_V2"
    contract = _contract()
    staging = begin_staging(output, resume=True, resume_contract=contract)
    key = contract.expected_partitions[0]
    for dataset, manifest_name in (
        ("observations", "observation_partition_manifest.json"),
        ("observation_membership", "observation_membership_partition_manifest.json"),
    ):
        write_json(
            {"partitions": {key: {"status": "PASS_EMPTY"}}},
            staging / dataset / manifest_name,
        )
    selected, audit = select_compatible_staging(output, contract)
    assert selected == staging
    accepted = audit["accepted"][0]
    assert accepted["complete_partitions"] == 2
    assert accepted["pass_empty"] == 2
    assert accepted["missing_partitions"] == []
