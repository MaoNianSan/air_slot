"""Exp1 entrypoint placeholder for a future authorized materialized run."""

from __future__ import annotations

from .protocol import Exp1Protocol


def validate_fast_contract(*, hidden_size: int = 16) -> None:
    """Validate frozen protocol constants without reading raw data or running models."""
    protocol = Exp1Protocol(primary_hidden_size=hidden_size)
    protocol.validate()


if __name__ == "__main__":
    validate_fast_contract()
