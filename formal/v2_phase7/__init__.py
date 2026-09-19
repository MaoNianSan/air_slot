"""Responsibility-split implementation of the Phase-7 Final-Test runner."""

from __future__ import annotations

from .cli import main
from .gate_a import run_gate_a
from .gate_b import execute_gate_b

__all__ = ["execute_gate_b", "main", "run_gate_a"]
