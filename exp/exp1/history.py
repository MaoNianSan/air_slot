"""Compatibility imports for the M1-owned history contract."""

from model.M1.history import (
    HistoryRepresentation,
    adaptive_history,
    current_history,
    fixed_history,
    represent_history,
)

__all__ = [
    "HistoryRepresentation",
    "adaptive_history",
    "current_history",
    "fixed_history",
    "represent_history",
]
