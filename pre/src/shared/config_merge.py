from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


class StrictConfigError(ValueError):
    pass


def _compatible_type(expected: Any, value: Any) -> bool:
    if expected is None:
        return True
    if isinstance(expected, bool):
        return isinstance(value, bool)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(expected))


def strict_deep_merge(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
    *,
    path: str = "",
) -> dict[str, Any]:
    if not isinstance(override, Mapping):
        raise StrictConfigError(f"CONFIG_SECTION_TYPE_MISMATCH={path or '<root>'}")
    result = deepcopy(dict(base))
    for key, value in override.items():
        current_path = f"{path}.{key}" if path else str(key)
        if key not in base:
            raise StrictConfigError(f"UNKNOWN_CONFIG_FIELD={current_path}")
        expected = base[key]
        if isinstance(expected, Mapping):
            if not isinstance(value, Mapping):
                raise StrictConfigError(f"CONFIG_FIELD_TYPE_MISMATCH={current_path}")
            result[key] = strict_deep_merge(expected, value, path=current_path)
        else:
            if isinstance(value, Mapping) or not _compatible_type(expected, value):
                raise StrictConfigError(f"CONFIG_FIELD_TYPE_MISMATCH={current_path}")
            result[key] = deepcopy(value)
    return result
