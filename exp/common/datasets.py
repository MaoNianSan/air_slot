from __future__ import annotations

from model.common.errors import ContractError


DATASET_ROLES = {
    "data2_2019": "MAIN_TEXT_PRINCIPAL",
    "data1_2019": "APPENDIX_REPLICATION",
}


def dataset_role(dataset_instance_id: str) -> str:
    try:
        return DATASET_ROLES[dataset_instance_id]
    except KeyError as exc:
        raise ContractError("EXPERIMENT_DATASET_ROLE_UNKNOWN") from exc


def assert_dataset_role(dataset_instance_id: str, declared_role: str) -> None:
    if dataset_role(dataset_instance_id) != declared_role:
        raise ContractError("DATASET_ROLE_MANIFEST_MISMATCH")
