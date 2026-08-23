"""Stable public facade for the fail-closed frozen artifact loader."""

from exp.common.frozen_artifact_loader import (  # noqa: F401
    FrozenDevelopmentBinding,
    load_current_development_binding,
)

__all__ = ["FrozenDevelopmentBinding", "load_current_development_binding"]
