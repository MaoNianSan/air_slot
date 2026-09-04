from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable
from pydantic import field_validator, model_validator

from model.common.errors import NotImplementedByScopeError
from model.common.value_objects import FrozenModel


class AdapterDescription(FrozenModel):
    dataset_instance_id: str
    source_families: tuple[str, ...]
    cross_dataset_overlay: bool = False

    @field_validator("dataset_instance_id")
    @classmethod
    def independent_identity(cls, value: str) -> str:
        if "+" in value or value not in {"data1_2019", "data2_2019"}:
            raise ValueError("dataset instance must remain independent")
        return value

    @model_validator(mode="after")
    def overlay_off(self):
        if self.cross_dataset_overlay:
            raise ValueError("cross-dataset overlay is disabled")
        return self


class SourceValidationRequest(FrozenModel):
    source_family: str


class SourceValidationReport(FrozenModel):
    dataset_instance_id: str
    source_family: str
    status: str
    reason_code: str | None = None


class CanonicalReadRequest(FrozenModel):
    source_family: str


@runtime_checkable
class DatasetAdapter(Protocol):
    def describe(self) -> AdapterDescription: ...
    def capabilities(self) -> dict[str, str]: ...
    def validate_source(
        self, request: SourceValidationRequest
    ) -> SourceValidationReport: ...
    def iter_canonical(self, request: CanonicalReadRequest) -> Iterator[Any]: ...


class InterfaceOnlyAdapter:
    def iter_canonical(self, request: CanonicalReadRequest) -> Iterator[Any]:
        raise NotImplementedByScopeError(
            f"production raw reader is not implemented for {request.source_family}"
        )
        yield  # pragma: no cover
