"""Compatibility facade for the legacy snapshot pipeline."""

from .legacy_snapshot_grid import build_snapshot_grid, derive_state_requests
from .snapshot_reference_enrichment import attach_aggregate_references
from .state_feature_resolver import attach_state_features
from .state_quality import finalize_snapshot_quality

__all__ = [
    "attach_aggregate_references",
    "attach_state_features",
    "build_snapshot_grid",
    "derive_state_requests",
    "finalize_snapshot_quality",
]
