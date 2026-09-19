"""Responsibility-split implementation of the Phase-7 Final-Test runner."""

from __future__ import annotations

from .gate_b0 import run_gate_b0_binding_audit
from .gate_b import production_binding_record, production_pipeline
from .cli import main
from .gate_a import run_gate_a
from .gate_b import execute_gate_b

__all__ = [
    "execute_gate_b",
    "main",
    "production_binding_record",
    "production_pipeline",
    "run_gate_a",
    "run_gate_b0_binding_audit",
]
