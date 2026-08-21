"""Declarative Exp1 protocol surface."""

from __future__ import annotations

from dataclasses import dataclass

from .variants import EXP1A_VARIANTS, EXP1B_VARIANTS, variant_definition


@dataclass(frozen=True)
class Exp1Protocol:
    variant_id: str

    @property
    def subexperiment(self) -> str:
        return variant_definition(self.variant_id)["subexperiment"]

    @property
    def controls(self) -> tuple[str, ...]:
        return tuple(variant_definition(self.variant_id)["fixed_factor"])

    @property
    def principal(self) -> bool:
        return self.variant_id in EXP1A_VARIANTS or self.variant_id in EXP1B_VARIANTS


__all__ = ["Exp1Protocol"]
