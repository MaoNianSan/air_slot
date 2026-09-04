"""Canonical cross-module evidence classification."""

from __future__ import annotations

from .enums import EvidenceClass


_EVIDENCE_RANK = {
    EvidenceClass.DIRECT: 0,
    EvidenceClass.DERIVED: 1,
    EvidenceClass.DOMAIN_PROXY: 2,
    EvidenceClass.EMPIRICAL_REFERENCE: 2,
    EvidenceClass.EXTERNAL_STANDARD: 2,
    EvidenceClass.SCENARIO_PARAMETER: 3,
    EvidenceClass.UNSUPPORTED: 4,
}


def weaker_or_equal(value: EvidenceClass, ceiling: EvidenceClass) -> bool:
    """Return whether value is no stronger than its declared ceiling."""
    return _EVIDENCE_RANK[value] >= _EVIDENCE_RANK[ceiling]


__all__ = ["EvidenceClass", "weaker_or_equal"]
