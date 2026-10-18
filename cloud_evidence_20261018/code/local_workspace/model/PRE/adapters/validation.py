from model.common.errors import ContractError
from .base import DatasetAdapter


def validate_adapter_interface(adapter: DatasetAdapter, registered_families: set[str]) -> dict[str, object]:
    description = adapter.describe()
    declared = set(description.source_families)
    if not declared <= registered_families:
        raise ContractError("adapter declares a source family absent from registries")
    return {"dataset_instance_id": description.dataset_instance_id,
            "source_families": sorted(declared), "status": "PASS"}
