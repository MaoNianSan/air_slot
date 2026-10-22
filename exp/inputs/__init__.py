"""Input layer: frozen cache -> canonical inputs -> typed model inputs.

This package is the preserved data-input chain for the V2 scientific line.
It is intentionally kept separate from exp.shared (analysis helpers) so that
input loading and analysis code cannot drift into each other.
"""

from __future__ import annotations

__all__: list[str] = []
