"""Declarative variant registry without experiment-specific dispatch logic."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VariantDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    changed_factor: str = Field(min_length=1)
    fixed_factor: tuple[str, ...] = Field(min_length=1)
    allowed_metrics: tuple[str, ...] = Field(min_length=1)
    claim_scope: str = Field(min_length=1)

    @model_validator(mode="after")
    def definition_is_consistent(self):
        if self.changed_factor in self.fixed_factor:
            raise ValueError("VARIANT_CHANGED_FACTOR_DECLARED_FIXED")
        if len(set(self.fixed_factor)) != len(self.fixed_factor):
            raise ValueError("VARIANT_FIXED_FACTOR_DUPLICATE")
        if len(set(self.allowed_metrics)) != len(self.allowed_metrics):
            raise ValueError("VARIANT_ALLOWED_METRIC_DUPLICATE")
        return self


class VariantRegistry:
    """In-memory registry for variant metadata only.

    A registered definition has no transformation callback. Concrete protocol
    packages must implement their variants outside ``exp.common``.
    """

    def __init__(self, definitions: Iterable[VariantDefinition] = ()):
        self._definitions: dict[str, VariantDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: VariantDefinition) -> VariantDefinition:
        if not isinstance(definition, VariantDefinition):
            raise TypeError("VARIANT_DEFINITION_TYPE_REQUIRED")
        if definition.variant_id in self._definitions:
            raise ValueError(f"VARIANT_ID_ALREADY_REGISTERED:{definition.variant_id}")
        self._definitions[definition.variant_id] = definition
        return definition

    def get(self, variant_id: str) -> VariantDefinition:
        try:
            return self._definitions[variant_id]
        except KeyError as exc:
            raise KeyError(f"VARIANT_ID_NOT_REGISTERED:{variant_id}") from exc

    def definitions(self) -> tuple[VariantDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def variant_ids(self) -> tuple[str, ...]:
        return tuple(definition.variant_id for definition in self.definitions())

    def validate_metric(self, variant_id: str, metric_id: str) -> None:
        definition = self.get(variant_id)
        if metric_id not in definition.allowed_metrics:
            raise ValueError(
                f"VARIANT_METRIC_NOT_ALLOWED:{variant_id}:{metric_id}"
            )

    def validate_metric_catalog(self, metric_ids: Iterable[str]) -> None:
        available = set(metric_ids)
        missing = sorted({
            metric_id
            for definition in self._definitions.values()
            for metric_id in definition.allowed_metrics
            if metric_id not in available
        })
        if missing:
            raise ValueError("VARIANT_METRIC_NOT_REGISTERED:" + ",".join(missing))

    def __contains__(self, variant_id: object) -> bool:
        return variant_id in self._definitions

    def __len__(self) -> int:
        return len(self._definitions)


__all__ = ["VariantDefinition", "VariantRegistry"]

