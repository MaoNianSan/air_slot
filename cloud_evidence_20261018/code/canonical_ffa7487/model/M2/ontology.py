"""Canonical M2 consequence component ontology."""

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS

# Historical M2 callers use COMPONENTS; keep that alias in the M2 owner.
COMPONENTS = CONSEQUENCE_COMPONENTS

__all__ = ["COMPONENTS", "CONSEQUENCE_COMPONENTS"]
