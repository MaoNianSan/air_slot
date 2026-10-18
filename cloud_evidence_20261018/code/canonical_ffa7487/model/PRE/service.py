"""PRE service facade exposing only evidence/state publication operations."""

from __future__ import annotations

from model.PRE.foundation import PREBuildRequest, PREBuildResult, build_pre_state
from model.PRE.pipeline import (
    ProductionPREPublisher,
    ProductionPRERequest,
)


class PREService:
    """Stable public PRE boundary; prediction and consequence logic are absent."""

    def __init__(self, publisher: ProductionPREPublisher | None = None):
        self._publisher = publisher

    def build(self, request: PREBuildRequest) -> PREBuildResult:
        return build_pre_state(request)

    def publish(self, request: ProductionPRERequest) -> PREBuildResult:
        publisher = self._publisher or ProductionPREPublisher.from_project()
        return publisher.publish(request)


__all__ = [
    "PREBuildRequest",
    "PREBuildResult",
    "PREService",
    "ProductionPREPublisher",
    "ProductionPRERequest",
]
