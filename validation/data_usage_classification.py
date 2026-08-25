"""Pure classification helpers for the Data Usage contract audit."""

from __future__ import annotations

from collections.abc import Iterable

PASS_STATUSES = (
    "COVERED_ACTIVE",
    "EXPLICITLY_UNUSED",
    "DIAGNOSTIC_ONLY",
    "REFERENCE_BUILD_ONLY",
    "SOURCE_SCHEMA_METADATA",
)
FAILURE_STATUSES = (
    "PRE_BYPASS",
    "RUNTIME_USED_NO_CONTRACT",
    "AMBIGUOUS_ACTIVE_COLUMN",
    "ACTIVE_SEMANTIC_CONFLICT",
    "ACTIVE_REGISTRY_CONFLICT",
    "ACTIVE_PRE_OUTPUT_CONFLICT",
)
ALL_STATUSES = PASS_STATUSES + FAILURE_STATUSES

_ACTIVE_ROLE_MAP = {
    "COVERED_ACTIVE": "COVERED_ACTIVE",
    "RETAINED_IDENTITY": "COVERED_ACTIVE",
    "OPTIONAL_PROJECTED_METADATA": "COVERED_ACTIVE",
    "SIGNED_TIME_OFFSET": "COVERED_ACTIVE",
    "NONNEGATIVE_DELAY_REPORTING_ONLY": "COVERED_ACTIVE",
}
_PASSIVE_ROLES = {
    "EXPLICITLY_UNUSED",
    "DIAGNOSTIC_ONLY",
    "REFERENCE_BUILD_ONLY",
    "SOURCE_SCHEMA_METADATA",
}


def classify_source_column(
    *,
    declared_role: str | None,
    canonicalizer_accessed: bool,
    matched_rule_ids: Iterable[str],
    primary_rule_ids: Iterable[str],
    pre_bypass: bool,
) -> tuple[str, list[str]]:
    if pre_bypass:
        return "PRE_BYPASS", ["RAW_COLUMN_ACCESSED_DOWNSTREAM_OF_PRE"]

    matched = set(matched_rule_ids)
    primary = set(primary_rule_ids)
    if declared_role == "EXPLICITLY_UNUSED" and canonicalizer_accessed:
        return "ACTIVE_SEMANTIC_CONFLICT", ["DECLARED_UNUSED_BUT_RUNTIME_ACCESSED"]
    if declared_role in _PASSIVE_ROLES:
        return declared_role, []

    if canonicalizer_accessed:
        if not matched:
            return "RUNTIME_USED_NO_CONTRACT", ["RUNTIME_COLUMN_WITHOUT_RULE"]
        if not matched & primary:
            return "ACTIVE_REGISTRY_CONFLICT", [
                "PRIMARY_CANONICALIZER_RULE_OMITS_USED_COLUMN"
            ]
        return _ACTIVE_ROLE_MAP.get(declared_role, "COVERED_ACTIVE"), []

    if matched:
        return _ACTIVE_ROLE_MAP.get(declared_role, "COVERED_ACTIVE"), []
    if declared_role == "EXPLICITLY_UNUSED":
        return "EXPLICITLY_UNUSED", []
    return "AMBIGUOUS_ACTIVE_COLUMN", ["SOURCE_COLUMN_ROLE_UNDECLARED"]


def zero_failure_counts() -> dict[str, int]:
    return {status: 0 for status in FAILURE_STATUSES}


__all__ = [
    "ALL_STATUSES",
    "FAILURE_STATUSES",
    "PASS_STATUSES",
    "classify_source_column",
    "zero_failure_counts",
]
