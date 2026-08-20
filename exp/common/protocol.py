"""Abstract lifecycle for future experiment protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .result_schema import ExperimentResult


class ExperimentProtocol(ABC):
    """Four-stage protocol interface with no scientific implementation."""

    @abstractmethod
    def prepare(self, context: Any) -> Any:
        """Validate inputs and prepare immutable protocol state."""

    @abstractmethod
    def run(self, prepared: Any) -> Any:
        """Execute a concrete protocol supplied by a future experiment."""

    @abstractmethod
    def evaluate(self, execution: Any) -> Any:
        """Evaluate execution output through a registered evaluation suite."""

    @abstractmethod
    def report(self, evaluation: Any) -> ExperimentResult:
        """Return one provenance-complete common result."""


__all__ = ["ExperimentProtocol"]

