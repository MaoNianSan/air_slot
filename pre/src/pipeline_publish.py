"""Compatibility facade for legacy PRE publication helpers."""

from .artifact_registry import (
    _artifact_registry,
    _output_hashes,
    _validate_published_target_metadata,
)
from .bundle_writer import _publish, _write_bundle, _write_fast_manifest
from .contract_enrichment import _enrich_contract

__all__ = [
    "_artifact_registry",
    "_enrich_contract",
    "_output_hashes",
    "_publish",
    "_validate_published_target_metadata",
    "_write_bundle",
    "_write_fast_manifest",
]
