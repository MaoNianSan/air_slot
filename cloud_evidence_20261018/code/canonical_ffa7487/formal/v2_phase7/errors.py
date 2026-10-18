"""Typed failures used by the Phase-7 runner."""

from __future__ import annotations

from typing import Any


class Phase7Error(RuntimeError):
    """Base error for the Phase-7 runner."""


class TypedBlocker(Phase7Error):
    """A fail-closed Phase-7 blocker with a stable code."""

    def __init__(self, code: str, detail: Any = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail is not None else code)


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise TypedBlocker(code, detail)


__all__ = ["Phase7Error", "TypedBlocker", "_require"]
