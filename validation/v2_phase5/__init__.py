"""Phase 5 Development families, Train support and draft freeze materialization.

The package is Development-only. It never reads or writes
``artifacts/experiment/final_test`` and keeps ``FINAL_TEST_ACCESS_COUNT``
unchanged.
"""

from __future__ import annotations

from .common import (
    PHASE_DIR,
    Authorities,
    Phase5GuardError,
    load_authorities,
    load_development_bridge,
    write_json,
)
from .families import materialize_family_a, materialize_family_b
from .freeze import build_freeze_draft, render_freeze_summary
from .h8 import materialize_h8_sensitivity
from .train_support import materialize_train_support

__all__ = [
    "PHASE_DIR",
    "Authorities",
    "Phase5GuardError",
    "build_freeze_draft",
    "load_authorities",
    "load_development_bridge",
    "materialize_family_a",
    "materialize_family_b",
    "materialize_h8_sensitivity",
    "materialize_train_support",
    "render_freeze_summary",
    "write_json",
]
