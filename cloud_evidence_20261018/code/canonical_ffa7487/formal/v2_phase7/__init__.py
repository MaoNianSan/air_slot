"""Responsibility-split implementation of the Phase-7 Final-Test runner."""

from __future__ import annotations

from .gate_b0 import run_gate_b0_binding_audit
from .execution_freeze import (
    FREEZE_JSON_PATH,
    FREEZE_MD_PATH,
    PRE_OPEN_REPORT_PATH,
    build_execution_freeze,
    pre_open_gate,
    validate_execution_freeze,
    write_execution_freeze,
)
from .gate_b import production_binding_record, production_pipeline
from .cli import main
from .gate_a import run_gate_a
from .gate_b import execute_gate_b

__all__ = [
    "FREEZE_JSON_PATH",
    "FREEZE_MD_PATH",
    "PRE_OPEN_REPORT_PATH",
    "build_execution_freeze",
    "execute_gate_b",
    "main",
    "pre_open_gate",
    "production_binding_record",
    "production_pipeline",
    "run_gate_a",
    "run_gate_b0_binding_audit",
    "validate_execution_freeze",
    "write_execution_freeze",
]
