"""Canonical M1 model ownership namespace.

The historical ``model.py`` path remains a compatibility facade because the
sealed V1 runtime manifest names that file explicitly.
"""

from .gru import M1V2GRU, OrderedEventGRU

__all__ = ["M1V2GRU", "OrderedEventGRU"]
