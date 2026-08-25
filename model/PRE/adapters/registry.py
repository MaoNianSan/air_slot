from pathlib import Path
from typing import Literal
import yaml
from pydantic import Field, model_validator

from model.common.errors import ContractError
from model.common.value_objects import FrozenModel
from model.PRE.feature_registry.models import ColumnRole


class SourceAdapterDefinition(FrozenModel):
    adapter_id: str
    version: str
    dataset_instance_id: Literal["data1_2019", "data2_2019"]
    source_family: str
    relative_globs: tuple[str, ...]
    format: Literal["csv", "csv_gzip", "csv_tar", "json_stat", "parquet"]
    canonical_object: str
    canonical_objects: tuple[str, ...] = ()
    required_columns: tuple[str, ...]
    projected_columns: tuple[str, ...]
    optional_projected_columns: tuple[str, ...] = ()
    column_roles: dict[str, ColumnRole] = {}
    rule_ids: tuple[str, ...]
    decision_time_role: str
    availability_basis: str

    @model_validator(mode="after")
    def canonical_types_include_primary(self):
        if (
            self.canonical_objects
            and self.canonical_object not in self.canonical_objects
        ):
            raise ValueError("primary canonical object missing from canonical_objects")
        if not set(self.optional_projected_columns) <= set(self.projected_columns):
            raise ValueError("optional projected column is not projected")
        declared = set(self.required_columns) | set(self.projected_columns)
        if not set(self.column_roles) <= declared:
            raise ValueError("column role references undeclared source column")
        return self


class SourceAdapterRegistry(FrozenModel):
    schema_version: str
    sources: tuple[SourceAdapterDefinition, ...]

    @classmethod
    def load(cls, path: Path) -> "SourceAdapterRegistry":
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def get(
        self, dataset_instance_id: str, source_family: str
    ) -> SourceAdapterDefinition:
        matches = [
            item
            for item in self.sources
            if item.dataset_instance_id == dataset_instance_id
            and item.source_family == source_family
        ]
        if len(matches) != 1:
            raise ContractError("SOURCE_ADAPTER_NOT_REGISTERED")
        return matches[0]


class RawReadRequest(FrozenModel):
    dataset_instance_id: Literal["data1_2019", "data2_2019"]
    source_family: str
    raw_root: Path
    output_root: Path
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    date: str | None = None
    max_rows: int | None = Field(default=None, gt=0)
    max_files: int | None = Field(default=None, gt=0)
    chunksize: int = Field(default=50_000, gt=0)

    @model_validator(mode="after")
    def separate_roots(self):
        raw = self.raw_root.resolve()
        output = self.output_root.resolve()
        if output == raw or raw in output.parents:
            raise ValueError("output_root must be outside raw_root")
        return self

    def resolve_source(self, relative_path: Path) -> Path:
        root = self.raw_root.resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ContractError("RAW_PATH_ESCAPE")
        return candidate
